# Build the frontend once; Node is not needed in the running container.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM denoland/deno:bin-2.9.8 AS deno

# Debian trixie includes ffmpeg 7+, meeting the audio engine's requirement.
FROM python:3.12-slim-trixie AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEDDING_MIX_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app/ ./backend/app/
RUN pip install --no-cache-dir ./backend \
    && groupadd --gid 10001 mix \
    && useradd --uid 10001 --gid mix --create-home mix \
    && mkdir -p /data \
    && chown mix:mix /data
COPY --from=frontend-build /build/backend/static/ ./backend/static/

# Run from source so settings resolve the static directory relative to /app.
WORKDIR /app/backend
USER mix
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import json,sys,urllib.request; sys.exit(not json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/system/check', timeout=8))['ready'])"]

# Listen on the container interface; Compose publishes only on host loopback.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
