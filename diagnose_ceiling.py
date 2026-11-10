"""Is 'six pollutants only' the ceiling? Same model, with and without the extra pollutant columns in the Kaggle file.

The extra columns are used ONLY here, to explain the ceiling. The app still takes six inputs.
(The numeric 'AQI' column is deliberately excluded: it is the label in disguise.)
"""
import warnings

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, recall_score

from common import FEATURES

warnings.filterwarnings("ignore")
train = pd.read_csv("data/processed/train.csv")
test = pd.read_csv("data/processed/test.csv")
EXTRA = [c for c in ["NO", "NOx", "NH3", "Benzene", "Toluene", "Xylene"] if c in train.columns]
if not EXTRA:
    raise SystemExit("No extra pollutant columns in this dataset (synthetic data?) - nothing to compare.")
for df in (train, test):
    df["month"] = df["month"].astype(float)


def run(cols, name):
    """Fit HistGradientBoosting (handles NaN natively) and report test metrics."""
    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_depth=8, random_state=42)
    model.fit(train[cols], train["label"])
    pred = model.predict(test[cols])
    rec = recall_score(test["label"], pred, labels=range(6), average=None, zero_division=0)
    f1 = f1_score(test["label"], pred, average="macro", labels=range(6), zero_division=0)
    print(f"{name:42s} macro-F1={f1:.4f}  accuracy={accuracy_score(test['label'], pred):.4f}  min recall={rec.min():.3f}")


print("extra columns found:", EXTRA)
print("% missing in TRAIN :", {c: round(float(train[c].isna().mean() * 100), 1) for c in EXTRA}, "\n")
run(FEATURES, "six pollutants + engineered (what the app uses)")
for c in EXTRA:
    run(FEATURES + [c], f"  + {c} only")
run(FEATURES + EXTRA, "  + ALL extra columns")
