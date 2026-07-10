FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev gcc poppler-utils tesseract-ocr tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip==26.1.2 setuptools==83.0.0
# sentence-transformers otherwise resolves the multi-gigabyte CUDA build of
# torch although this service runs on a CPU-only Hetzner host. The production
# embedding path uses the external gateway; the CPU wheel preserves the local
# fallback without shipping CUDA runtimes.
RUN pip install --no-cache-dir --retries 10 --timeout 300 \
    --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
# --retries/--timeout: robust gegen instabile Verbindung (NUC/Wohnwagen).
RUN pip install --no-cache-dir --retries 10 --timeout 300 -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

# Entrypoint wendet zuerst Alembic-Migrationen an (alembic upgrade head bzw.
# stamp head bei bestehenden, noch nicht versionierten DBs) und startet dann
# uvicorn. Siehe entrypoint.sh.
ENTRYPOINT ["/app/entrypoint.sh"]
