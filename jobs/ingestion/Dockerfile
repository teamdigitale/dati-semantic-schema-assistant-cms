FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

LABEL org.opencontainers.image.title="Schema Assistant ingestion"

COPY pyproject.toml uv.lock ./
COPY config ./config
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable --extra ingestion

CMD ["python", "-m", "schema_assistant.ingestion"]
