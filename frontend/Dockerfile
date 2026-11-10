# Build context = ./frontend only: the UI cannot import backend code (loose coupling).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 API_URL=http://backend:8000 UI_METRICS_PORT=8001
EXPOSE 8501 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8501/_stcore/health', timeout=2)"
CMD ["python", "run.py"]
