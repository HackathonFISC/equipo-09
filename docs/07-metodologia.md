# 07 · Metodología — Puente

Cómo se despliega, cómo funciona y cómo está construido Puente, con sus límites conocidos. Complementa el [PRD](01-prd.md), los [requerimientos técnicos](02-requerimientos-tecnicos.md) y el [esquema del backend](05-esquema-backend.md).

## 1. Despliegue

### Local (desarrollo y demo)

Requisitos: Node ≥ 22, pnpm 11, Python ≥ 3.12 y uv.

```bash
cp .env.example .env                       # modelo y clave del LLM
pnpm install
cd apps/api && uv sync
uv run python -m puente_api.db.seed        # 50 corregimientos, 150 habilidades, 25 ofertas, 12 cursos, 40 jóvenes
uv run python scripts/check_llm.py         # el LLM responde
cd ../.. && pnpm dev                       # web :3001 · api :8000
```

`--reset` en el comando del seed borra y vuelve a cargar los datos semilla. La configuración se lee del `.env` de la raíz o de `apps/api/.env`. La base es SQLite (`DATABASE_URL=sqlite:///./puente.db`, relativa a `apps/api`) y los checkpoints del grafo viven en un archivo hermano, `apps/api/puente-checkpoints.sqlite`, así que una pausa del orientador sobrevive a reiniciar la API.

### Docker Compose

> Describe lo que agrega la rama `feat/api-h6-docker` (H6), todavía no fusionada al escribir este documento: `compose.yaml`, los Dockerfiles, `psycopg` y la variable `CHECKPOINT_PATH`. En `main` sin esa rama solo existe el despliegue local.

`docker compose up --build` levanta tres servicios:

| Servicio | Imagen | Qué hace |
|---|---|---|
| `postgres` | `postgres:16-alpine` | Base de datos (volumen `pgdata`) |
| `api` | `apps/api/Dockerfile` (Python 3.12 + uv) | Siembra de forma idempotente y arranca FastAPI en :8000. Checkpoints (`CHECKPOINT_PATH=/data/checkpoints.sqlite`) y caché del LLM en el volumen `apidata` |
| `web` | `apps/web/Dockerfile` (Node 22 + pnpm) | `next build` + `next start` en :3001 |

El navegador llama a la API en `http://localhost:8000` (`NEXT_PUBLIC_API_URL`, fijada al compilar) y los Server Components la llaman dentro de la red de Docker en `http://api:8000` (`API_INTERNAL_URL`). `docker compose down -v` borra los volúmenes para empezar de cero.

### Verificación

- `pnpm --filter api test` (unitarios) y `pnpm --filter api evals` (28 casos).
- `cd apps/api && uv run python scripts/smoke_demo.py` recorre el guion del demo contra la API viva (`--strict-llm` exige respuestas del LLM). El script llega con la rama `feat/api-h6-docker`.

## 2. Funcionamiento

### Regla de diseño

**El LLM extrae, redacta y explica; el código calcula, asigna, verifica y decide.** Ninguna restricción (traslado, presupuesto, horario, salario, cupos) depende de texto generado: no hay camino de texto a puntaje.

### Flujo de una oferta (empresa)

1. **Guardrails de entrada** (`guardrails/screen.py` detrás del puerto `graph/guardrail_port.py`, sin LLM): bloquean la inyección de prompt y los textos de más de 20 000 caracteres con un 422, y redactan la PII (cédula, teléfono, correo) antes de llamar al LLM. Si el guardrail falla con una excepción, bloquea. En ofertas, la discriminación no bloquea aquí: pasa a Mercado.
2. **Mercado** extrae título, habilidades, horario, salario y corregimiento con el LLM, y el código los normaliza a ESCO-lite (etiqueta o alias exactos y luego similitud difusa) y a corregimientos.
3. Los requisitos discriminatorios se detectan con **reglas deterministas** (edad, género, apariencia, foto, estado civil, embarazo, residencia, nacionalidad) más los que el LLM cite con texto literal de la oferta. Si hay alguno, la oferta queda **bloqueada** y se abre una revisión `bloqueo_oferta`. Si el LLM falla, las reglas bloquean igual.
4. El grafo se detiene (`interrupt`) hasta que el orientador confirma el bloqueo (`aprobar`), corrige título, salario o vacantes y la publica (`editar`), o la libera (`rechazar`, con comentario opcional).

### Flujo de un joven

1. **Registro** con corregimiento, tiempo máximo de traslado, presupuesto diario, horario y salario mínimo.
2. **Perfil**: CV en PDF o texto, o una entrevista de hasta 5 preguntas dirigidas a las habilidades que piden las ofertas publicadas. El LLM propone habilidades y el código exige que cada una cite un fragmento literal de lo que escribió el joven; sin evidencia se descarta.
3. **Ruta de formación** (`GET/POST /youth/{id}/training-plan`): un MIP con OR-Tools (CP-SAT, con respaldo greedy) elige sesiones de cursos que maximizan las vacantes desbloqueadas, sujeto a cupos, horario del joven, choques entre sesiones, costo total y traslado al centro. El LLM solo redacta la explicación, y se descarta si trae cifras que el solver no dio.

### Corrida de matching (orientador)

1. **Matching** (`POST /match-runs`): CP-SAT asigna cada joven a lo sumo a una vacante, con capacidad por oferta, restricciones duras y objetivo de cobertura de habilidades ponderada. El grafo usa el preset `relaxed` (hasta 15 min, B/. 1.00 y una habilidad obligatoria de holgura, penalizadas y registradas en cada asignación).
2. **Auditor**: vuelve a ejecutar el solver con los mismos parámetros cambiando nombre, género y corregimiento (un corregimiento gemelo con el mismo tiempo de traslado) y mide la paridad. Por debajo del 95 % abre una revisión `alerta_sesgo`.
3. **Postulación**: redacta CV y carta por candidato; un verificador rechaza cualquier habilidad ausente del perfil y, si falla, usa una plantilla determinista. Abre la revisión `lista_corta`.
4. **Orientador**: aprueba, reordena o quita candidatos, o descarta la lista. Al aprobar se agendan entrevistas de 30 min sin choques desde las 09:00 (hora de Panamá) del siguiente día hábil, y las postulaciones pasan a «enviada». Una alerta de sesgo aceptada retiene la lista corta; descartarla exige un comentario.

### Trazabilidad

Cada nodo escribe una fila en `agent_trace` (agente, paso, entrada, herramienta, salida, decisión, razón, duración y tipo: `paso`, `pausa_hitl`, `decision_humana`, `guardrail` o `error`). `/traza/[threadId]` muestra la línea de tiempo. Langfuse es opcional (ver `.env.example`).

### Robustez del LLM

`LLMClient` (LiteLLM) valida cada salida con Pydantic y reintenta mostrando el error al modelo. Los errores permanentes (400, 401, 403, 404, 422) pasan directo al modelo de respaldo. Los transitorios (429, 5xx, red) esperan con backoff exponencial. Tras 4 fallas seguidas en una petición se abre un circuito (`LLM_CIRCUIT_FAILURES`), y hay un presupuesto de 45 s por petición (`LLM_BUDGET_S`). Si nada funciona, cada agente usa un valor por defecto seguro y la traza lo declara. Una caché opcional en disco (`LLM_CACHE_DIR`) repite respuestas ya validadas.

## 3. Arquitectura

Diagramas en [03-app-flow.md](03-app-flow.md) y [02-requerimientos-tecnicos.md](02-requerimientos-tecnicos.md).

| Capa | Tecnología | Dónde |
|---|---|---|
| Web | Next.js 16, React 19, Tailwind 4, shadcn/ui; cliente tipado `openapi-fetch` | `apps/web`, `packages/ui` |
| Contrato | OpenAPI 3.1 (fuente de verdad), Scalar | `packages/api-spec` |
| API | FastAPI, errores `application/problem+json` | `apps/api/src/puente_api/main.py`, `routers/` |
| Orquestación | LangGraph: supervisor determinista, `interrupt`, checkpointer SQLite | `graph/` |
| Optimización | OR-Tools CP-SAT (matching) y MIP con respaldo greedy (formación) | `solvers/` |
| Guardrails | Reglas en código (inyección, PII, discriminación) | `guardrails/` |
| LLM | LiteLLM detrás de `LLMClient` | `llm/` |
| Datos | SQLAlchemy 2; SQLite en local, PostgreSQL en Docker (rama `feat/api-h6-docker`) | `db/` |

## 4. Evaluación

- **28 casos deterministas** en `apps/api/tests/evals/cases/` (matching, auditor, guardrails, formación). Pasan 28/28.
- **Métricas del PRD §8** medidas sobre el seed completo y publicadas en [results.md](../apps/api/tests/evals/results.md): 0 violaciones de restricciones duras con el preset estricto (que en el seed da 1 asignación), paridad contrafactual del 100 % en las tres variables, 100 % de recall en ofertas discriminatorias (6/6 de las 25 etiquetadas) y 100 % de entradas maliciosas bloqueadas (8/8).
- **Extracción con LLM (F1)**: `uv run python -m tests.evals.llm_extraction` contra el proveedor real; escribe `results-llm.md`. No medido todavía.

## 5. Datos

Corregimientos reales (INEC) con coordenadas aproximadas; matriz de traslado estimada con un método documentado; habilidades ESCO-lite curadas a mano; empresas, ofertas, cursos y jóvenes **sintéticos** y marcados como tales. Detalle en [db/seed/README.md](../apps/api/src/puente_api/db/seed/README.md).

## 6. Límites conocidos

- **Entrada por foto** no disponible (corte 1 del plan): ofertas y CVs en texto o PDF; una imagen se rechaza con un mensaje.
- **Una vacante por joven y por corrida**: el solver asigna a lo sumo una oferta a cada joven. Con los datos semilla hay pocos pares factibles (1 asignación con el preset estricto, 3 en el preset del demo), y la paridad contrafactual es poco exigente con tan pocas asignaciones.
- **Holguras del preset del demo**: 2 de 3 asignaciones del seed superan el traslado máximo y les falta una habilidad obligatoria, siempre dentro de la tolerancia. El orientador lo ve en la lista corta y puede quitarlas.
- **Reglas de discriminación** diseñadas con las ofertas del seed a la vista: el 100 % de recall es sobre ese conjunto; con textos nuevos puede bajar. El LLM complementa, nunca reemplaza.
- **Corregir una oferta bloqueada** solo cambia título, salario y vacantes; el texto original se conserva para auditoría.
- **Alerta de sesgo aceptada**: retiene la lista corta, pero la nueva corrida se lanza a mano («Ejecutar matching»).
- **Altas por API** de empresas, centros y cursos (`POST /companies`, `/training-centers`, `/courses`) no implementadas; los catálogos vienen del seed.
- **Ejecución síncrona**: los agentes corren dentro de la petición HTTP (con presupuesto de LLM de 45 s); no hay cola de trabajos.
- **LLM del demo en plan gratuito**: el demo usa Gemini (`gemini/gemini-3.8-flash`) con una clave del plan gratuito, que limita las peticiones por minuto. Un 429 se reintenta con backoff y, si se agota el presupuesto, el agente usa su valor por defecto. La caché `LLM_CACHE_DIR` lo mitiga: en los ensayos y en el demo, las respuestas ya validadas se repiten sin llamar al proveedor.
- **Sin envío real** de correos: la acción es persistir lista corta, entrevistas y bloqueos, y mostrarlos en la web.
