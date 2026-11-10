"""Stage 2 - Ray Data pipeline: clean, impute, engineer features, split.

Throughput (rows/sec) and per-stage timings go to metrics/pipeline_metrics.json
and are shown on the UI's Pipeline page.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import ray

from common import add_engineered
from common import track_stage
from common import CLASSES, POLLUTANTS, ensure_dir, get_logger, load_params

log = get_logger("preprocess")


def make_transform(medians: dict, caps: dict):
    """Build a Ray batch function closing over imputation medians and clip caps."""

    def transform(batch: pd.DataFrame) -> pd.DataFrame:
        batch = batch.copy()
        batch["Date"] = pd.to_datetime(batch["Date"])
        for p in POLLUTANTS:
            batch.loc[batch[p] < 0, p] = np.nan                       # invalid -> missing
            city_med = batch["City"].map(medians[p])
            batch[p] = batch[p].fillna(city_med).fillna(medians[p]["__global__"])
            batch[p] = batch[p].clip(upper=caps[p])                   # tame outliers
        batch = add_engineered(batch, batch["Date"].dt.month)
        batch["label"] = batch["AQI_Bucket"].map({c: i for i, c in enumerate(CLASSES)})
        return batch

    return transform


def main() -> None:
    """Entry point for the DVC `preprocess` stage."""
    cfg = load_params()
    d, p = cfg["data"], cfg["preprocess"]
    t0 = time.time()
    raw = pd.read_csv(d["raw_path"], parse_dates=["Date"])
    raw = raw.dropna(subset=["AQI_Bucket"]).drop_duplicates(["City", "Date"])
    n_rows = len(raw)

    # Statistics are fit on the TRAIN period only (avoids leakage).
    cutoff = pd.Timestamp(p["test_cutoff_date"])
    train_part = raw[raw["Date"] < cutoff]
    medians = {}
    for pol in POLLUTANTS:
        m = train_part.groupby("City")[pol].median().to_dict()
        m["__global__"] = float(train_part[pol].median())
        medians[pol] = m
    caps = {pol: float(train_part[pol].quantile(p["clip_quantile"])) for pol in POLLUTANTS}
    t_stats = time.time()

    # Workers must be able to import `common`, whatever directory we were launched from.
    project_dir = str(Path(__file__).resolve().parent)
    ray.init(num_cpus=p["ray_num_cpus"], include_dashboard=False, ignore_reinit_error=True,
             logging_level="ERROR", runtime_env={"env_vars": {"PYTHONPATH": project_dir}})
    t_ray = time.time()
    ds = ray.data.from_pandas(raw)
    ds = ds.map_batches(make_transform(medians, caps), batch_format="pandas",
                        batch_size=p["ray_batch_size"])
    out = ds.to_pandas()
    t_transform = time.time()
    ray.shutdown()

    out = out.sort_values(["City", "Date"]).reset_index(drop=True)
    train = out[out["Date"] < cutoff]
    test = out[out["Date"] >= cutoff]
    if train.empty or test.empty:
        raise ValueError("Time split produced an empty train or test set")
    ensure_dir(d["processed_dir"])
    train.to_csv(f"{d['processed_dir']}/train.csv", index=False)
    test.to_csv(f"{d['processed_dir']}/test.csv", index=False)
    with open(f"{d['processed_dir']}/stats.json", "w", encoding="utf-8") as fh:
        json.dump({"medians": medians, "caps": caps}, fh, indent=2)

    total = time.time() - t0
    transform_s = t_transform - t_ray
    metrics = {
        "engine": "ray.data", "rows_in": n_rows, "rows_train": len(train),
        "rows_test": len(test), "num_cpus": p["ray_num_cpus"],
        "stage_seconds": {"fit_stats": round(t_stats - t0, 3),
                          "ray_startup": round(t_ray - t_stats, 3),
                          "ray_transform": round(transform_s, 3),
                          "write": round(time.time() - t_transform, 3)},
        "total_seconds": round(total, 3),
        "throughput_rows_per_sec_transform": round(n_rows / max(transform_s, 1e-6), 1),
        "throughput_rows_per_sec_end_to_end": round(n_rows / total, 1),
        "status": "success",
    }
    with open("metrics/pipeline_metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    log.info("Preprocess OK: %s rows, %.0f rows/s (transform)", n_rows,
             metrics["throughput_rows_per_sec_transform"])


if __name__ == "__main__":
    with track_stage("preprocess"):
        main()
