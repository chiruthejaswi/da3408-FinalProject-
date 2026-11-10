"""How do the dataset's labels relate to the CPCB formula applied to its own daily readings? (read-only)"""
import warnings

import mlflow.sklearn
import pandas as pd

from common import CLASSES, FEATURES, POLLUTANTS
from ingest import bucket, sub_index

warnings.filterwarnings("ignore")
IDX = {c: i for i, c in enumerate(CLASSES)}
d = pd.read_csv("data/interim/city_day.csv").dropna(subset=[*POLLUTANTS, "AQI", "AQI_Bucket"]).copy()
print(f"rows with ALL six readings + AQI + label: {len(d):,}")

sub = d[POLLUTANTS].apply(lambda col: col.map(lambda v, p=col.name: sub_index(p, v)))
d["f_aqi"], d["driver"] = sub.max(axis=1), sub.idxmax(axis=1)
fi, li = d["f_aqi"].map(bucket).map(IDX), d["AQI_Bucket"].map(IDX)
gap = d["AQI"] - d["f_aqi"]

print("\n1) Are the dataset's own columns consistent?")
print(f"   AQI_Bucket == bucket(AQI numeric): {(d['AQI'].map(bucket) == d['AQI_Bucket']).mean():.1%}")
print("\n2) Dataset AQI vs formula on the same daily readings")
print(f"   correlation = {d['AQI'].corr(d['f_aqi']):.3f} | mean(AQI - formula) = {gap.mean():+.1f} "
      f"| mean |diff| = {gap.abs().mean():.1f}")
print(f"   formula bucket LOWER than label : {(fi < li).mean():.1%}")
print(f"   formula bucket EQUAL            : {(fi == li).mean():.1%}")
print(f"   formula bucket HIGHER than label: {(fi > li).mean():.1%}")
print(f"   within ONE category             : {((fi - li).abs() <= 1).mean():.1%}")
print("\n3) Which pollutant drives the formula's maximum, and how far off is it then?")
print(pd.DataFrame({"share of rows": d["driver"].value_counts(normalize=True).round(3),
                    "mean(AQI - formula)": gap.groupby(d["driver"]).mean().round(1)}).to_string())

test = pd.read_csv("data/processed/test.csv")
test["month"] = test["month"].astype(float)
pred = mlflow.sklearn.load_model("models/airsense_model").predict(test[FEATURES])
print("\n4) The trained model on the TEST set")
exact, near = (pred == test["label"]).mean(), (abs(pred - test["label"]) <= 1).mean()
print(f"   exact accuracy = {exact:.1%} | within ONE category = {near:.1%}")
