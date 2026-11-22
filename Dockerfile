# CodeMind — Production Dockerfile
# Lightweight Python 3.12-slim container with non-root security

FROM python:3.12-slim as runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0 \
    CODEMIND_EMBEDDING_PROVIDER=mock

WORKDIR /app

# Install minimal OS dependencies for git mining and curl healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source code and packaging configs
COPY codemind/ ./codemind/
COPY pyproject.toml README.md ./

# Install package in standard mode
RUN pip install --no-cache-dir -e .

# Create non-root user for security hardening
RUN groupadd -r codemind && useradd -r -g codemind -d /app -s /bin/bash codemind \
    && chown -R codemind:codemind /app

USER codemind

# Expose web application port
EXPOSE 8000

# Healthcheck verifying FastAPI server responsiveness
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/graph || exit 1

# Launch FastAPI web application with strictly single-worker process model (--workers 1)
# NOTE: CodeMind uses process-local in-memory state and synchronization; do not increase worker processes.
CMD ["uvicorn", "codemind.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
