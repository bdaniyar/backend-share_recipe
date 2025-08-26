# Backend Dockerfile for FastAPI app (production optimized)
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app code
COPY app app
COPY alembic alembic
COPY alembic.ini alembic.ini

# Expose default port (Railway may override via PORT env)
EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Entrypoint - run migrations then start uvicorn on provided PORT (fallback 8000)
CMD ["sh", "-c", "alembic upgrade head || exit 1; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]

# --- Optional for development ---
# To include development dependencies, uncomment the following:
# COPY requirements-dev.txt requirements-dev.txt
# RUN pip install -r requirements-dev.txt
