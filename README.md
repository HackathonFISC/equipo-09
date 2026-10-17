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
| [07 · Metodología](docs/07-metodologia.md) | Despliegue, funcionamiento, arquitectura y límites conocidos |
| [08 · Ensayos](docs/08-ensayos.md) | Bitácora de ensayos del demo y checklist de grabación |
| [09 · Datos del demo](docs/09-datos-demo.md) | Entradas exactas del demo, resultados en producción e ids |
| [Docs internas](apps/docs/content/docs) | Guía del equipo con Fumadocs: agentes, LLM, solvers, runbooks (`pnpm docs:dev` → :3002) |
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
cp .env.example .env              # completa LLM_MODEL y LLM_API_KEY (ver abajo)
pnpm install
cd apps/api && uv sync
uv run python -m puente_api.db.seed      # carga los datos semilla (idempotente)
uv run python scripts/check_llm.py       # comprueba que el LLM responde
cd ../..
pnpm dev          # web :3001 · api :8000 (Scalar en /docs)
pnpm api:docs     # contrato OpenAPI en Scalar :4010
```

Sin el paso de semillas la API arranca con la base vacía.

### Credenciales del demo (`.env`)

- `LLM_MODEL` / `LLM_MODEL_FAST`: el prefijo elige el proveedor (`anthropic/…`, `openai/…`, `gemini/…`, `ollama/…`).
- `LLM_API_KEY`: clave del proveedor de `LLM_MODEL` (solo se usa con ese proveedor). Para un respaldo (`LLM_FALLBACK_MODEL`) de otro proveedor, define en el mismo `.env` su variable estándar (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`…): la API la exporta al entorno para LiteLLM sin pisar una ya definida.
- Si el LLM no responde, los agentes siguen con valores por defecto seguros y la traza lo dice («se usó el valor por defecto seguro»). `scripts/check_llm.py` lo detecta antes del demo.
- `LLM_CACHE_DIR=.llm-cache` guarda las respuestas válidas: la misma entrada se repite sin red (útil para ensayos y evals).
- La web lee su configuración de `apps/web/.env.local`, no del `.env` de la raíz. Para el demo crea ese archivo con `NEXT_PUBLIC_API_MOCKS=nunca`: así un fallo de la API se ve como error y no como datos de ejemplo (`auto`, el valor por defecto, los muestra si la API no responde).

Nunca subas claves reales: `.env` está en `.gitignore`.

### Docker Compose

```bash
cp .env.example .env              # con tu clave de LLM
docker compose up --build         # postgres + api (siembra al arrancar) + web
```

Web en http://localhost:3001 y API en http://localhost:8000/docs. La API usa PostgreSQL y guarda en el volumen `apidata` los checkpoints del grafo (las pausas del orientador sobreviven a un reinicio) y la caché del LLM. Para empezar de cero: `docker compose down -v`.

### Prueba de humo del demo

Con la API corriendo (local o Docker):

```bash
cd apps/api && uv run python scripts/smoke_demo.py            # añade --strict-llm para exigir LLM
```

Recorre el guion por la API (oferta bloqueada, entrevista, inyección bloqueada, matching con pausa, aprobación con entrevistas agendadas, ruta de formación, trazas) e imprime OK/FALLA por paso. Crea datos nuevos: úsala sobre una base de ensayo.

### Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La traza dice «se usó el valor por defecto seguro» | LLM sin clave, modelo mal escrito o proveedor caído | `uv run python scripts/check_llm.py` y revisa `.env` |
| La web muestra «Datos de ejemplo» | La API no responde en `NEXT_PUBLIC_API_URL` | Levanta la API, o pon `NEXT_PUBLIC_API_MOCKS=nunca` en `apps/web/.env.local` para ver el error real |
| Listados vacíos | Faltan las semillas | `uv run python -m puente_api.db.seed` |
| Reiniciar los datos del demo | — | Detén la API, borra `apps/api/puente.db*` y `apps/api/puente-checkpoints.sqlite*`, vuelve a sembrar |

## Evals

28 casos deterministas (sin LLM ni red) en `apps/api/tests/evals/cases/` más las métricas de éxito del PRD medidas sobre los datos semilla. Resultados completos y método en [apps/api/tests/evals/results.md](apps/api/tests/evals/results.md).

| Métrica (PRD §8) | Meta | Resultado |
|---|---|---|
| Matches que violan restricciones duras (preset estricto) | 0 | 0 (el seed da 1 asignación con el preset estricto) |
| Paridad contrafactual (nombre, género, corregimiento) | ≥ 95 % | 100 % en las tres (40 jóvenes, 3 con asignación) |
| Detección de ofertas discriminatorias (recall, 25 ofertas etiquetadas) | ≥ 90 % | 100 % (6/6) |
| Entradas maliciosas bloqueadas o neutralizadas | 100 % | 100 % (8/8) |
| Extracción de habilidades con LLM (F1) | ≥ 0.80 | no medido (ver `tests/evals/llm_extraction.py`) |
| Casos de eval que pasan | ≥ 15 | 28/28 |

```bash
pnpm --filter api evals                              # los 28 casos
cd apps/api && uv run python -m tests.evals.report   # regenera results.md
cd apps/api && uv run python -m tests.evals.llm_extraction   # F1 con el LLM real (escribe results-llm.md)
```

El preset del demo (`relaxed`) tolera hasta 15 min, B/. 1.00 y 1 habilidad obligatoria de exceso, penalizados y visibles para el orientador; en los datos semilla 2 de 3 asignaciones usan esa holgura (detalle en `results.md`).

## Bitácora de IA

Qué partes se hicieron con IA, con qué herramienta y qué se modificó a mano. Reconstruida con el historial de git y los PR de GitHub: solo se anota lo que consta ahí, en `.claude/agents/` o en entradas anteriores. «Revisión manual: no consta» significa que el PR no tiene revisiones registradas en GitHub ni hay commits posteriores que la documenten; no afirma que no se haya mirado el código.

Hechos comunes a H1–H4: todo el trabajo se hizo en ramas `claude/…` creadas por Claude Code y con commits bajo la identidad git de @devoncats. Los PR [#1](https://github.com/HackathonFISC/equipo-09/pull/1) a [#6](https://github.com/HackathonFISC/equipo-09/pull/6) los abrió y fusionó @devoncats el 2026-10-16, sin revisiones registradas en GitHub. Los subagentes por integrante (`.claude/agents/jose-agentes.md`, `kenneth-web.md`, `sebastian-datos.md`) se agregaron en `00035da`, dentro del PR #3; el historial no registra qué subagente produjo cada commit salvo donde la entrada lo dice.

- **Documentación H0 (`docs/01`–`06`, monorepo, contrato OpenAPI):** Claude Code, antes de que existieran los subagentes, generó el monorepo con Better-T-Stack, el stub de FastAPI, el contrato `packages/api-spec/openapi.yaml` con Scalar y los seis documentos de `docs/` (PR #1, rama `claude/plan-3-project-definition-677a24`). Revisión manual: no consta.
- **Agentes H1 (modelos, catálogo, LLMClient):** Claude Code (subagente: no consta) escribió los modelos SQLAlchemy 2, los endpoints `GET /locations`, `/skills`, `/postings` y el `LLMClient` sobre LiteLLM con salida Pydantic, reintento y respaldo (PR #3). Revisión manual: no consta.
- **Datos H1 (seeds):** Claude Code (subagente: no consta) generó los datos semilla (50 corregimientos, matriz de traslado de 2500 pares, 150 habilidades ESCO-lite, 15 empresas, 25 ofertas con 25 etiquetas de discriminación, 4 centros, 12 cursos, 40 jóvenes), sus cargadores y tests de integridad (`d17f2b2`, PR #3). Revisión manual: no consta.
- **Web H1 (layout, selector de rol, cliente tipado):** Claude Code (agente `kenneth-web`) generó `apps/web` (rutas por rol, `/datos`, cliente `openapi-fetch` desde el contrato, mocks tipados) y los tokens de color de `packages/ui` (PR #2). Revisión manual: no consta.
- **Agentes H2 (supervisor, Mercado, Perfil):** Claude Code (subagente: no consta) escribió el supervisor LangGraph, los agentes Mercado y Perfil, el registro `agent_trace`, `ingestPosting`, los endpoints de CV y entrevista y tests de punta a punta con LLM simulado (rama `feat/agentes-h2-mercado-perfil`, PR #4). Revisión manual: no consta.
- **Datos H2 (solver de matching):** Claude Code (subagente: no consta) escribió el solver CP-SAT con holguras penalizadas, su adaptador de datos y un test por restricción (rama `feat/datos-matching-solver`, PR #4). Revisión manual: no consta.
- **Web H2 (ingesta y perfil):** Claude Code (subagente: no consta) generó la ingesta de oferta en `/empresa`, el registro, CV y entrevista guiada del joven y un arreglo de la URL pública de la API (rama `feat/web-h2-ingesta-perfil`, PR #4). Revisión manual: no consta.
- **Datos H3 (auditor, formación, reglas de discriminación):** Claude Code (subagente: no consta) escribió las reglas de discriminación en código con un test por regla, el auditor contrafactual (nombre, género, corregimiento) con auditoría de ofertas y el solver MIP de ruta de formación con respaldo greedy (rama `feat/datos-h3-auditor-formacion`, PR #5). Revisión manual: no consta.
- **Agentes H3 (Postulación, HITL, /reviews, /match-runs):** Claude Code (agente `jose-agentes`) escribió los nodos matching, auditor (puerto), postulación y orientador con `interrupt`, el checkpointer y los endpoints, con tests (PR #5). En la integración se conectó el auditor real al puerto y se alinearon propuesta y `edits` entre web y API (`3217211`, `0d0749a`). Revisión manual: no consta.
- **Web H3 (bandeja del orientador y oportunidades):** Claude Code (subagente: no consta) generó la bandeja del orientador con propuesta, explicación y decisión HITL y las tarjetas de oportunidad del joven, más un ajuste de ancho de la tabla (rama `feat/web-h3-orientador-oportunidades`, PR #5). El PR #5 deja anotado que falta la revisión formal de accesibilidad AA. Revisión manual: no consta.
- **Agentes H4 (trazas, Langfuse, guardrails, ruta de formación):** Claude Code (agente `jose-agentes`) enriqueció `agent_trace` (herramienta, salida, tipo de fila, pausa HITL), añadió `GET /traces`, el callback opcional de Langfuse sobre LiteLLM, el puerto `graph/guardrail_port.py` y el agente de Formación con `GET/POST /youth/{id}/training-plan`, con tests (PR #6). En la integración se dejó la discriminación de ofertas a Mercado en vez del guardrail (`b316348`). Revisión manual: no consta.
- **Datos H4 (guardrails de entrada y evals):** Claude Code (agente `sebastian-datos`) escribió `screen_text` (inyección de prompt, redacción de PII y bloqueo de discriminación, reglas en código), sus tests unitarios y 28 casos de eval deterministas con `results.md` (PR #6). Revisión manual: no consta.
- **Web H4 (traza y ruta de formación):** Claude Code (agente `kenneth-web`) generó la pantalla `/traza/[threadId]` (línea de tiempo por agente con herramienta, decisión, explicación y pausa HITL), la ruta `/joven/formacion`, los cursos en `/centro`, el cliente `traces.ts` y los mocks `mock-traces.ts` derivados del contrato (PR #6). La descripción del PR #6 dice que las pantallas se revisaron en el navegador con mocks en escritorio y a 375 px; no consta quién lo hizo. Revisión manual: no consta.
- **H5–H7 (endurecimiento, métricas, despliegue):** Claude (claude.ai) auditó el repositorio contra el plan, ejecutó el demo de punta a punta y redactó una guía con el código de cada cambio, probado en una copia. Los PR [#7](https://github.com/HackathonFISC/equipo-09/pull/7), [#8](https://github.com/HackathonFISC/equipo-09/pull/8) y [#9](https://github.com/HackathonFISC/equipo-09/pull/9) (H5) declaran que el código se tomó de esa guía y se aplicó y revisó a mano; sus commits figuran con la identidad git de @Xyryung y los fusionó @devoncats el 2026-10-17, sin revisiones registradas en GitHub. En H6, Claude Code redactó la sección Evals de este README, esta Bitácora (a partir del historial) y `docs/07-metodologia.md` (revisado contra el código de `main`).
  - José: reintentos del LLM (`drop_params`, errores permanentes vs. transitorios, circuito, presupuesto, caché), reglas de discriminación en Mercado, error 500 con CORS, `GET /courses`, fechas en UTC, Docker Compose. *Cambios a mano: (completar)*.
  - Sebastian: métricas del PRD en `results.md`, eval opcional con LLM, metodología. *Cambios a mano: (completar)*.
  - Kenneth: estado vacío de la ruta de formación, botón «Ejecutar matching», entrevistas agendadas, textos de decisión del orientador, guion y video. *Cambios a mano: (completar)*.

---

Entrega: tag de git `final-24h` sobre el último commit válido, al cumplirse la hora 24.
