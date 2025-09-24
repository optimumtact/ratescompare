import argparse
from datetime import datetime, timedelta

import pandas as pd
import yaml


def parse_time_str(time_str):
    """Convert HH:MM string to timedelta."""
    hours, minutes = map(int, time_str.split(":"))
    return timedelta(hours=hours, minutes=minutes)


def calculate_band_cost(kwh, interval_time, bands):
    """Return cost for one interval based on bands."""
    for band in bands:
        start_td = parse_time_str(band["start"])
        end_td = parse_time_str(band["end"])
        if end_td.total_seconds() == 0:  # handle "24:00"
            end_td = timedelta(hours=24)
        if start_td <= interval_time < end_td:
            return kwh * band["rate"]
    return 0.0


import csv
from datetime import datetime

import pandas as pd


def load_eiep13a(csvfile):
    """
    Parse an EIEP13A CSV (lowercase header style) into a dataframe of half-hourly imports/exports.
    """
    # Read the CSV file into a DataFrame
    df = pd.read_csv(csvfile)
    # Filter rows where "Record Type" is "DET"
    df = df[df["rec_type"].str.strip().str.upper() == "DET"]

    # Convert columns to appropriate types
    df["read_start"] = pd.to_datetime(df["read_start"].str.strip(), errors="coerce")
    df["read_end"] = pd.to_datetime(df["read_end"].str.strip(), errors="coerce")
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce").fillna(0.0)
    df["energy_flow_direction"] = df["energy_flow_direction"].str.strip().str.upper()

    # Return the cleaned DataFrame
    return df[["read_start", "read_end", "energy_flow_direction", "kwh"]]


def main():
    parser = argparse.ArgumentParser(
        description="Summarise electricity usage/costs with imports and exports"
    )
    parser.add_argument("csvfiles", nargs="+", help="EIEP13A CSV files")
    parser.add_argument("--yamlfile", default="rates.yaml", help="Rate plans file")
    parser.add_argument("--out-file", default="monthly_summary.csv", help="Output CSV")
    args = parser.parse_args()

    # --- Load rate plans ---
    with open(args.yamlfile) as f:
        rate_plans = yaml.safe_load(f)

    # --- Load all EIEP13A data ---
    df_all = pd.concat([load_eiep13a(f) for f in args.csvfiles], ignore_index=True)

    df_all["date"] = df_all["read_start"].dt.date
    df_all["month"] = df_all["read_start"].dt.to_period("M")
    df_all["interval_time"] = (
        df_all["read_start"].dt.hour * 60 + df_all["read_start"].dt.minute
    )
    df_all["interval_td"] = df_all["interval_time"].apply(
        lambda m: timedelta(minutes=m)
    )

    all_results = []

    for plan in rate_plans:
        title = plan.get("title", "Unknown")
        daily_rate = plan.get("daily_rate", 0.0)
        per_kwh_rate = plan.get("per_kwh_rate")
        bands = plan.get("bands")
        fixed_discount = plan.get("fixed_discount", 0.0)
        export_rates = plan.get("export_rates", None)  # new: support export rates

        daily_results = []

        for date, group in df_all.groupby("date"):
            is_weekend = pd.to_datetime(date).weekday() >= 5
            imports, exports = 0.0, 0.0

            for _, row in group.iterrows():
                kwh = row["kwh"]
                interval_td = row["interval_td"]

                if row["energy_flow_direction"] == "I":  # Import
                    if bands:
                        applicable = (
                            bands["weekend"] if is_weekend else bands["weekday"]
                        )
                        imports += calculate_band_cost(kwh, interval_td, applicable)
                    else:
                        rate = per_kwh_rate if per_kwh_rate is not None else 0.0
                        imports += kwh * rate
                elif row["energy_flow_direction"] == "X":  # Export
                    if export_rates:
                        applicable = export_rates.get(
                            "weekend" if is_weekend else "weekday"
                        )
                        if applicable:
                            exports += calculate_band_cost(kwh, interval_td, applicable)
                        else:
                            rate = export_rates.get("flat", 0.0)
                            exports += kwh * rate
                    # else: exports ignored

            daily_cost = daily_rate + imports - exports
            daily_results.append((date, daily_cost, imports, exports))

        daily_df = pd.DataFrame(
            daily_results, columns=["date", "daily_cost", "imports", "exports"]
        )
        monthly = (
            daily_df.groupby(
                daily_df["date"].map(lambda d: pd.to_datetime(d).to_period("M"))
            )
            .agg(
                Fixed_cost=("daily_cost", lambda x: daily_rate * len(x)),
                Variable_cost=("imports", "sum"),
                Credits=("exports", "sum"),
                Days_in_month=("date", "count"),
            )
            .reset_index()
        )
        totalcost = monthly["Fixed_cost"] + monthly["Variable_cost"]

        monthly["Total_cost"] = (
            monthly["Fixed_cost"] + monthly["Variable_cost"] - monthly["Credits"]
        )
        # Pre load column with 0
        monthly["Discounts"] = 0.0
        if fixed_discount:
            monthly["Discounts"] = monthly["Total_cost"] * (fixed_discount / 100)
            monthly["Total_cost"] *= 1 - fixed_discount / 100

        monthly["Title"] = title
        monthly["Month"] = monthly["date"].dt.strftime("%Y-%m")
        monthly["totalcostnotadjusted"] = totalcost
        monthly = monthly[
            [
                "Title",
                "Month",
                "Days_in_month",
                "Fixed_cost",
                "Variable_cost",
                "Credits",
                "Discounts",
                "Total_cost",
                "totalcostnotadjusted",
            ]
        ]
        # --- Add total summary row ---
        total_row = pd.DataFrame(
            {
                "Title": [title],
                "Month": ["TOTAL"],
                "Days_in_month": [monthly["Days_in_month"].sum()],
                "Fixed_cost": [monthly["Fixed_cost"].sum().round(2)],
                "Variable_cost": [monthly["Variable_cost"].sum().round(2)],
                "Credits": [monthly["Credits"].sum().round(2)],
                "Discounts": [monthly["Discounts"].sum().round(2)],
                "Total_cost": [monthly["Total_cost"].sum().round(2)],
                "totalcostnotadjusted": [
                    monthly["totalcostnotadjusted"].sum().round(2)
                ],
            }
        )
        monthly = pd.concat([monthly, total_row], ignore_index=True)

        # --- Print summary to console ---
        total_days = total_row["Days_in_month"].iloc[0]
        fixed_cost = total_row["Fixed_cost"].iloc[0]
        variable_cost = total_row["Variable_cost"].iloc[0]
        credits = total_row["Credits"].iloc[0]
        discounts = total_row["Discounts"].iloc[0]
        total_cost = total_row["Total_cost"].iloc[0]
        total_cost_notadjusted = total_row["totalcostnotadjusted"].iloc[0]

        print(f"\n=== Summary for plan: {title} ===")
        print(f"  Total days: {total_days}")
        print(f"  Fixed cost: ${fixed_cost:.2f}")
        print(f"  Variable cost: ${variable_cost:.2f}")
        print(f"  Credits from exports: ${credits:.2f}")
        print(f"  Discounts saved: ${discounts:.2f}")
        print(f"  TOTAL cost: ${total_cost:.2f}")
        print(
            f"  Total before discounts and export credits: ${total_cost_notadjusted:.2f}"
        )
        print("=" * 40)

        all_results.append(monthly)

        all_results.append(monthly)

    final_df = pd.concat(all_results, ignore_index=True)
    final_df.to_csv(args.out_file, index=False)
    print(f"Saved results to {args.out_file}")


if __name__ == "__main__":
    main()
