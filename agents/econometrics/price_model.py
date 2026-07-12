import os
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


def interpret_coefficient(feature, coefficient):
    if coefficient > 0:
        direction = "positive"
        meaning = "higher values are associated with higher 12-month home price appreciation"
    elif coefficient < 0:
        direction = "negative"
        meaning = "higher values are associated with lower 12-month home price appreciation"
    else:
        direction = "neutral"
        meaning = "no estimated relationship in this model"

    return f"{feature}: {direction} relationship — {meaning}."


def save_summary(results, data):
    output_path = OUTPUT_DIR / "price_model_summary.txt"

    lines = []

    lines.append("BELL COUNTY ZIP PRICE APPRECIATION MODEL")
    lines.append("=" * 60)
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
    lines.append("-" * 60)

    for feature in ["const"] + FEATURES:
        coef = results.params.get(feature)
        pvalue = results.pvalues.get(feature)

        lines.append(f"{feature}")
        lines.append(f"  coefficient: {coef:.6f}")
        lines.append(f"  p-value: {pvalue:.6f}")

        if feature != "const":
            lines.append(f"  interpretation: {interpret_coefficient(feature, coef)}")

        lines.append("")

    lines.append("RAW STATSMODELS SUMMARY")
    lines.append("-" * 60)
    lines.append(str(results.summary()))

    output = "\n".join(lines)

    with open(output_path, "w") as file:
        file.write(output)

    return output_path, output


def main():
    print("Loading ZIP econometric dataset...")
    df = load_dataset()

    print("Preparing model data...")
    data, X, y = prepare_model_data(df)

    print("Running OLS price appreciation model...")
    results = run_model(X, y)

    output_path, output = save_summary(results, data)

    print(output)
    print(f"\nSaved model summary to: {output_path}")


if __name__ == "__main__":
    main()