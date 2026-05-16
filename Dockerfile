FROM python:3.13-slim AS base

# Minimal system deps (gcc only needed if a wheel is missing; included for safety)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Install Python dependencies first so layer caches well
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e . || true

# Project source
COPY backend ./backend
COPY dashboard ./dashboard
COPY scripts ./scripts
COPY _extracted ./_extracted
COPY chroma_db ./chroma_db

# Now finalize editable install with the actual package present
RUN pip install -e .

# Non-root user
RUN useradd --create-home --shell /bin/bash sentinel && chown -R sentinel:sentinel /app
USER sentinel

EXPOSE 8000

# Audit log lives in /tmp on Render free tier (no persistent disk).
ENV SQLITE_PATH=/tmp/audit.db

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
