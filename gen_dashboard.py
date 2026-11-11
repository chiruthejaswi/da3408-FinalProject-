"""Generate grafana/dashboards/airsense.json (python gen_dashboard.py)."""
import json

DS = {"type": "prometheus", "uid": "prometheus"}
_id = [0]


def panel(title, exprs, kind="timeseries", x=0, y=0, w=8, h=7, unit="short", legend=None, neutral=False):
    """One Grafana panel with one or more PromQL targets.

    neutral=True shows a stat in a fixed blue instead of Grafana's default red-above-80 threshold colouring,
    which would make a plain count (e.g. predictions served) look like an alarm.
    """
    _id[0] += 1
    defaults = {"unit": unit}
    if neutral:
        defaults["color"] = {"mode": "fixed", "fixedColor": "blue"}
    return {"id": _id[0], "title": title, "type": kind, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"expr": e, "legendFormat": (legend[i] if legend else ""), "refId": chr(65 + i),
                         "datasource": DS} for i, e in enumerate(exprs)],
            "fieldConfig": {"defaults": defaults, "overrides": []}}


LAT = 'histogram_quantile({q}, sum(rate(airsense_http_request_seconds_bucket{{path="/predict"}}[1m])) by (le))'
panels = [
    panel("Model loaded", ["airsense_model_loaded"], "stat", 0, 0, 4, 5),
    panel("Requests / sec (backend)", ["sum(rate(airsense_http_requests_total[1m]))"], "stat", 4, 0, 5, 5, "reqps",
          neutral=True),
    panel("Error rate (4xx+5xx share)",
          ['(sum(rate(airsense_http_requests_total{status=~"4..|5.."}[1m])) or vector(0)) / '
           'clamp_min(sum(rate(airsense_http_requests_total[1m])),0.001)'], "stat", 9, 0, 5, 5, "percentunit"),
    panel("p95 /predict latency", [LAT.format(q=0.95)], "stat", 14, 0, 5, 5, "s"),
    panel("Predictions served", ["sum(airsense_predictions_total)"], "stat", 19, 0, 5, 5, neutral=True),
    panel("Request rate by endpoint", ["sum(rate(airsense_http_requests_total[1m])) by (path)"],
          "timeseries", 0, 5, 12, 8, "reqps", ["{{path}}"]),
    panel("Latency p50 / p95 / p99 (/predict)", [LAT.format(q=q) for q in (0.5, 0.95, 0.99)],
          "timeseries", 12, 5, 12, 8, "s", ["p50", "p95", "p99"]),
    panel("Predictions by category", ["sum(increase(airsense_predictions_total[5m])) by (category)"],
          "barchart", 0, 13, 8, 8, "short", ["{{category}}"]),
    panel("Prediction confidence (avg)",
          ["rate(airsense_prediction_confidence_sum[1m]) / clamp_min(rate(airsense_prediction_confidence_count[1m]),0.001)"],
          "timeseries", 8, 13, 8, 8, "percentunit", ["avg confidence"]),
    panel("Errors by type", ["sum(increase(airsense_errors_total[5m])) by (type)"],
          "timeseries", 16, 13, 8, 8, "short", ["{{type}}"]),
    panel("DATA DRIFT: z-score of recent inputs vs training", ["airsense_input_drift_zscore"],
          "timeseries", 0, 21, 12, 8, "short", ["{{feature}}"]),
    panel("Median PM2.5 input (live)",
          ['histogram_quantile(0.5, sum(rate(airsense_input_value_bucket{feature="PM2.5"}[5m])) by (le))'],
          "timeseries", 12, 21, 12, 8, "short", ["PM2.5 median"]),
    panel("Batch rows (ok vs failed)", ["sum(increase(airsense_batch_rows_total[5m])) by (outcome)"],
          "timeseries", 0, 29, 8, 7, "short", ["{{outcome}}"]),
    panel("UI page views", ["sum(increase(airsense_ui_page_views_total[5m])) by (page)"],
          "timeseries", 8, 29, 8, 7, "short", ["{{page}}"]),
    panel("UI -> API calls by outcome", ["sum(increase(airsense_ui_api_calls_total[5m])) by (outcome)"],
          "timeseries", 16, 29, 8, 7, "short", ["{{outcome}}"]),
    panel("Scrape targets up", ["up"], "stat", 0, 36, 24, 4, "short", ["{{job}}"]),
]
dash = {"uid": "airsense-main", "title": "AirSense - Live Monitoring", "tags": ["airsense"], "timezone": "browser",
        "refresh": "5s", "time": {"from": "now-15m", "to": "now"}, "schemaVersion": 39, "version": 1,
        "panels": panels}
with open("grafana/dashboards/airsense.json", "w", encoding="utf-8") as fh:
    json.dump(dash, fh, indent=1)
print("wrote grafana/dashboards/airsense.json with", len(panels), "panels")
