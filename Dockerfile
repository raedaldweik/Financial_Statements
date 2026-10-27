# Investor Financial Intelligence - single-container deploy (FastAPI + static frontend).
# poppler-utils provides pdftotext / pdfseparate / pdfunite used by the ingestion pipeline.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/  /app/backend/
COPY frontend/ /app/frontend/
COPY filings/  /app/filings/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    STORAGE_DIR=/app/storage

# Uploaded filings live in /app/storage. On Railway, mount a volume there (Settings > Volumes)
# so uploads survive redeploys; Railway rejects the Dockerfile VOLUME instruction, so none here.
RUN mkdir -p /app/storage

WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
