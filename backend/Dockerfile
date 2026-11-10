# Build context = repository root (backend needs src/common for shared feature code).
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend-requirements.txt
RUN pip install --no-cache-dir -r backend-requirements.txt
COPY backend/ backend/
COPY common.py common.py
ENV PYTHONUNBUFFERED=1 MODEL_DIR=/app/models/airsense_model META_PATH=/app/models/model_meta.json \
    METRICS_DIR=/app/metrics DVC_YAML=/app/dvc.yaml LOG_DIR=/app/logs
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=2)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
