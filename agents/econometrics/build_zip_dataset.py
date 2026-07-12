from io import StringIO
from pathlib import Path

import certifi
import pandas as pd
import requests

ZIP_CODES = [
    "76502", "76504", "76513", "76559",
    "76571", "76548", "76549", "76542", "76543"
]

DATA_DIR = Path("data/econometrics")
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

ZILLOW_ZIP_ZHVI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
)

FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "unemployment_rate": "UNRATE",
    "mortgage_30yr": "MORTGAGE30US",
}


def fred_csv_url(series_id):
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def fetch_csv(url, timeout=60):
    response = requests.get(url, verify=certifi.where(), timeout=timeout)
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))


def load_fred_series(name, series_id):
    print(f"Loading FRED: {name} ({series_id})")
    df = fetch_csv(fred_csv_url(series_id), timeout=30)

    df.columns = ["date", name]
    df["date"] = pd.to_datetime(df["date"])
    df[name] = pd.to_numeric(df[name], errors="coerce")
    df = df.dropna()

    df["month"] = df["date"].dt.to_period("M").astype(str)

    return df[["month", name]]


def build_macro_dataset():
    macro = None

    for name, series_id in FRED_SERIES.items():
        df = load_fred_series(name, series_id)

        if macro is None:
            macro = df
        else:
            macro = macro.merge(df, on="month", how="outer")

    macro = macro.sort_values("month")
    macro.to_csv(PROCESSED_DIR / "macro_monthly.csv", index=False)

    return macro


def load_zillow_zip_prices():
    print("Loading Zillow ZIP ZHVI...")
    df = fetch_csv(ZILLOW_ZIP_ZHVI_URL, timeout=60)

    id_cols = [
        "RegionID", "SizeRank", "RegionName", "RegionType",
        "StateName", "State", "City", "Metro", "CountyName"
    ]

    date_cols = [c for c in df.columns if c not in id_cols]

    df["RegionName"] = df["RegionName"].astype(str)
    df = df[df["RegionName"].isin(ZIP_CODES)]

    long_df = df.melt(
        id_vars=id_cols,
        value_vars=date_cols,
        var_name="date",
        value_name="zhvi"
    )

    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df["month"] = long_df["date"].dt.to_period("M").astype(str)
    long_df["zip_code"] = long_df["RegionName"].astype(str)
    long_df["zhvi"] = pd.to_numeric(long_df["zhvi"], errors="coerce")

    long_df = long_df[
        ["date", "month", "zip_code", "City", "CountyName", "zhvi"]
    ].dropna()

    long_df = long_df.sort_values(["zip_code", "date"])
    long_df.to_csv(PROCESSED_DIR / "zip_zhvi_monthly.csv", index=False)

    return long_df


def add_local_placeholders(panel):
    panel["property_tax_rate"] = None
    panel["crime_index"] = None
    panel["school_rating"] = None
    panel["average_wage"] = None
    panel["days_on_market"] = None
    panel["active_inventory"] = None
    panel["new_listings"] = None
    return panel


def build_zip_panel():
    macro = build_macro_dataset()
    zhvi = load_zillow_zip_prices()

    panel = zhvi.merge(macro, on="month", how="left")
    panel = panel.sort_values(["zip_code", "date"])

    panel["zhvi_1mo_change"] = panel.groupby("zip_code")["zhvi"].pct_change(1)
    panel["zhvi_3mo_change"] = panel.groupby("zip_code")["zhvi"].pct_change(3)
    panel["zhvi_12mo_change"] = panel.groupby("zip_code")["zhvi"].pct_change(12)

    for col in ["mortgage_30yr", "fed_funds_rate", "unemployment_rate", "cpi"]:
        panel[f"{col}_lag_1"] = panel.groupby("zip_code")[col].shift(1)
        panel[f"{col}_lag_3"] = panel.groupby("zip_code")[col].shift(3)
        panel[f"{col}_lag_12"] = panel.groupby("zip_code")[col].shift(12)

    panel = add_local_placeholders(panel)

    output_path = PROCESSED_DIR / "bell_county_zip_panel.csv"
    panel.to_csv(output_path, index=False)

    print(f"\nSaved ZIP econometric panel to: {output_path}")
    print(f"Rows: {len(panel)}")
    print(panel.tail(20))


if __name__ == "__main__":
    build_zip_panel()