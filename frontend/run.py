"""Container entrypoint: expose Prometheus metrics from process start, then run Streamlit.

Streamlit only executes app.py when a browser connects, so starting the metrics
server there would leave Prometheus scraping a dead port until the first visitor.
Streamlit runs in this same process, so app.py shares the counters defined in ui_metrics.
"""
import os
import sys

import ui_metrics
from streamlit.web import cli as stcli

if __name__ == "__main__":
    ui_metrics.start_metrics_server()
    sys.argv = ["streamlit", "run", "app.py", f"--server.port={os.getenv('UI_PORT', '8501')}",
                "--server.address=0.0.0.0", "--server.headless=true"]
    sys.exit(stcli.main())
