"""Stage 1 - Ingest & validate raw data.

Uses the real Kaggle `city_day.csv` if present at params.data.raw_path (input only, never modified).
Otherwise generates a clearly-labelled SYNTHETIC dataset with the same schema so the whole
pipeline is runnable offline. Drop the real file in data/raw/ and run `dvc repro` - no code changes.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common import track_stage
from common import (BREAKPOINTS, CLASSES, POLLUTANTS, ensure_dir,
                               get_logger, load_params)

log = get_logger("ingest")

# (PM2.5, PM10, NO2, SO2, CO, O3) typical medians per city for synthetic data.
CITY_PROFILE = {
    "Delhi": (110, 230, 50, 15, 1.6, 40), "Mumbai": (45, 100, 35, 18, 1.0, 35),
    "Chennai": (35, 70, 25, 12, 0.8, 30), "Kolkata": (70, 130, 40, 14, 1.2, 38),
    "Bengaluru": (30, 75, 28, 10, 0.7, 32), "Hyderabad": (40, 85, 30, 11, 0.9, 33),
    "Ahmedabad": (60, 120, 38, 40, 1.4, 45), "Patna": (95, 180, 42, 13, 1.5, 36),
    "Lucknow": (85, 190, 45, 12, 1.3, 38), "Aizawl": (15, 30, 10, 5, 0.3, 28),
}


def sub_index(pollutant: str, value: float) -> float:
    """CPCB sub-index for one pollutant (linear interpolation in its band)."""
    if value is None or np.isnan(value):
        return np.nan
    for c_lo, c_hi, i_lo, i_hi in BREAKPOINTS[pollutant]:
        if value <= c_hi:
            return i_lo + (value - c_lo) * (i_hi - i_lo) / (c_hi - c_lo)
    return 500.0


def bucket(aqi: float):
    """Map numeric AQI to its CPCB category."""
    if aqi is None or np.isnan(aqi):
        return None
    for edge, name in zip([50, 100, 200, 300, 400], CLASSES):
        if aqi <= edge:
            return name
    return CLASSES[-1]


def make_synthetic(rows_per_city: int, seed: int) -> pd.DataFrame:
    """Generate realistic seasonal, log-normal pollutant data with gaps."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=rows_per_city, freq="D")
    season = 1 + 0.45 * np.cos(2 * np.pi * (dates.day_of_year.values - 15) / 365)
    frames = []
    for city, prof in CITY_PROFILE.items():
        data = {"City": city, "Date": dates}
        for name, med in zip(POLLUTANTS, prof):
            noise = rng.lognormal(0, 0.45, len(dates))
            data[name] = np.round(med * season * noise, 2)
        frames.append(pd.DataFrame(data))
    df = pd.concat(frames, ignore_index=True)
    sub = np.column_stack([df[p].map(lambda v, p=p: sub_index(p, v)) for p in POLLUTANTS])
    df["AQI"] = np.round(np.nanmax(sub, axis=1))
    df["AQI_Bucket"] = df["AQI"].map(bucket)
    for p in POLLUTANTS:  # ~6% missing values, like the real data
        df.loc[rng.random(len(df)) < 0.06, p] = np.nan
    return df


def validate(df: pd.DataFrame) -> dict:
    """Schema + quality checks. Raises ValueError on a hard failure."""
    required = ["City", "Date", *POLLUTANTS, "AQI_Bucket"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if len(df) == 0:
        raise ValueError("Dataset is empty")
    return {
        "rows": int(len(df)),
        "cities": int(df["City"].nunique()),
        "null_pct": {p: round(float(df[p].isna().mean() * 100), 2) for p in POLLUTANTS},
        "unlabelled_rows": int(df["AQI_Bucket"].isna().sum()),
        "negative_values": int((df[POLLUTANTS] < 0).sum().sum()),
        "class_counts": {k: int(v) for k, v in df["AQI_Bucket"].value_counts().items()},
    }


def main() -> None:
    """Entry point for the DVC `ingest` stage.

    Reads the user's real CSV if present (never modified); otherwise generates synthetic data in memory.
    Either way the validated result goes to params.data.interim_path and its provenance is recorded.
    """
    params = load_params()["data"]
    start = time.time()
    raw, interim = Path(params["raw_path"]), Path(params["interim_path"])
    if raw.exists():
        log.info("Using REAL dataset at %s", raw)
        df = pd.read_csv(raw, parse_dates=["Date"])
        source = "real"
    else:
        log.warning("No real CSV at %s - generating SYNTHETIC demo data", raw)
        df = make_synthetic(params["synthetic_rows_per_city"], params["seed"])
        source = "synthetic"
    report = validate(df)
    ensure_dir(str(interim.parent))
    df.to_csv(interim, index=False)
    report.update(source=source, seconds=round(time.time() - start, 3))
    ensure_dir("metrics")
    with open("metrics/data_quality.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    log.info("Ingest OK: %s rows, %s cities (%s)", report["rows"], report["cities"], source)


if __name__ == "__main__":
    with track_stage("ingest"):
        main()
