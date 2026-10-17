# Resultados de evals

Generado con `uv run python -m tests.evals.report` (no editar a mano). Los evals son deterministas: usan los solvers OR-Tools y los guardrails directamente, sin LLM, sin red y sin base de datos.

## Métricas de éxito del PRD (§8)

Medidas sobre los datos semilla completos (40 jóvenes, 25 ofertas, 25 etiquetas), además de los casos controlados de abajo.

| Métrica | Meta | Resultado | Estado | Cómo se mide |
|---|---|---|---|---|
| Matches que violan restricciones duras (preset estricto) | 0 | 0 de 1 asignaciones | CUMPLE | Seed completo con `MatchingParams()`; cada asignación se re-verifica con `check_pair` estricto, independiente del solver. |
| Asignaciones con holgura en el preset del demo (`relaxed`) | informativa | 2 de 3 asignaciones | — | El nodo Matching usa `MatchingParams.relaxed()`: tolera 15 min, B/. 1.00 y 1 habilidad obligatoria, penalizados. Casos: Abdiel Cedeño → Ayudante general de obra: habilidades_obligatorias, traslado_max; Edilma De León → Dependiente de farmacia: habilidades_obligatorias, traslado_max |
| Paridad contrafactual: nombre | ≥ 95 % | 100 % (40 jóvenes, 3 con asignación) | CUMPLE | Se re-ejecuta el solver del demo cambiando la variable y se cuenta qué fracción de jóvenes conserva su resultado. Con pocas asignaciones la paridad es poco exigente: los no asignados siguen sin asignar. |
| Paridad contrafactual: genero | ≥ 95 % | 100 % (40 jóvenes, 3 con asignación) | CUMPLE | Se re-ejecuta el solver del demo cambiando la variable y se cuenta qué fracción de jóvenes conserva su resultado. Con pocas asignaciones la paridad es poco exigente: los no asignados siguen sin asignar. |
| Paridad contrafactual: corregimiento | ≥ 95 % | 100 % (40 jóvenes, 3 con asignación) | CUMPLE | Se re-ejecuta el solver del demo cambiando la variable y se cuenta qué fracción de jóvenes conserva su resultado. Con pocas asignaciones la paridad es poco exigente: los no asignados siguen sin asignar. |
| Detección de ofertas discriminatorias (recall) | ≥ 90 % | 6/6 (100 %) | CUMPLE | Reglas deterministas sobre las 25 ofertas etiquetadas a mano. Sin errores. |
| Detección de ofertas discriminatorias (precisión) | informativa | 6/6 (100 %) | — | Incluye 19 ofertas limpias y los controles de precisión del seed. |
| Tipos de requisito discriminatorio detectados | informativa | 16/16 (100 %) | — | Por oferta: tipos esperados (edad, género, apariencia…) que las reglas encontraron. |
| Extracción de habilidades de ofertas (F1) | ≥ 0.80 | no medido | — | Requiere un proveedor LLM: `uv run python -m tests.evals.llm_extraction`. |
| Entradas maliciosas bloqueadas o neutralizadas | 100 % | 8/8 (100 %) | CUMPLE | Casos `guard-*` con ataque o PII (inyección, instrucciones ocultas, cédula, correo). |

## Métrica de los casos

Un caso **pasa** cuando su salida coincide con `expected` (métrica de la columna «Métrica» de cada caso) y se cumplen las invariantes transversales: 0 restricciones duras violadas en las asignaciones y 0 fugas de PII o instrucciones embebidas en `sanitized`. La puntuación por categoría es casos pasados / casos totales.

## Resumen por categoría

| Categoría | Casos | Pasan | Exactitud |
|---|---:|---:|---:|
| Auditor contrafactual y discriminación | 5 | 5 | 5/5 (100 %) |
| Ruta de formación | 5 | 5 | 5/5 (100 %) |
| Guardrails de entrada | 11 | 11 | 11/11 (100 %) |
| Matching (restricciones duras) | 7 | 7 | 7/7 (100 %) |
| **Total** | **28** | **28** | **28/28 (100 %)** |

## Métricas de guardrails

- Ataques o PII detectados (recall): 8/8 (100 %)
- Textos legítimos sin falsos positivos: 3/3 (100 %)

## Detalle por caso

| Caso | Categoría | Métrica | Resultado |
|---|---|---|---|
| `audit-01-ciego-nombre-genero-corregimiento` | auditor | Paridad contrafactual por variable (jóvenes que conservan resultado / total) y veredicto passed | PASA |
| `audit-02-sesgo-genero-detectado` | auditor | Paridad contrafactual por variable (jóvenes que conservan resultado / total) y veredicto passed | PASA |
| `audit-03-sesgo-nombre-detectado` | auditor | Paridad contrafactual por variable (jóvenes que conservan resultado / total) y veredicto passed | PASA |
| `audit-04-oferta-discriminatoria` | auditor | passed == False y tipos de hallazgo esperados presentes | PASA |
| `audit-05-oferta-limpia` | auditor | passed == True y 0 hallazgos | PASA |
| `train-01-curso-desbloquea-oferta` | formacion | Sesiones elegidas y ofertas desbloqueadas idénticas a las esperadas | PASA |
| `train-02-sesion-llena` | formacion | Sesiones elegidas y ofertas desbloqueadas idénticas a las esperadas | PASA |
| `train-03-sin-solape` | formacion | Sesiones elegidas y ofertas desbloqueadas idénticas a las esperadas | PASA |
| `train-04-presupuesto` | formacion | Sesiones elegidas y ofertas desbloqueadas idénticas a las esperadas | PASA |
| `train-05-traslado-centro-lejano` | formacion | Sesiones elegidas y ofertas desbloqueadas idénticas a las esperadas | PASA |
| `guard-01-inyeccion-cv-es` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-02-inyeccion-entrevista-en` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-03-inyeccion-oferta-plantilla` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-04-inyeccion-oculta-cero-ancho` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-05-pii-cedula-telefono` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-06-pii-correo` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-07-discriminacion-edad-genero` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-08-discriminacion-foto-civil` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-09-cv-legitimo` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-10-oferta-legitima` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `guard-11-cv-estado-civil-no-bloquea` | guardrails | allowed esperado, razones esperadas presentes y 0 fugas de PII/instrucciones en sanitized | PASA |
| `match-01-basico` | matching | Asignación joven→oferta idéntica a la esperada y 0 restricciones duras violadas | PASA |
| `match-02-traslado-duro` | matching | Asignación joven→oferta idéntica a la esperada y 0 restricciones duras violadas | PASA |
| `match-03-horario-duro` | matching | Asignación joven→oferta idéntica a la esperada y 0 restricciones duras violadas | PASA |
| `match-04-requisito-obligatorio` | matching | Asignación joven→oferta idéntica a la esperada y 0 restricciones duras violadas | PASA |
| `match-05-requisito-holgura` | matching | Asignación esperada + holgura 'habilidades_obligatorias' registrada | PASA |
| `match-06-presupuesto-duro` | matching | Asignación joven→oferta idéntica a la esperada y 0 restricciones duras violadas | PASA |
| `match-07-cupos` | matching | Carga por oferta ≤ vacantes y total de asignados esperado | PASA |

## Cómo reproducirlos

```bash
pnpm --filter api evals                      # pytest tests/evals (un test por caso)
cd apps/api && uv run python -m tests.evals.report   # regenera este archivo
```

Los casos viven en `apps/api/tests/evals/cases/*.json` (uno por categoría; `_world.json` es la tabla de traslados compartida). Para añadir un caso, agrega un objeto con `id`, `category`, `type`, `description`, `metric`, `input` y `expected`; los tipos válidos son `matching`, `audit_matching`, `audit_posting`, `guardrail` y `training` (ver `runner.py`). Los controles positivos del auditor (`audit-02`, `audit-03`) usan solvers sesgados a propósito para comprobar que el contrafactual detecta el sesgo.
