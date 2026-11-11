"""AirSense - Streamlit UI. Talks to the backend ONLY through api_client (REST)."""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import ui_metrics
from api_client import ApiClient, ApiError, ApiUnavailable

st.set_page_config(page_title="AirSense - Air Quality Predictor", page_icon="🌫️", layout="wide")
ui_metrics.start_metrics_server()
api = ApiClient()

# (label, key, max, step, unit, help, placeholder)
READINGS = [
    ("PM2.5", "pm25", 1000.0, 1.0, "µg/m³", "Fine dust (smaller than 2.5 µm). The biggest driver of AQI.", "e.g. 85"),
    ("PM10", "pm10", 2000.0, 1.0, "µg/m³", "Coarse dust (smaller than 10 µm).", "e.g. 160"),
    ("NO2", "no2", 1000.0, 1.0, "µg/m³", "Nitrogen dioxide, mostly from vehicles.", "e.g. 45"),
    ("SO2", "so2", 2000.0, 1.0, "µg/m³", "Sulphur dioxide, from industry and power plants.", "e.g. 12"),
    ("CO", "co", 100.0, 0.1, "mg/m³", "Carbon monoxide. NOTE: milligrams, not micrograms.", "e.g. 1.2"),
    ("O3", "o3", 1000.0, 1.0, "µg/m³", "Ground-level ozone.", "e.g. 35"),
]
EXAMPLES = {
    "🌿 Clean-air day": {"city": "Bengaluru", "pm25": 12.0, "pm10": 28.0, "no2": 9.0, "so2": 4.0, "co": 0.3, "o3": 25.0},
    "🏙️ Typical metro day": {"city": "Mumbai", "pm25": 55.0, "pm10": 110.0, "no2": 38.0, "so2": 16.0, "co": 1.0, "o3": 35.0},
    "🌫️ Winter smog": {"city": "Delhi", "pm25": 260.0, "pm10": 420.0, "no2": 90.0, "so2": 20.0, "co": 3.5, "o3": 45.0},
}
LIGHT_BG = {"#92D050", "#FFC000"}  # colours that need dark text

st.markdown("""
<style>
.aq-card {border-radius: 16px; padding: 1.2rem 1.5rem; margin-bottom: .8rem;}
.aq-card h1 {margin: 0; font-size: 2.2rem;}
.aq-card p {margin: .3rem 0 0 0; font-size: 1.05rem;}
.block-container {padding-top: 2rem;}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------- helpers
@st.cache_data(ttl=300, show_spinner=False)
def load_cities(url: str) -> list:
    """Cities for the dropdown (cached 5 min per API URL)."""
    return ApiClient(url).cities()


def result_card(res: dict) -> None:
    """Colour-coded result banner, confidence, advice."""
    text = "#1b1b1b" if res["color"] in LIGHT_BG else "#ffffff"
    st.markdown(
        f"<div class='aq-card' style='background:{res['color']};color:{text}'>"
        f"<h1>{res['category']}</h1><p>{res['headline']} in {res['city']}</p></div>",
        unsafe_allow_html=True)
    pct = int(round(res["confidence"] * 100))
    st.progress(res["confidence"], text=f"Confidence: {pct}%")
    if res["low_confidence"]:
        st.warning("The model is not very sure about this one. Double-check your readings "
                   "or treat the result as approximate.")
    st.subheader("What this means for you")
    st.write(res["advice"])
    st.info(f"**Sensitive groups** (children, older adults, asthma/heart/lung conditions): "
            f"{res['sensitive_groups']}")
    if res["imputed_fields"]:
        st.caption("Readings you left blank were filled in with typical values for this city: "
                   + ", ".join(res["imputed_fields"]) + ".")
    with st.expander("How sure is the model about each category?"):
        probs = pd.Series(res["probabilities"], name="Probability")
        st.bar_chart(probs, horizontal=True)


def friendly_error(exc: Exception) -> None:
    """Show a plain-language error for API failures."""
    if isinstance(exc, ApiUnavailable):
        st.error("😕 The prediction service isn't responding. Please try again in a minute.")
    elif isinstance(exc, ApiError):
        st.error(exc.message)
        for d in exc.details:
            st.write(f"• **{d['field']}**: {d['message']}")
    else:
        st.error("Something unexpected happened. Please try again.")


def apply_example(name: str) -> None:
    """Callback: fill the form with an example scenario."""
    known = st.session_state.get("_cities", [])
    for k, v in EXAMPLES[name].items():
        if k == "city" and v not in known:  # model may not know this city; keep current one
            continue
        st.session_state[k] = v


# ------------------------------------------------------------------- pages
def page_predict() -> None:
    st.title("🌫️ Air Quality Predictor")
    st.write("Pick a city, type in the pollutant readings you have, and get the air-quality "
             "category with health advice. **You need at least 2 readings** - blanks are filled in "
             "automatically.")
    try:
        cities = load_cities(api.base_url)
        st.session_state["_cities"] = cities
    except (ApiUnavailable, ApiError) as exc:
        friendly_error(exc)
        return

    st.caption("Not sure what to enter? Try an example:")
    cols = st.columns(len(EXAMPLES))
    for col, name in zip(cols, EXAMPLES):
        col.button(name, on_click=apply_example, args=(name,), width="stretch")

    form, result = st.columns([1, 1], gap="large")
    with form:
        st.subheader("1. Where and when")
        city = st.selectbox("City", cities, key="city")
        day = st.date_input("Date (affects seasonal patterns)", value=date.today())
        st.subheader("2. Pollutant readings")
        payload = {"city": city, "date": day.isoformat()}
        c1, c2 = st.columns(2)
        for i, (label, key, mx, step, unit, hlp, ph) in enumerate(READINGS):
            payload[key] = (c1 if i % 2 == 0 else c2).number_input(
                f"{label} ({unit})", min_value=0.0, max_value=mx, value=None, step=step,
                key=key, help=hlp, placeholder=ph)
        given = sum(payload[r[1]] is not None for r in READINGS)
        go = st.button("Predict air quality", type="primary", width="stretch")

    with result:
        st.subheader("3. Result")
        if go:
            if given < 2:
                ui_metrics.PREDICT_CLICKS.labels("too_few_inputs").inc()
                st.warning(f"Please enter at least 2 readings (you entered {given}).")
            else:
                try:
                    with st.spinner("Analysing..."):
                        res = api.predict(payload)
                    ui_metrics.PREDICT_CLICKS.labels("ok").inc()
                    result_card(res)
                except (ApiUnavailable, ApiError) as exc:
                    ui_metrics.PREDICT_CLICKS.labels("error").inc()
                    friendly_error(exc)
        else:
            st.info("Your result will appear here.")


def page_batch() -> None:
    st.title("📄 Batch prediction")
    st.write("Have many readings? Upload a CSV and get a prediction for every row.")
    try:
        st.download_button("⬇️ Download CSV template", api.template_csv(), "airsense_template.csv",
                           "text/csv")
    except (ApiUnavailable, ApiError) as exc:
        friendly_error(exc)
        return
    st.caption("Columns: City, Date (optional), PM2.5, PM10, NO2, SO2, CO, O3. "
               "Blank readings are allowed (at least 2 per row). Max 5 MB.")
    up = st.file_uploader("Choose a CSV file", type=["csv"])
    if up is None:
        return
    content = up.getvalue()
    try:
        preview = pd.read_csv(pd.io.common.BytesIO(content))
    except Exception:  # noqa: BLE001
        ui_metrics.BATCH_UPLOADS.labels("unreadable").inc()
        st.error("That file couldn't be read as a CSV. Please use the template.")
        return
    st.write(f"Preview ({len(preview)} rows):")
    st.dataframe(preview.head(10), width="stretch")
    if st.button("Run predictions", type="primary"):
        try:
            with st.spinner("Predicting..."):
                out = api.predict_batch(up.name, content)
            ui_metrics.BATCH_UPLOADS.labels("ok").inc()
        except (ApiUnavailable, ApiError) as exc:
            ui_metrics.BATCH_UPLOADS.labels("error").inc()
            friendly_error(exc)
            return
        m1, m2, m3 = st.columns(3)
        m1.metric("Rows", out["total"])
        m2.metric("Predicted", out["succeeded"])
        m3.metric("Skipped (problems)", out["failed"])
        if out["results"]:
            df = pd.DataFrame(out["results"]).drop(columns=["low_confidence"], errors="ignore")
            colors = {r["category"]: r["color"] for r in out["results"]}
            show = df.drop(columns=["color", "imputed_fields"], errors="ignore")
            styled = show.style.map(
                lambda v: (f"background-color:{colors[v]};color:"
                           f"{'#1b1b1b' if colors[v] in LIGHT_BG else '#fff'}") if v in colors else "",
                subset=["category"])
            st.dataframe(styled, width="stretch", hide_index=True)
            st.bar_chart(show["category"].value_counts())
            st.download_button("⬇️ Download results", show.to_csv(index=False),
                               "airsense_results.csv", "text/csv")
        if out["errors"]:
            st.warning("Some rows were skipped. Fix them and re-upload:")
            st.dataframe(pd.DataFrame(out["errors"]).rename(columns={"row": "CSV row"}),
                         hide_index=True, width="stretch")


def dag_dot(dag: dict, latest: dict) -> str:
    """Graphviz DOT string; node colour reflects the last run status."""
    palette = {"success": "#2e7d32", "failed": "#c62828", None: "#9e9e9e"}
    lines = ["digraph {", "rankdir=LR;", 'node [shape=box, style="rounded,filled", fontcolor=white, fontname=Helvetica];']
    for n in dag["nodes"]:
        status = latest.get(n, {}).get("status")
        lines.append(f'"{n}" [fillcolor="{palette[status]}"];')
    lines += [f'"{a}" -> "{b}";' for a, b in dag["edges"]]
    return "\n".join(lines + ["}"])


def page_pipeline() -> None:
    st.title("⚙️ ML Pipeline Console")
    try:
        status, info = api.pipeline_status(), api.model_info()
    except (ApiUnavailable, ApiError) as exc:
        friendly_error(exc)
        return
    s = status["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pipeline runs logged", s["total"])
    c2.metric("Successful", s["success"])
    c3.metric("Failed", s["failed"])
    c4.metric("Model", info["model_name"])
    t_dag, t_runs, t_data, t_exp, t_model = st.tabs(
        ["Pipeline (DAG)", "Run console", "Data engineering", "Experiments", "Model"])

    with t_dag:
        st.caption("Green = last run succeeded, red = failed, grey = never run. Defined in dvc.yaml.")
        st.graphviz_chart(dag_dot(status["dag"], status["latest_by_stage"]))
        rows = [{"Stage": k, "Last status": v["status"], "Seconds": v["seconds"],
                 "Started (UTC)": v["started_at"][:19]} for k, v in status["latest_by_stage"].items()]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with t_runs:
        hist = status["history"]
        if not hist:
            st.info("No runs recorded yet. Run `dvc repro`.")
        else:
            hist_df = pd.DataFrame(hist)
            cols = [c for c in ["started_at", "stage", "status", "seconds", "error"] if c in hist_df]
            st.dataframe(hist_df[cols], hide_index=True, width="stretch")
            for rec in [h for h in hist if h["status"] == "failed"][:5]:
                with st.expander(f"❌ {rec['stage']} failed at {rec['started_at'][:19]}"):
                    st.code(rec.get("traceback") or rec.get("error", ""))

    with t_data:
        pm, dq = status.get("pipeline_metrics"), status.get("data_quality")
        if pm:
            a, b, c = st.columns(3)
            a.metric("Engine", pm["engine"])
            b.metric("Transform throughput", f"{pm['throughput_rows_per_sec_transform']:,.0f} rows/s")
            c.metric("End-to-end", f"{pm['throughput_rows_per_sec_end_to_end']:,.0f} rows/s")
            st.caption("Seconds per stage")
            st.bar_chart(pd.Series(pm["stage_seconds"]))
        if dq:
            st.caption(f"Data source: **{dq['source']}** · {dq['rows']:,} rows · {dq['cities']} cities")
            left, right = st.columns(2)
            left.write("Missing values (%) per pollutant")
            left.bar_chart(pd.Series(dq["null_pct"]))
            right.write("Rows per category")
            right.bar_chart(pd.Series(dq["class_counts"]))

    with t_exp:
        st.link_button("Open MLflow UI", status["links"]["mlflow"])
        st.link_button("Open Grafana dashboard", status["links"]["grafana"])
        runs = status["mlflow_runs"]
        if runs:
            st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
        else:
            st.info("MLflow runs are not reachable from the API right now.")

    with t_model:
        st.write(f"**Selected:** {info['model_name']} · **MLflow run:** `{info['mlflow_run_id']}` · "
                 f"**Git commit:** `{str(info['git_commit'])[:12]}` · **Trained:** {info['trained_at'][:19]}")
        tm = pd.Series({k: v for k, v in info["test_metrics"].items()
                        if k in ("accuracy", "macro_f1", "weighted_f1")})
        st.write("Held-out test metrics (later dates than training):")
        st.bar_chart(tm)
        st.write("Per-class recall:")
        st.bar_chart(pd.Series({k.replace("recall_", ""): v for k, v in info["test_metrics"].items()
                                if k.startswith("recall_")}))
        st.write("Validation macro-F1 per candidate (used for model selection):")
        st.bar_chart(pd.Series(info["candidate_val_macro_f1"]))
        if info.get("data_source") == "synthetic":
            st.warning("This model was trained on SYNTHETIC demo data. Put the real city_day.csv in data/raw/ "
                       "with the real dataset and run `dvc repro`.")


def page_help() -> None:
    st.markdown((Path(__file__).parent / "user_manual.md").read_text(encoding="utf-8"))


PAGES = {"🌫️ Predict": ("Predict", page_predict), "📄 Batch (CSV)": ("Batch", page_batch),
         "⚙️ Pipeline": ("Pipeline", page_pipeline), "❓ Help": ("Help", page_help)}

with st.sidebar:
    st.header("AirSense")
    choice = st.radio("Go to", list(PAGES), label_visibility="collapsed")
    try:
        if api.health()["model_loaded"]:
            st.success("Service online")
        else:
            st.warning("Model not loaded")
    except (ApiUnavailable, ApiError):
        st.error("Service offline")
    st.caption("Estimates for information only - not an official CPCB AQI reading.")

name, render = PAGES[choice]
ui_metrics.PAGE_VIEWS.labels(name).inc()
render()
