# API de Puente: FastAPI + LangGraph + OR-Tools. Contexto de build: apps/api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Misma versión de uv con la que se generó uv.lock.
RUN pip install --no-cache-dir "uv==0.12.17"

WORKDIR /app
# 1) Solo dependencias: esta capa se reutiliza mientras no cambie uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# 2) Código del proyecto.
COPY src ./src
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

EXPOSE 8000
# Siembra idempotente («Seeds ya cargados» si ya existen) y luego la API.
CMD ["sh", "-c", "python -m puente_api.db.seed && exec uvicorn puente_api.main:app --host 0.0.0.0 --port 8000"]
