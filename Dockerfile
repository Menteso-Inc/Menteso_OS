FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/patentzoom_seo_agent/package.json agents/patentzoom_seo_agent/package-lock.json ./agents/patentzoom_seo_agent/
RUN cd agents/patentzoom_seo_agent && npm ci --include=dev && npm cache clean --force

COPY . .
RUN cd agents/patentzoom_seo_agent && npm run build && npm prune --omit=dev

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8010/login >/dev/null || exit 1

CMD ["python", "main.py", "dashboard"]
