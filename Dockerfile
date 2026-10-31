# FINN on Hugging Face Spaces (Docker SDK) or any container host. One process serves the API and the web app.
# Secrets (GROQ_API_KEY, OPENROUTER_API_KEY, TAVILY_API_KEY) come from the host's secret settings, never the image.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FINN_DATA_MODE=live FINN_DB_PATH=/tmp/finn/finn.db FINN_TIMEZONE=Asia/Kolkata PORT=7860
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY design/prototype design/prototype
COPY data/.gitkeep data/.gitkeep
# Spaces run the container as user 1000: the data folder (portfolio edits) and /tmp must be writable.
RUN useradd -m -u 1000 finn && mkdir -p /tmp/finn && chown -R finn /app/data /tmp/finn
USER finn
WORKDIR /app/backend
EXPOSE 7860
CMD ["sh", "-c", "uvicorn finn.api:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
