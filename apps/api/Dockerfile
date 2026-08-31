FROM python:3.13-slim AS production

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --upgrade pip && pip install .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && alembic current && alembic heads && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM production AS development

RUN pip install -e ".[dev]"
COPY tests ./tests

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Render does not specify a build target, so the last stage is the deployed
# image. Keep local Compose on the explicit development target while making
# the Dockerfile default inherit the migration-gated production command.
FROM production AS runtime
