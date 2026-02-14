# ─── Stage 1: Builder (Compilation) ────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build-time dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    # Preinstall CPU-only torch wheels so downstream deps do not pull CUDA packages.
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt


# ─── Stage 2: Runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies only (no build-essential)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        poppler-utils \
        tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN useradd -m -u 1000 -s /sbin/nologin vancity && \
    mkdir -p /app && \
    chown -R vancity:vancity /app

# Copy application code
COPY --chown=vancity:vancity api/ ./api/
COPY --chown=vancity:vancity db/ ./db/
COPY --chown=vancity:vancity sdk/ ./sdk/

# Health check using Python (no curl/wget needed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').close()" || exit 1

# Switch to non-root user
USER vancity

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
