FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/tutorflow-venv \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
RUN uv sync --locked --no-dev --no-editable

ENV PATH="/opt/tutorflow-venv/bin:$PATH"
ARG TUTORFLOW_GIT_SHA=unknown
ENV TUTORFLOW_GIT_SHA=${TUTORFLOW_GIT_SHA}

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
