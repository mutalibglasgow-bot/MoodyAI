from pathlib import Path

import pandas as pd
import statsmodels.api as sm


DATA_PATH = Path("data/econometrics/processed/bell_county_zip_panel.csv")
OUTPUT_DIR = Path("data/econometrics/models")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


DEPENDENT_VARIABLE = "zhvi_12mo_change"

FEATURES = [
    "mortgage_30yr_lag_12",
    "fed_funds_rate_lag_12",
    "unemployment_rate_lag_12",
    "cpi_lag_12",
    "active_inventory",
    "days_on_market",
    "new_listings",
]


def load_dataset():
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Missing dataset: {DATA_PATH}. Run build_zip_dataset.py first."
        )

    df = pd.read_csv(DATA_PATH)
    df["date"] = pd.to_datetime(df["date"])

    return df


def prepare_model_data(df):
    model_cols = ["date", "zip_code", "City", DEPENDENT_VARIABLE] + FEATURES

    data = df[model_cols].copy()

    for col in [DEPENDENT_VARIABLE] + FEATURES:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.dropna()
    data = data.sort_values(["zip_code", "date"])

    y = data[DEPENDENT_VARIABLE]
    X = data[FEATURES]
    X = sm.add_constant(X)

    return data, X, y


def run_model(X, y):
    model = sm.OLS(y, X)
    results = model.fit(cov_type="HC3")
    return results


def save_summary(results, data):
    output_path = OUTPUT_DIR / "inventory_model_summary.txt"

    lines = []

    lines.append("BELL COUNTY ZIP INVENTORY-ENHANCED PRICE MODEL")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Dependent variable: {DEPENDENT_VARIABLE}")
    lines.append(f"Observation count: {int(results.nobs)}")
    lines.append(f"ZIP codes included: {', '.join(sorted(data['zip_code'].astype(str).unique()))}")
    lines.append(f"Date range: {data['date'].min().date()} to {data['date'].max().date()}")
    lines.append("")
    lines.append(f"R-squared: {results.rsquared:.4f}")
    lines.append(f"Adjusted R-squared: {results.rsquared_adj:.4f}")
    lines.append("")
    lines.append("COEFFICIENTS")
    lines.append("-" * 70)

    for feature in ["const"] + FEATURES:
        coef = results.params.get(feature)
        pvalue = results.pvalues.get(feature)

        lines.append(f"{feature}")
        lines.append(f"  coefficient: {coef:.6f}")
        lines.append(f"  p-value: {pvalue:.6f}")

        if feature == "active_inventory":
            lines.append("  interpretation: Higher inventory usually means more supply and weaker price pressure.")
        elif feature == "days_on_market":
            lines.append("  interpretation: Higher DOM usually means slower demand and weaker price pressure.")
        elif feature == "new_listings":
            lines.append("  interpretation: More new listings usually means more supply entering the market.")
        elif feature != "const":
            direction = "higher" if coef > 0 else "lower"
            lines.append(f"  interpretation: Higher {feature} is associated with {direction} 12-month appreciation.")

        lines.append("")

    lines.append("RAW STATSMODELS SUMMARY")
    lines.append("-" * 70)
    lines.append(str(results.summary()))

    output = "\n".join(lines)

    with open(output_path, "w") as file:
        file.write(output)

    return output_path, output


def main():
    print("Loading ZIP econometric dataset...")
    df = load_dataset()

    print("Preparing inventory-enhanced model data...")
    data, X, y = prepare_model_data(df)

    if len(data) == 0:
        print("No usable rows found.")
        print("")
        print("This is expected until active_inventory, days_on_market, and new_listings are populated.")
        print("Next step: merge Redfin/Realtor.com inventory data into bell_county_zip_panel.csv.")
        return

    print("Running inventory-enhanced OLS model...")
    results = run_model(X, y)

    output_path, output = save_summary(results, data)

    print(output)
    print(f"\nSaved model summary to: {output_path}")


if __name__ == "__main__":
    main()