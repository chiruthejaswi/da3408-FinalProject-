"""Why is real-data macro-F1 lower? Splits test results by whether readings were missing, and compares with the CPCB formula."""
import json
import warnings
import mlflow.sklearn
import pandas as pd
from sklearn.metrics import f1_score, recall_score
from common import CLASSES, FEATURES, POLLUTANTS
from ingest import bucket, sub_index
warnings.filterwarnings("ignore")

test = pd.read_csv("data/processed/test.csv", parse_dates=["Date"])
test["month"] = test["month"].astype(float)
raw = pd.read_csv("data/interim/city_day.csv", parse_dates=["Date"])
q = json.load(open("metrics/data_quality.json"))
print(f"source={q['source']} | raw rows={q['rows']} | cities={q['cities']} | test rows={len(test)}")
print("missing % per pollutant:", q["null_pct"])
print("\nTEST rows per class:", test["AQI_Bucket"].value_counts().reindex(CLASSES).fillna(0).astype(int).to_dict())

model = mlflow.sklearn.load_model("models/airsense_model")
y = test["label"].values
pred = model.predict(test[FEATURES])
labels = list(range(6))
def f1(yt, yp):
    """Macro-F1 over all six classes."""
    return f1_score(yt, yp, average="macro", labels=labels, zero_division=0)

# which test rows had at least one of the 6 readings missing BEFORE imputation?
orig = raw[["City", "Date", *POLLUTANTS]].rename(columns={p: p + "_orig" for p in POLLUTANTS})
m = test[["City", "Date"]].merge(orig, on=["City", "Date"], how="left")
had_gap = m[[p + "_orig" for p in POLLUTANTS]].isna().any(axis=1).values
print(f"\nTest rows with >=1 missing reading (imputed): {had_gap.mean():.1%}")

aqi = test[POLLUTANTS].apply(lambda col: col.map(lambda v, p=col.name: sub_index(p, v))).max(axis=1)
formula = aqi.map(bucket).map({c: i for i, c in enumerate(CLASSES)}).fillna(0).astype(int).values

print("\n                              macro-F1   accuracy   rows")
groups = [("ALL test rows", slice(None)), ("complete rows (no imputation)", ~had_gap), ("rows with imputation", had_gap)]
for name, mask in groups:
    if (mask.sum() if hasattr(mask, "sum") else len(y)) == 0:
        continue
    n = int(mask.sum()) if hasattr(mask, "sum") else len(y)
    print(f"model   {name:30s} {f1(y[mask], pred[mask]):.4f}    {(y[mask] == pred[mask]).mean():.4f}   {n}")
    print(f"formula {name:30s} {f1(y[mask], formula[mask]):.4f}    {(y[mask] == formula[mask]).mean():.4f}   {n}")
rec = recall_score(y, pred, labels=labels, average=None, zero_division=0)
print("\nper-class recall (model):", {c: round(float(r), 3) for c, r in zip(CLASSES, rec)})
