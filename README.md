# Electricity Usage and Cost Calculator

This project is a Python script that calculates and summarizes electricity usage and costs for multiple rate plans. It processes a CSV file containing interval-based electricity usage data and uses YAML configuration files to define rate plans and metadata about the CSV file structure.

The csv file should be formatted in the EIEP_13A format
https://www.ea.govt.nz/documents/182/EIEP_13A_Electricity_conveyed_information_for_consumers.pdf

### Features

- Supports both flat and banded rate plans.
- Dynamically determines the date column and interval columns from a configuration file.
- Calculates daily and monthly electricity costs.
- Handles weekends and custom time bands for rate calculations.
- Outputs a detailed monthly summary for each rate plan.

### Requirements

- Python 3.7+
- Libraries: `pandas`, `pyyaml`
- uv

### Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   ```
2. Use uv to run the project
   ```
   uv run calculate.py sampledata.csv
   ```
   
# Usage
 Command-Line Arguments
* `<csvfile>`: Path to the input CSV file containing electricity usage data.
* `--yamlfile`: Path to the YAML file defining rate plans (default: rates.yaml).
* `--config-file`: Path to the YAML configuration file for CSV metadata (default: config.yaml).
* `--out-file`: Path to the output CSV file for the monthly summary (default: monthly_summary.csv).

Example
```bash
python calculate.py <csvfile> [--yamlfile rates.yaml] [--config-file config.yaml] [--out-file monthly_summary.csv]
```
# Configuration Files
### config.yaml

Defines the structure of the input CSV file, including the date column and interval columns.

Example:
```yaml
date_column: "Read Date"
interval_columns:
  - "12:01am-12:30am"
  - "12:31am-1:00am"
  # Add other interval columns here
header_descriptions:
  Read Date: "The date of the meter reading."
  12:01am-12:30am: "Energy usage from 12:01am to 12:30am."
  # Add descriptions for other columns here
```

### rates.yaml

Defines the rate plans, including flat and banded rates.

Example:
```yaml
- title: "Flat Rate Plan"
  daily_rate: 0.50
  per_kwh_rate: 0.15

- title: "Banded Rate Plan"
  daily_rate: 0.40
  bands:
    weekday:
      - start: "00:00"
        end: "07:00"
        rate: 0.10
      - start: "07:00"
        end: "19:00"
        rate: 0.20
      - start: "19:00"
        end: "24:00"
        rate: 0.15
    weekend:
      - start: "00:00"
        end: "24:00"
        rate: 0.12
```

### Output
The script generates a CSV file summarizing monthly electricity usage and costs for each rate plan. It includes:

* Total kWh used per month.
* Fixed and variable costs.
* Total cost for each month.
* A summary row with totals for all months.

#### Example run
```bash
 uv run calculate.py ElectricKiwi\ Consumption\ Data\ -\ 010624\ to\ 010625\ ELECTRICITY.csv 

=== Total summary for Genesis Low User ===
           Title Month  Monthly_kWh  Days_in_month  Fixed_cost  Variable_cost  Total_cost
Genesis Low User TOTAL      3910.65            277      382.26        1147.38     1529.64

=== Total summary for Genesis Normal User ===
              Title Month  Monthly_kWh  Days_in_month  Fixed_cost  Variable_cost  Total_cost
Genesis Normal User TOTAL      3910.65            277      686.79         953.02     1639.82

=== Total summary for Electric Kiwi ===
        Title Month  Monthly_kWh  Days_in_month  Fixed_cost  Variable_cost  Total_cost
Electric Kiwi TOTAL      3910.65            277      318.55        1305.29     1623.84

=== Total summary for Meridian Economy 24 ===
              Title Month  Monthly_kWh  Days_in_month  Fixed_cost  Variable_cost  Total_cost
Meridian Economy 24 TOTAL      3910.65            277      477.83         990.18      1468.0

Saved multi-plan monthly summary to monthly_summary.csv
```
