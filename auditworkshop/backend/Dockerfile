FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev gcc poppler-utils tesseract-ocr tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --retries/--timeout: robust gegen instabile Verbindung (NUC/Wohnwagen).
RUN pip install --no-cache-dir --retries 10 --timeout 300 -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

# Entrypoint wendet zuerst Alembic-Migrationen an (alembic upgrade head bzw.
# stamp head bei bestehenden, noch nicht versionierten DBs) und startet dann
# uvicorn. Siehe entrypoint.sh.
ENTRYPOINT ["/app/entrypoint.sh"]
