# Puente

Sistema agéntico de inserción laboral juvenil para Panamá (nombre provisional).

<!-- Cambia el 0 por el número de su reto y deja la línea tal cual ("Reto: N"):
       1 = Agua · 2 = Educación · 3 = Empleabilidad
     No cambien de reto sin autorización de los organizadores. -->
Reto: 3

## Equipo

- Sebastian Olivera (@sebolive386)
- Jose Vasquez (@devoncats)
- Kenneth Zhong (@Xyryung)

## Problema

Los jóvenes no saben qué habilidades pide el mercado ni cómo traducir su experiencia informal; las empresas reciben postulaciones que no encajan y publican requisitos discriminatorios; los cursos de formación no llegan a quien los aprovecha; y nadie considera el tiempo y costo de traslado (Tocumen vs. La Chorrera). El desempleo juvenil (15–29) se estima en 19.9 % (sept. 2025).

Puente conecta a jóvenes, empresas y centros de formación con agentes que normalizan datos sucios, asignan con solvers deterministas bajo restricciones reales y auditan el sesgo, con un orientador humano aprobando las decisiones clave. Detalle en [docs/01-prd.md](docs/01-prd.md).

## Documentación

| Documento | Contenido |
|---|---|
| [01 · PRD](docs/01-prd.md) | Problema, actores, alcance, historias, matriz requisitos → producto |
| [02 · Requerimientos técnicos](docs/02-requerimientos-tecnicos.md) | Arquitectura, agentes, HITL, guardrails, evals, fuentes |
| [03 · App flow](docs/03-app-flow.md) | Diagrama de arquitectura, secuencias, flujos y pantallas |
| [04 · Design brief](docs/04-design-brief.md) | Principios, identidad visual, pantallas, guion del demo |
| [05 · Esquema del backend](docs/05-esquema-backend.md) | Modelo de datos y API |
| [06 · Plan de implementación](docs/06-plan-implementacion.md) | Bloques de 24 h, responsables, riesgos |
| [OpenAPI](packages/api-spec/openapi.yaml) | Contrato de la API (Scalar: `pnpm api:docs`) |

## Arquitectura de agentes

Seis agentes en el MVP orquestados por un supervisor LangGraph: Inteligencia de mercado, Perfil, Matching (OR-Tools CP-SAT), Ruta de formación (MIP), Postulación y Auditor de sesgo (contrafactuales). El orientador interviene en tres puntos: bloqueo de ofertas, lista corta y alertas de sesgo. Diagrama en [docs/03-app-flow.md](docs/03-app-flow.md).

## Tecnologías y fuentes de datos

Monorepo pnpm + Turborepo generado con [Better-T-Stack](https://better-t-stack.dev) (comando en `bts.jsonc`):

```
apps/web          Next.js + Tailwind + shadcn/ui
apps/api          FastAPI + LangGraph + OR-Tools (Python, uv)
packages/ui       componentes compartidos
packages/api-spec contrato OpenAPI 3.1 + Scalar
docs/             documentación del proyecto
```

LLM agnóstico vía LiteLLM. Fuentes: ofertas de portales públicos, cursos INADEH, taxonomía ESCO, corregimientos de Panamá, INEC/Mitradel. Ver [docs/02-requerimientos-tecnicos.md §8](docs/02-requerimientos-tecnicos.md).

## Instalación y ejecución

Requisitos: Node ≥ 22, pnpm 11, Python ≥ 3.12, uv.

```bash
cp .env.example .env
pnpm install
cd apps/api && uv sync && cd ../..
pnpm dev          # web :3001 · api :8000 (Scalar en /docs)
pnpm api:docs     # contrato OpenAPI en Scalar :4010
```

## Evals

Al menos 15 casos de prueba, métrica y resultados.

## Bitácora de IA

Qué partes se hicieron con IA, con qué herramienta y qué se modificó a mano.

- **Web H1 (layout, selector de rol, cliente tipado):** Claude Code (agente `kenneth-web`) generó `apps/web` (rutas por rol, `/datos`, cliente `openapi-fetch` desde el contrato, mocks tipados) y los tokens de color de `packages/ui`. Pendiente de revisión manual de Kenneth.
- **Agentes H3 (Postulación, HITL, /reviews, /match-runs):** Claude Code (agente `jose-agentes`) escribió los nodos matching, auditor (puerto), postulación y orientador con `interrupt`, el checkpointer y los endpoints, con tests. Pendiente de revisión manual de José.

---

Entrega: tag de git `final-24h` sobre el último commit válido, al cumplirse la hora 24.
