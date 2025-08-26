# Backend Dockerfile for FastAPI app (production optimized)
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY share-recipe-frontend/backend/requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app code
COPY share-recipe-frontend/backend/app app
COPY share-recipe-frontend/backend/alembic alembic
COPY share-recipe-frontend/backend/alembic.ini alembic.ini

# Expose default port (Railway may override via PORT env)
EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Entrypoint - run migrations then start uvicorn on provided PORT (fallback 8000)
CMD ["sh", "-c", "alembic upgrade head || exit 1; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]
