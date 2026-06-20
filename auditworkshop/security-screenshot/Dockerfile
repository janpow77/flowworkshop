# Playwright-Basis-Image mit vorinstalliertem Chromium + Systemabhängigkeiten.
# Die Image-Tag-Version muss zur playwright-Version in requirements.txt passen.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

# Verknüpft das GHCR-Paket mit dem Repo (Actions-Schreibzugriff via source-Label).
LABEL org.opencontainers.image.source="https://github.com/janpow77/flowworkshop"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --retries 10 --timeout 300 -r requirements.txt

COPY server.py .

# Kein externes Port-Mapping: nur intern im Compose-Netz erreichbar.
EXPOSE 8090

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
