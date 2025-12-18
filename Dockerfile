# === БАЗОВЫЙ ОБРАЗ ===
FROM python:3.11.11-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# === BUILDER ===
FROM base as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# === DEVELOPMENT ===
FROM base as development

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# === PRODUCTION ===
FROM base as production

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appuser /app/staticfiles /app/media /app/logs

RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

RUN python manage.py collectstatic --noinput || true

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health/', timeout=5)" || exit 1

EXPOSE 8000