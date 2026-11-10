"""Stage 3 - Train candidates, track with MLflow, select best, export model.

Selection uses a time-based VALIDATION slice of the training period; the test
set (later in time) is touched only once, for the final chosen model.
Reproducibility: every run is tagged with the Git commit hash and dataset hash.
"""
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (accuracy_score, classification_report,  # noqa: E402
                             confusion_matrix, f1_score, recall_score)
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from common import CLASSES, ensure_dir, get_logger, load_params  # noqa: E402
from common import FEATURES  # noqa: E402
from common import track_stage  # noqa: E402

log = get_logger("train")


def git_commit() -> str:
    """Current Git commit hash (+'-dirty' if code/params/pipeline files have uncommitted changes), or 'unknown'."""
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        clean = subprocess.call(["git", "diff", "--quiet", "HEAD", "--", "*.py", "params.yaml", "dvc.yaml"],
                                stderr=subprocess.DEVNULL) == 0
        return sha if clean else sha + "-dirty"
    except Exception:  # noqa: BLE001
        return "unknown"


def file_md5(path: str) -> str:
    """MD5 of a file, used as a dataset-version tag."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_models(cfg: dict) -> dict:
    """Candidate estimators defined from params.yaml."""
    seed = cfg["seed"]
    return {
        "logreg": Pipeline([("scale", StandardScaler()),
                            ("clf", LogisticRegression(class_weight="balanced", **cfg["logreg"]))]),
        "random_forest": RandomForestClassifier(class_weight="balanced", n_jobs=-1,
                                                random_state=seed, **cfg["random_forest"]),
        "hist_gb": HistGradientBoostingClassifier(random_state=seed, **cfg["hist_gb"]),
    }


def evaluate(model, X, y) -> dict:
    """Accuracy, macro/weighted F1 and per-class recall."""
    pred = model.predict(X)
    labels = list(range(len(CLASSES)))
    rec = recall_score(y, pred, labels=labels, average=None, zero_division=0)
    out = {"accuracy": accuracy_score(y, pred),
           "macro_f1": f1_score(y, pred, average="macro", labels=labels, zero_division=0),
           "weighted_f1": f1_score(y, pred, average="weighted", zero_division=0)}
    out.update({f"recall_{c.replace(' ', '_')}": float(r) for c, r in zip(CLASSES, rec)})
    return out


def plot_confusion(y, pred, path: str) -> None:
    """Save a confusion-matrix PNG."""
    cm = confusion_matrix(y, pred, labels=list(range(len(CLASSES))))
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(CLASSES)), CLASSES, rotation=45, ha="right")
    ax.set_yticks(range(len(CLASSES)), CLASSES)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def check_local_experiment(name: str, tracking_uri: str) -> None:
    """Fail with a clear message if a local MLflow store was created in a different folder/machine.

    mlflow.db remembers ABSOLUTE artifact paths; copying the project elsewhere leaves them dangling.
    """
    if not tracking_uri.startswith(("sqlite:", "file:")):
        return
    exp = mlflow.get_experiment_by_name(name)
    if exp is None:
        return
    loc = exp.artifact_location.replace("file://", "")
    if loc.startswith("/") and not Path(loc).resolve().is_relative_to(Path.cwd().resolve()):
        raise RuntimeError(
            f"MLflow experiment '{name}' stores artifacts in '{loc}', which is outside this project "
            "(mlflow.db was created elsewhere). Delete mlflow.db and the mlruns/ folder and re-run; "
            "they are regenerated automatically.")


def main() -> None:
    """Entry point for the DVC `train` stage."""
    cfg = load_params()
    d, t = cfg["data"], cfg["train"]
    train = pd.read_csv(f"{d['processed_dir']}/train.csv", parse_dates=["Date"])
    test = pd.read_csv(f"{d['processed_dir']}/test.csv", parse_dates=["Date"])
    for df in (train, test):  # float64 month avoids MLflow int-schema warnings
        df["month"] = df["month"].astype("float64")
    val_cut = train["Date"].quantile(1 - t["val_fraction"])
    sub, val = train[train["Date"] < val_cut], train[train["Date"] >= val_cut]
    log.info("train_sub=%d val=%d test=%d", len(sub), len(val), len(test))

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")
    mlflow.set_tracking_uri(tracking_uri)
    check_local_experiment(t["experiment_name"], tracking_uri)
    mlflow.set_experiment(t["experiment_name"])
    mlflow.sklearn.autolog(log_models=False, log_datasets=False, silent=True)
    commit, data_hash = git_commit(), file_md5(f"{d['processed_dir']}/train.csv")
    common_tags = {"git_commit": commit, "dataset_md5": data_hash,
                   "dvc_stage": "train", "data_source": json.load(
                       open("metrics/data_quality.json"))["source"]}

    # ---- 1. Candidate comparison on the validation slice --------------------
    scores = {}
    for name, model in build_models(t).items():
        with mlflow.start_run(run_name=f"candidate-{name}"):
            mlflow.set_tags({**common_tags, "role": "candidate"})
            mlflow.log_params({"model": name, "n_features": len(FEATURES),
                               "features": ",".join(FEATURES),
                               "train_rows": len(sub), "val_rows": len(val)})
            t0 = time.time()
            model.fit(sub[FEATURES], sub["label"])
            fit_s = time.time() - t0
            m = evaluate(model, val[FEATURES], val["label"])
            t1 = time.time()
            model.predict(val[FEATURES])
            m["fit_seconds"] = fit_s
            m["predict_ms_per_row"] = (time.time() - t1) * 1000 / len(val)
            mlflow.log_metrics({f"val_{k}": v for k, v in m.items()})
            scores[name] = m["macro_f1"]
            log.info("%-14s val macro-F1=%.4f acc=%.4f", name, m["macro_f1"], m["accuracy"])
    best = max(scores, key=scores.get)

    # ---- 2. Refit winner on full train, evaluate ONCE on test ---------------
    final = build_models(t)[best]
    with mlflow.start_run(run_name=f"final-{best}") as run:
        mlflow.set_tags({**common_tags, "role": "final", "selected_model": best})
        mlflow.log_params({"model": best, "selection_metric": "val_macro_f1",
                           "candidate_scores": json.dumps({k: round(v, 4) for k, v in scores.items()})})
        final.fit(train[FEATURES], train["label"])
        metrics = evaluate(final, test[FEATURES], test["label"])
        mlflow.log_metrics({f"test_{k}": v for k, v in metrics.items()})
        pred = final.predict(test[FEATURES])

        ensure_dir("metrics")
        plot_confusion(test["label"], pred, "metrics/confusion_matrix.png")
        imp = permutation_importance(final, test[FEATURES], test["label"], n_repeats=3,
                                     random_state=t["seed"], scoring="f1_macro", n_jobs=1)
        imp_df = pd.DataFrame({"feature": FEATURES, "importance": imp.importances_mean}
                              ).sort_values("importance", ascending=False)
        imp_df.to_csv("metrics/feature_importance.csv", index=False)
        report = classification_report(test["label"], pred, labels=list(range(len(CLASSES))),
                                       target_names=CLASSES, zero_division=0)
        with open("metrics/classification_report.txt", "w", encoding="utf-8") as fh:
            fh.write(report)
        for f in ["confusion_matrix.png", "feature_importance.csv", "classification_report.txt"]:
            mlflow.log_artifact(f"metrics/{f}")
        mlflow.log_artifact(f"{d['processed_dir']}/stats.json")
        mlflow.sklearn.log_model(final, name="model", serialization_format="cloudpickle",
                                 input_example=test[FEATURES].head(3))

        # ---- 3. Export for the backend (MLflow model format) ----------------
        out_dir = "models/airsense_model"
        shutil.rmtree(out_dir, ignore_errors=True)
        # cloudpickle: we only ever load our OWN trusted artifact (see HLD security notes).
        mlflow.sklearn.save_model(final, out_dir, serialization_format="cloudpickle",
                                  input_example=test[FEATURES].head(3))
        stats = json.load(open(f"{d['processed_dir']}/stats.json"))
        meta = {
            "model_name": best, "mlflow_run_id": run.info.run_id, "git_commit": commit,
            "dataset_md5": data_hash, "trained_at": datetime.now(timezone.utc).isoformat(),
            "data_source": common_tags["data_source"],
            "classes": CLASSES, "features": FEATURES,
            "cities": sorted(train["City"].unique().tolist()),
            "medians": stats["medians"], "caps": stats["caps"],
            "feature_mean": train[FEATURES].mean().to_dict(),
            "feature_std": train[FEATURES].std().to_dict(),
            "test_metrics": {k: round(float(v), 4) for k, v in metrics.items()},
            "candidate_val_macro_f1": {k: round(v, 4) for k, v in scores.items()},
        }
        with open("models/model_meta.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        with open("metrics/train_metrics.json", "w", encoding="utf-8") as fh:
            json.dump({"selected": best, "run_id": run.info.run_id, "git_commit": commit,
                       **{k: round(float(v), 4) for k, v in metrics.items()}}, fh, indent=2)
    log.info("Selected %s | test macro-F1=%.4f acc=%.4f | run_id=%s",
             best, metrics["macro_f1"], metrics["accuracy"], run.info.run_id)


if __name__ == "__main__":
    with track_stage("train"):
        main()
