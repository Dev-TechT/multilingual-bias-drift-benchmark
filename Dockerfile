# Multilingual Bias Drift Benchmark — web app image
# Build:  docker build -t mbdb:0.3.0 .
# Run:    docker run --rm -p 127.0.0.1:8000:8000 -v mbdb-data:/data mbdb:0.3.0
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MBDB_DATA_DIR=/data \
    MBDB_DATASETS_DIR=/app/examples \
    MBDB_DEMO_DELAY_SECONDS=0.15 \
    MBDB_HOST=0.0.0.0 \
    MBDB_PORT=8000

WORKDIR /app
# Only public sample/dev data is copied; private holdout data must never be baked into an image (DATA_TIERS.md).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[web]"
COPY examples ./examples

RUN useradd --create-home --uid 10001 mbdb && mkdir -p /data && chown mbdb:mbdb /data
USER mbdb
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["sh", "-c", "uvicorn fillblank_web.app:app --host ${MBDB_HOST} --port ${MBDB_PORT} --proxy-headers --forwarded-allow-ips='*'"]
