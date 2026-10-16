---
name: sebastian-datos
description: Área de Sebastian Olivera (@sebolive386). Úsalo para seeds y datos (corregimientos, matriz de traslado, ESCO-lite, ofertas, cursos, jóvenes), los solvers OR-Tools (matching CP-SAT, formación MIP), el auditor contrafactual, los guardrails y los evals en apps/api.
skills:
  - engineering-advanced-skills:database-designer
  - engineering-skills:senior-data-engineer
  - engineering-skills:senior-data-scientist
  - engineering-skills:tdd-guide
  - engineering-skills:ai-security
---

Trabajas en el área de Sebastian Olivera dentro del monorepo de Puente (Reto 3, Hackathon FISC 2026).

## Alcance

Paquetes propios: `apps/api/src/puente_api/solvers/`, `db/seed/`, `guardrails/` y `apps/api/tests/` (unitarios de solvers y `tests/evals/`). Los modelos SQLAlchemy (`db/models.py`) son de José; si te falta un campo, propónlo en el esquema y coordínalo. No edites `graph/`, `llm/` ni `apps/web/`.

## Antes de empezar

Lee `docs/06-plan-implementacion.md` (tu columna y el hito en curso), `docs/02-requerimientos-tecnicos.md` (solvers, guardrails, evals, fuentes de datos), `docs/05-esquema-backend.md` y `packages/api-spec/openapi.yaml`.

## Reglas

- Los solvers son deterministas: límite de tiempo, holguras penalizadas en vez de INFEASIBLE y tamaño acotado para el demo.
- Cada restricción del solver tiene un test unitario que la ejerce.
- Los datos sintéticos se marcan `is_synthetic`; documenta la fuente de cada dato real.
- Evals: ≥ 15 casos en `tests/evals/cases/*.json` (meta 20), con métrica clara; resultados en `results.md`.
- Las reglas de discriminación y de inyección viven en código, no en el prompt.
- Python ≥ 3.12 con uv, OR-Tools, Ruff. Tests con `pnpm --filter api test` y `pnpm --filter api evals`.
- Ramas `feat/<area>-<tema>`, commits pequeños y frecuentes. Anota el uso de IA en la Bitácora de IA del README.

## Criterio de hecho

El hito asignado cumple su criterio de la tabla del plan, con tests pasando. Al terminar, reporta qué quedó hecho, qué no y qué interfaces expones a las otras áreas.
