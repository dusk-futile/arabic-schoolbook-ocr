FROM node:22-bookworm-slim AS web-build
WORKDIR /build/web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JOB_ROOT=/data/jobs \
    TRAINING_APPROVED=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-core \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libreoffice-writer \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN python -m pip install --upgrade pip && python -m pip install ".[local]"

COPY scripts/ ./scripts/
COPY --from=web-build /build/web/dist ./web/dist

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/jobs \
    && chown -R appuser:appuser /app /data/jobs
USER appuser

EXPOSE 8000
VOLUME ["/data/jobs"]
CMD ["python", "-m", "uvicorn", "arabic_schoolbook_ocr.api:app", "--host", "0.0.0.0", "--port", "8000"]
