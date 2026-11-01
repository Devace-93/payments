# accounts API service image (also used for the `worker` and `migrate` services).
# Build context is the REPO ROOT (see deploy/docker-compose.yml:
#   build: { context: .., dockerfile: services/api/Dockerfile }).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY services/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared core + shared config, then the API package itself.
# The package must live at /app/api so `api.app:create_app` is importable.
COPY dbcore /app/dbcore
COPY packages/shared /app/packages/shared
COPY services/api/api /app/api
# Alembic migrations (run by the `migrate` compose service via dbcore.cli).
COPY db /app/db

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "api.app:create_app()"]
