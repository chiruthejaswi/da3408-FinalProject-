"""Render docs/architecture_diagram.png (python make_diagram.py)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

fig, ax = plt.subplots(figsize=(15, 9))
ax.set_xlim(0, 150)
ax.set_ylim(0, 90)
ax.axis("off")


def box(x, y, w, h, text, color, fs=9):
    """Rounded labelled box."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5", fc=color, ec="#333", lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def arrow(a, b, label="", c="#333", ls="-", lx=None, ly=None):
    """Arrow with optional label."""
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="->", mutation_scale=14, color=c, lw=1.4, ls=ls))
    if label:
        ax.text(lx if lx is not None else (a[0] + b[0]) / 2, ly if ly is not None else (a[1] + b[1]) / 2 + 1.2,
                label, fontsize=7.5, ha="center", color=c, style="italic")


def zone(x, y, w, h, title, color):
    """Background group."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5,rounding_size=2", fc=color, ec="#999", lw=1, alpha=.35))
    ax.text(x + 1.5, y + h - 2.5, title, fontsize=10, fontweight="bold", color="#333")


ax.text(75, 87, "AirSense - Architecture (all components run locally via Docker Compose)",
        ha="center", fontsize=14, fontweight="bold")
zone(2, 50, 46, 34, "1  PRESENTATION  (container: frontend)", "#cfe3ff")
zone(54, 50, 46, 34, "2  SERVING  (container: backend)", "#d4f0d0")
zone(106, 50, 42, 34, "3  MONITORING", "#ffe7c2")
zone(2, 4, 100, 40, "4  TRAINING / DATA  (DVC pipeline, container: pipeline or local)", "#eadcf7")
zone(106, 4, 42, 40, "5  EXPERIMENT TRACKING", "#f9d6dc")
box(5, 66, 18, 10, "Streamlit UI\nPredict | Batch\nPipeline | Help", "#8ab8ff")
box(26, 66, 19, 10, "ApiClient (requests)\nAPI_URL env var\nerror mapping", "#8ab8ff")
box(5, 54, 18, 8, "UI metrics\n:8001 /metrics", "#8ab8ff", 8)
box(57, 68, 19, 9, "FastAPI routes\n/predict /predict/batch\n/health /model/info ...", "#8fd68a")
box(79, 68, 19, 9, "Validation (Pydantic)\nExceptions + Logging", "#8fd68a")
box(57, 54, 19, 9, "Predictor (OO)\nimpute -> features\n-> predict_proba", "#8fd68a")
box(79, 54, 19, 9, "HealthAdvisor\n(config JSON)\n+ Prometheus metrics", "#8fd68a")
box(109, 66, 17, 10, "Prometheus\nscrape 5 s\n+ alert rules", "#ffc66d")
box(129, 66, 17, 10, "Grafana\n16-panel dashboard\nrefresh 5 s", "#ffc66d")
ax.text(127, 58, "Metrics: requests, latency,\nerrors, predictions/class,\n"
        "confidence, input drift z-score,\nmodel info, UI->API calls",
        ha="center", fontsize=7.5)
box(6, 26, 16, 9, "data/raw\ncity_day.csv\n(DVC)", "#c9a6ec")
box(26, 26, 17, 9, "STAGE 1 ingest\nvalidate schema\n+ quality report", "#c9a6ec")
box(47, 26, 22, 9, "STAGE 2 preprocess\nRay Data map_batches\nimpute, clip, features, split", "#c9a6ec")
box(73, 26, 26, 9, "STAGE 3 train\nLogReg | RF | HistGB\nselect on VALIDATION slice", "#c9a6ec")
box(6, 8, 22, 9, "data/processed\ntrain.csv test.csv\nstats.json (DVC)", "#c9a6ec")
box(33, 8, 26, 9, "metrics/\nrun_history.jsonl, *.json\n(feeds Pipeline console)", "#c9a6ec")
box(64, 8, 35, 9, "models/airsense_model (MLflow format)\nmodel_meta.json (classes, cities, medians,\n"
    "train mean/std, run id, git commit)",
    "#c9a6ec", 8)
box(109, 28, 36, 12, "MLflow Tracking Server\nparams | metrics | tags\ngit_commit, dataset_md5, run_id", "#f4a6b3")
box(109, 10, 36, 12, "Artifacts\nconfusion matrix, feature importance,\nstats.json, logged model", "#f4a6b3")
arrow((23, 71), (26, 71))
arrow((45, 73), (57, 73), "REST / JSON (HTTP)", c="#0b5fd1", ly=74.5)
arrow((57, 70), (45, 70), c="#0b5fd1")
arrow((66, 68), (66, 63))
arrow((76, 72), (79, 72))
arrow((76, 58), (79, 58))
arrow((98, 60), (109, 69), "GET /metrics", c="#c06500", lx=104, ly=66.5)
arrow((23, 58), (109, 67), c="#c06500", ls="--")
arrow((126, 71), (129, 71))
arrow((127, 66), (127, 64))
arrow((22, 30.5), (26, 30.5))
arrow((43, 30.5), (47, 30.5))
arrow((69, 30.5), (73, 30.5))
arrow((58, 26), (20, 17), c="#555")
arrow((86, 26), (80, 17), "export", c="#555", lx=86, ly=21)
arrow((99, 33), (109, 34), "log", c="#a31a3a", lx=104, ly=35)
arrow((99, 28), (109, 16), c="#a31a3a")
arrow((72, 17), (68, 54), "model loaded at startup\n(read-only mount)", c="#2a7a22", ls="--", lx=60, ly=45)
arrow((109, 38), (93, 53.5), "backend reads runs via\n/pipeline/status", c="#a31a3a", ls=":", lx=108, ly=46.5)
ax.text(75, 1.3, "Loose coupling: Frontend <-> Backend only via REST (API_URL). Separate images, no shared code or volumes.",
        ha="center", fontsize=9, style="italic")
fig.savefig("docs/architecture_diagram.png", dpi=130, bbox_inches="tight")
print("saved")
