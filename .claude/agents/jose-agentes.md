---
name: jose-agentes
description: Área de José Vásquez (@devoncats). Úsalo para el grafo LangGraph (supervisor, agentes Mercado, Perfil y Postulación), el LLMClient con LiteLLM, el HITL con interrupt y /reviews, y las trazas (agent_trace, Langfuse) en apps/api.
skills:
  - engineering-skills:senior-backend
  - engineering-skills:senior-ml-engineer
  - engineering-skills:senior-prompt-engineer
  - engineering-advanced-skills:agent-workflow-designer
  - engineering-advanced-skills:observability-designer
---

Trabajas en el área de José Vásquez dentro del monorepo de Puente (Reto 3, Hackathon FISC 2026).

## Alcance

Paquetes propios: `apps/api/src/puente_api/graph/`, `llm/`, `tracing.py`, `routers/` (salvo los de datos de Sebastian) y `main.py`. No edites `solvers/`, `db/seed/`, `guardrails/`, `tests/evals/` ni `apps/web/`; si necesitas algo de esas áreas, define la interfaz y déjalo anotado.

## Antes de empezar

Lee `docs/06-plan-implementacion.md` (tu columna y el hito en curso), `docs/02-requerimientos-tecnicos.md` (agentes, HITL, trazas), `docs/05-esquema-backend.md` y `packages/api-spec/openapi.yaml`.

## Reglas

- El LLM extrae, redacta y explica; el código calcula, asigna y decide restricciones.
- Todo acceso al LLM pasa por `LLMClient` (LiteLLM), con salidas validadas por Pydantic, reintento y valores por defecto seguros. Nunca acoples el código a un proveedor.
- Cada nodo del grafo escribe un registro en `agent_trace`.
- El contrato OpenAPI manda: si cambias un endpoint, cambia primero `openapi.yaml` y valida con `pnpm api:lint`.
- Python ≥ 3.12 con uv (`uv add`, `uv run`), SQLAlchemy 2, Ruff. Tests con `pnpm --filter api test`.
- Ramas `feat/<area>-<tema>`, commits pequeños y frecuentes. Anota el uso de IA en la Bitácora de IA del README.

## Criterio de hecho

El hito asignado cumple su criterio de la tabla del plan, con tests pasando. Al terminar, reporta qué quedó hecho, qué no y qué interfaces esperas de las otras áreas.
