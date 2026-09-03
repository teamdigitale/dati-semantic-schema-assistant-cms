FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY config ./config
COPY src ./src

# Install only the agent runtime extras; ingestion dependencies live in the job image.
RUN uv sync --frozen --no-dev --no-editable --extra agent

EXPOSE 8080

CMD ["python", "-m", "schema_assistant.agent"]
