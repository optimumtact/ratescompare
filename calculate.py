import argparse
from datetime import datetime, timedelta

import pandas as pd
import yaml


def parse_time_str(time_str):
    """Convert a HH:MM string to a timedelta object."""
    hours, minutes = map(int, time_str.split(":"))
    return timedelta(hours=hours, minutes=minutes)


def calculate_band_cost(row, interval_times, bands, is_weekend):
    """
    Calculate the daily cost for a row (day) based on band rates.

    Parameters:
    - row: a DataFrame row representing a single day's intervals
    - interval_times: list of timedelta objects for each half-hour column
    - bands: dict with 'weekday' and 'weekend' lists of band dicts {start, end, rate}
    - is_weekend: boolean indicating if the day is weekend

    Returns:
    - daily cost (float)
    """
    total_cost = 0.0
    applicable_bands = bands["weekend"] if is_weekend else bands["weekday"]

    # Convert band times to timedeltas
    band_ranges = []
    for band in applicable_bands:
        start_td = parse_time_str(band["start"])
        end_td = parse_time_str(band["end"])
        rate = band["rate"]
        band_ranges.append((start_td, end_td, rate))

    # Multiply each interval kWh by its band rate
    for i, col in enumerate(interval_times):
        kwh = row.iloc[i]
        interval_time = interval_times[i]
        for start, end, rate in band_ranges:
            # Handle the special case where end="24:00"
            if end.total_seconds() == 0:
                end = timedelta(hours=24)
            if start <= interval_time < end:
                total_cost += kwh * rate
                break  # Only one band applies
    return total_cost


def main():
    parser = argparse.ArgumentParser(
        description="Summarise electricity usage and cost for multiple rate plans (flat or banded)."
    )
    parser.add_argument("csvfile", help="Path to the power CSV file")
    parser.add_argument(
        "--yamlfile",
        default="rates.yaml",
        help="Path to YAML file with rate plans (default: rates.yaml)",
    )
    parser.add_argument(
        "--config-file",
        default="config.yaml",
        help="Path to YAML config file with CSV header metadata",
    )
    parser.add_argument(
        "--out-file", default="monthly_summary.csv", help="Output CSV filename"
    )
    args = parser.parse_args()

    # --- Load Config YAML ---
    with open(args.config_file) as f:
        config = yaml.safe_load(f)

    date_col = config["date_column"]
    interval_cols = config["interval_columns"]

    # --- Load CSV ---
    df = pd.read_csv(args.csvfile)

    # Ensure date column exists
    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' not found in CSV file.")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    # Ensure interval columns exist
    missing_cols = [col for col in interval_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Interval columns missing in CSV: {missing_cols}")

    df[interval_cols] = df[interval_cols].apply(pd.to_numeric, errors="coerce")

    # Each interval represents a 30-minute period
    interval_times = [timedelta(minutes=30 * i) for i in range(len(interval_cols))]

    # --- Load YAML rate plans ---
    with open(args.yamlfile) as f:
        rate_plans = yaml.safe_load(f)

    all_results = []

    # --- Loop over each provider ---
    for plan in rate_plans:
        title = plan.get("title", "Unknown")
        daily_rate = plan.get("daily_rate", 0.0)
        per_kwh_rate = plan.get("per_kwh_rate", None)
        bands = plan.get("bands", None)  # None for flat rate

        daily_costs = []

        # --- Calculate daily costs ---
        for idx, row in df.iterrows():
            day = row[date_col]
            is_weekend = day.weekday() >= 5  # Saturday=5, Sunday=6

            if bands:
                # Banded rate
                daily_cost = calculate_band_cost(
                    row[interval_cols], interval_times, bands, is_weekend
                )
                daily_cost += daily_rate  # add daily fixed rate if specified
            else:
                # Flat rate
                kwh = row[interval_cols].sum()
                rate = per_kwh_rate if per_kwh_rate is not None else 0.0
                daily_cost = daily_rate + kwh * rate

            daily_costs.append(daily_cost)

        df["daily_kwh"] = df[interval_cols].sum(axis=1)
        df["daily_cost"] = daily_costs

        # --- Aggregate monthly ---
        monthly = (
            df.groupby(df[date_col].dt.to_period("M"))
            .agg(
                Monthly_kWh=("daily_kwh", "sum"),
                Days_in_month=(date_col, "count"),
                Fixed_cost=("daily_cost", lambda x: (daily_rate * len(x))),
                Variable_cost=("daily_cost", lambda x: x.sum() - (daily_rate * len(x))),
            )
            .reset_index()
        )
        monthly["Total_cost"] = monthly["Fixed_cost"] + monthly["Variable_cost"]
        monthly["Title"] = title
        monthly["Month"] = monthly[date_col].dt.strftime("%Y-%m")
        monthly = monthly[
            [
                "Title",
                "Month",
                "Monthly_kWh",
                "Days_in_month",
                "Fixed_cost",
                "Variable_cost",
                "Total_cost",
            ]
        ]

        # --- Add total summary row ---
        total_row = pd.DataFrame(
            {
                "Title": [title],
                "Month": ["TOTAL"],
                "Monthly_kWh": [monthly["Monthly_kWh"].sum().round(2)],
                "Days_in_month": [monthly["Days_in_month"].sum()],
                "Fixed_cost": [monthly["Fixed_cost"].sum().round(2)],
                "Variable_cost": [monthly["Variable_cost"].sum().round(2)],
                "Total_cost": [monthly["Total_cost"].sum().round(2)],
            }
        )
        monthly = pd.concat([monthly, total_row], ignore_index=True)

        # Print total to terminal
        print(f"\n=== Total summary for {title} ===")
        print(total_row.to_string(index=False))

        all_results.append(monthly)

    # --- Save all results ---
    final_df = pd.concat(all_results, ignore_index=True)
    final_df.to_csv(args.out_file, index=False)
    print(f"\nSaved multi-plan monthly summary to {args.out_file}")


if __name__ == "__main__":
    main()
