FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MOODYAI_ENV=production \
    MOODYAI_HOST=0.0.0.0 \
    MOODYAI_FORWARDED_ALLOW_IPS=*

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /var/data/backups \
    && useradd --create-home --uid 10001 moodyai \
    && chown -R moodyai:moodyai /app /var/data

USER moodyai

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl --fail http://127.0.0.1:${PORT:-10000}/ready || exit 1

CMD ["python", "run_production.py"]
