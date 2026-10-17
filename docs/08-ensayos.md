# 08 · Ensayos del demo

Bitácora de los ensayos del guion ([doc 04 §6](04-design-brief.md#6-guion-visual-del-demo-3-min)) y checklist de grabación. Una fila por problema. Solo las filas con «Bloqueo: sí» se arreglan después del congelamiento (reglas de H7: apareció en un ensayo, rompe un segmento y se arregla en menos de 30 min).

## Reinicio antes de cada ensayo (5 min)

La prueba de humo crea datos: córrela primero y reinicia después.

```bash
# con pnpm dev corriendo en otra terminal
cd apps/api
uv run python scripts/check_llm.py               # el LLM responde
uv run python scripts/smoke_demo.py --strict-llm # el camino del backend funciona
# detén pnpm dev (Ctrl+C) y reinicia los datos:
rm -f puente.db puente.db-* puente-checkpoints.sqlite*
uv run python -m puente_api.db.seed
cd ../.. && pnpm dev
```

Conserva `apps/api/.llm-cache/` entre ensayos si `LLM_CACHE_DIR` está definido: las entradas idénticas se repiten desde la caché y el ensayo 2 y la grabación son más rápidos y estables.

**Roles.** Kenneth maneja y narra. José vigila la terminal de la API y `/traza` (errores y respaldos del LLM). Sebastian lleva el reloj y llena esta bitácora.

## Bitácora

El ensayo 0 fue automático: un agente recorrió el guion en el navegador integrado de Claude Code el 2026-10-17, sobre una base recién sembrada, con la API real (`gemini/gemini-3.8-flash`, caché vacía salvo la oferta) y `NEXT_PUBLIC_API_MOCKS=nunca`, en `next dev`. «Real» es la espera del agente medida en la API más el tiempo estimado de las acciones en pantalla; no incluye la latencia del propio agente que manejaba el navegador. Capturas en [`ensayos/ensayo-0/`](ensayos/ensayo-0/).

| Ensayo | Segmento | Previsto | Real | Qué pasó | Dueño | ¿Bloqueo? |
| --- | --- | --- | --- | --- | --- | --- |
| 0 (automático) | 0:00 portada | 15 s | 15 s | Sin problemas. En todo el recorrido las pantallas dicen «Datos de la API», nunca «Datos de ejemplo». Se ve el indicador «N» de Next.js en modo dev. | Kenneth | No |
| 0 (automático) | 0:15 empresa | 30 s | 30 s de acción + 20–46 s de Mercado (< 1 s con caché) | **Arreglado** (`fix(web): esperar 90 s…`): la web abortaba a los 30 s y mostraba «La API tardó demasiado en responder», pero la API seguía y creaba la oferta; al reintentar quedaban dos bloqueos iguales en la bandeja. Ahora espera 90 s (presupuesto del LLM 45 s + solver). | Kenneth | Sí (arreglado) |
| 0 (automático) | 0:15 empresa | 30 s | — | **Pendiente.** Con la caché vacía Gemini agotó el tiempo: dos `litellm.Timeout` por llamada con `LLM_TIMEOUT_S=25` y el presupuesto de 45 s agotado. Mercado cayó al respaldo: título = primera frase del texto y 0 habilidades (los 4 hallazgos sí salen, son reglas). Igual en Formación (52 s, explicación de plantilla). Reproducir: base nueva, `.llm-cache` vacía, `POST /postings` con la oferta del guion → la traza dice «el LLM no dio una salida válida». Probar `LLM_TIMEOUT_S=40` y llenar la caché antes de grabar. | José | No (con caché) |
| 0 (automático) | 0:15 orientador | — | < 1 s | Corregir y publicar funciona: título «Cajero/a de supermercado», revisión «Editada y aprobada», oferta publicada. | — | No |
| 0 (automático) | 0:45 registro y entrevista | 35 s | ~40 s de acción + 34 s de Perfil | Perfil encontró 4 habilidades con su frase (manejo de caja, control de inventario, atención al cliente, atención de fonda). El formulario de registro tiene unos 10 campos: acelerar 2× en la edición. Hay que pulsar «Empezar entrevista» antes de responder. | Kenneth | No |
| 0 (automático) | 0:45 registro | — | — | El seed ya tiene una joven «Ana» que entra en la misma lista corta; con el mismo nombre se ven dos «Ana». El guion registra a «Ana Pérez». | Kenneth | No |
| 0 (automático) | 1:20 matching y traza | 30 s | 15 s de acción + 37 s de agentes + 10 s de compilación | OPTIMAL, 5 asignaciones (no 3: cuentan la oferta corregida y Ana Pérez), paridad 1.00 en las tres variables. En `next dev` la primera visita a `/traza/[id]` compila ~10 s con «Matching, Auditor y Postulación están trabajando…» en pantalla: grabar con build de producción o abrir antes cualquier `/traza/<id>`. | Kenneth | No |
| 0 (automático) | 1:20 Postulación | — | 32 s | **Pendiente.** El verificador descartó los 5 textos del LLM («menciona habilidades ausentes del perfil»: Responsabilidad, Trabajo en equipo, Puntualidad…) y usó la plantilla segura en los 5, tras 2 llamadas fallidas. Son 32 s del LLM sin efecto visible. Reproducir: `POST /match-runs` sobre el estado del guion y leer el paso Postulación de la traza. | José | No |
| 0 (automático) | 1:50 lista corta | 30 s | 30 s de acción + 3 s | **Arreglado** (`fix(web): lista corta dice a qué oferta va…`): la lista corta aplanaba 4 ofertas y no decía a cuál iba cada candidato. Ahora cada fila muestra «→ oferta». Quitar a Edilma con motivo y Guardar edición funcionan; 4 entrevistas el lunes 19 oct a las 09:00, 09:30, 10:00 y 10:30 (hora de Panamá). | Kenneth | Sí (arreglado) |
| 0 (automático) | 1:50 lista corta | — | — | **Pendiente.** La propuesta `lista_corta` no trae por candidato el traslado, el costo diario ni las holguras, así que la pantalla no muestra que Edilma tarda 42 min con un máximo de 30 (solo «traslado 0 %»). La web ya pinta `commuteMin` y `dailyCost` si llegan en `proposal.postings[].candidates[]`. Reproducir: `GET /reviews?status=pendiente` tras la corrida. Mientras tanto, el motivo escrito lo deja a la vista. | José | Sí (narrativa) |
| 0 (automático) | 1:50 lista corta | — | — | **Pendiente.** Tras decidir, el editor sigue a la vista (flechas, ✕, «Devolver» y el motivo editable) aunque la revisión ya está resuelta. Cosmético. | Kenneth | No |
| 0 (automático) | 2:20 formación | 20 s | 15 s de acción + 8–52 s si se calcula en vivo | En una base nueva Alexis no tiene ruta: hay que pulsar «Calcular mi ruta». Calcularla antes de grabar. Resultado: 3 cursos, B/. 25.40, 4 ofertas con 5 vacantes (con la oferta corregida; sin ella, 3 ofertas con 4 vacantes). | Kenneth | No |
| 0 (automático) | 2:20 formación | — | — | **Arreglado** (mismo commit que la lista corta): el indicador «Vacantes que abre» mostraba `unlockedPostings` (4 ofertas) mientras el texto decía 5 vacantes. Ahora dice «Ofertas que abre». | Kenneth | No (arreglado) |
| 0 (automático) | 2:20 formación | — | — | **Pendiente.** Los ítems de la ruta no traen el nombre del centro, así que «INADEH» no aparece en pantalla (los 4 centros del seed son INADEH). Agregar el centro a `TrainingPlan.items[]`. | Sebastian | No |
| 0 (automático) | 2:40 inyección | 20 s | 15 s de acción + ~10 s de carga | Bloqueada con 422: «Respuesta detenida por un guardrail … inyeccion_prompt:ignorar_instrucciones». En `next dev` `/joven/perfil` tardó ~10 s en salir de «Cargando…»: tener la pestaña abierta. Tras reiniciar la entrevista el contador dice «Pregunta 1 de hasta 5» con el texto de la pregunta 2 (cosmético). | Kenneth | No |
| 0 (automático) | entorno | — | — | `pnpm --filter web dev` falla en Windows: el postinstall de varlock revienta al salir (`Assertion failed … async.c`) y pnpm 11 reintenta el install antes de cada script. Arreglo: `VARLOCK_TELEMETRY_DISABLED=true` antes de pnpm. | José | No |
| 0 (automático) | entorno | — | — | Dos veces la prueba de humo de otra sesión corrió contra la API de este ensayo (puertos 8000 y 8010) porque su uvicorn no pudo tomar el puerto, y ensució la base. `smoke_demo.py` debería abortar si el servidor que levanta no arranca, y cada ensayo comprobar antes que el puerto está libre. | José | No |
| 1 |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |

### Duración estimada por segmento (ensayo 0)

| Segmento | Previsto | Acción en pantalla | Espera de agentes (sin caché) | Con caché y build de producción |
| --- | --- | --- | --- | --- |
| 0:00 portada | 15 s | 15 s | — | 15 s |
| 0:15 empresa → orientador | 30 s | ~30 s | 20–46 s | ~30 s |
| 0:45 registro + entrevista | 35 s | ~40 s (registro a 2×: ~25 s) | 34 s | ~35 s si se corta la espera |
| 1:20 matching → traza | 30 s | ~15 s | 37 s (+10 s compilación dev) | ~30 s si se corta la espera |
| 1:50 lista corta | 30 s | ~30 s | 3 s | ~30 s |
| 2:20 formación (precalculada) | 20 s | ~15 s | 0 s (8–52 s si se calcula en vivo) | ~20 s |
| 2:40 inyección + evals | 20 s | ~15 s | < 1 s | ~20 s |
| **Total** | **3:00** | **~2:40** | **~1:35–2:30** | **~3:00 cortando las esperas** |

Las esperas del LLM no caben en 3 minutos: se graban por segmento y se cortan en la edición (H7). En vivo, llenar la caché con una pasada previa idéntica deja la oferta en < 1 s; la entrevista y el matching dependen de que las entradas sean las mismas.

## Checklist de grabación

- [ ] Reinicio completo (arriba) y `check_llm.py` en verde; mismo modelo desde el ensayo 1 hasta la grabación.
- [ ] Pasada previa con las mismas entradas para llenar `.llm-cache`; luego reiniciar la base **sin** borrar la caché.
- [ ] `apps/web/.env.local` con `NEXT_PUBLIC_API_MOCKS=nunca` (el `.env` de la raíz no lo lee la web). Ninguna pantalla debe decir «Datos de ejemplo».
- [ ] Build de producción (`pnpm build && pnpm --filter web start`) o indicador de Next.js oculto; abrir antes cada pestaña del guion (incluida una `/traza/<id>`).
- [ ] Ruta de Alexis calculada antes de grabar (`/joven/formacion?id=ec74ea56-2c0e-581d-873f-7d3d0fa1e5d4` → «Calcular mi ruta»).
- [ ] Pantalla 1920×1080 a 30 fps (OBS, o `Win+G` / `⌘⇧5`).
- [ ] Navegador con perfil limpio (sin extensiones ni barra de marcadores), zoom 125 %, modo claro, no molestar activado.
- [ ] Narración grabada aparte (nota de voz en un cuarto silencioso) y montada en la edición.
- [ ] Grabar por segmento (7 clips cortos), no en una toma.
- [ ] Decir «el siguiente día hábil», no un día de la semana: la fecha de las entrevistas depende de cuándo se graba.
- [ ] Ensayo 2 grabado completo como **video de respaldo**.
