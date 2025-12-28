FROM python:3.11-slim

RUN adduser --disabled-password --gecos "" appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY README.md /app/README.md

ARG VERSION=dev
ARG VCS_REF=dev
ENV VERSION=$VERSION
ENV VCS_REF=$VCS_REF

ENV PORT=8000
EXPOSE 8000
VOLUME ["/data"]

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS -H "X-API-Key: ${API_KEY}" http://localhost:${PORT:-8000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
