# Multi-stage optimized Dockerfile for PurpleInsight Central Services
FROM python:3.11-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
RUN pip install --no-cache-dir --prefix=/install psycopg2-binary fastapi uvicorn pyyaml pydantic sqlalchemy httpx requests

# Runner stage
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install runtime dependencies (libpq5 for PostgreSQL client, curl for Docker health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python packages
COPY --from=builder /install /usr/local

# Copy backend code files
COPY backend /app/backend

# Copy flat data files for database seeder
COPY data /app/data

# Expose API Service Port
EXPOSE 8000

# Create and run under secure non-root context
RUN groupadd -r purple && useradd --no-log-init -r -g purple purple && chown -R purple:purple /app
USER purple

# Start Uvicorn Server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
