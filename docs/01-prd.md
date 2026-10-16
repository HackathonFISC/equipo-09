# 01 · PRD — Puente

> Sistema agéntico de inserción laboral juvenil · Reto 3 (Empleabilidad) · Hackathon FISC AI Agents 2026 · Equipo 09
> Nombre de trabajo: **Puente** (provisional).

## 1. Resumen

Puente es un mercado de tres lados (jóvenes, empresas y centros de formación) en el que un equipo de agentes de IA normaliza datos sucios (ofertas copiadas de portales, fotos de volantes, CVs en foto o inexistentes), asigna candidatos a vacantes y a cursos con **solvers deterministas** que respetan restricciones reales de traslado, horario y dinero, y **audita el sesgo** de cada decisión. Un **orientador humano** aprueba o corrige las decisiones clave y cada recomendación viene con su explicación.

No es un chat ni un portal de empleo genérico: los agentes perciben (leen ofertas y CVs), deciden (matching y ruta de formación con optimización) y actúan (bloquean ofertas, agendan entrevistas, envían listas cortas).

## 2. Problema

| Lado | Qué falla hoy | Consecuencia |
|---|---|---|
| Jóvenes | No saben qué habilidades pide el mercado ni cómo traducir experiencia informal (negocio familiar, voluntariado). No saben qué curso gratuito cierra su brecha. | Envían CVs masivos sin respuesta; terminan en la informalidad. |
| Empresas | Reciben cientos de postulaciones que no encajan. Publican requisitos vagos o discriminatorios ("buena presencia", límites de edad). | Filtran a mano, contratan tarde y excluyen talento. |
| Centros de formación (INADEH y similares) | Sus cursos no llegan a quien más los aprovecha. | Cupos mal usados, brechas sin cerrar. |
| Geografía | Una oferta en Tocumen puede ser inviable para alguien de La Chorrera por horas de traslado y costo. Los portales lo ignoran. | Abandono temprano del empleo o postulaciones imposibles. |

**Datos de contexto (verificar y citar en la presentación):**
- Desempleo juvenil (15–29 años) estimado en **19.9 %** a septiembre 2025 (16.5 % hombres, 25.4 % mujeres), frente a 17.8 % en octubre 2024; ~113 mil jóvenes desocupados. Fuente: La Prensa, con base en INEC/Observatorio Mitradel — <https://www.prensa.com/economia/al-menos-113-mil-jovenes-no-tienen-empleo-formal-en-panama/>
- Desempleo nacional estimado en 10.4 % (septiembre 2025). Fuente: INEC — <https://www.inec.gob.pa/archivos/P053342420260304095947Comentario%20Sept%202025.pdf>
- Panamá Oeste reporta la tasa de desempleo juvenil más alta del país. Fuente: TVN — <https://www.tvn-2.com/nacionales/panama-oeste-desempleo-juvenil-registra-tasa-alta-a-nivel-nacional-sector-privado-genera-empleo_1_2240743.html>

Esto justifica que el demo se centre en jóvenes de **Panamá Oeste (Arraiján, La Chorrera)** frente a ofertas concentradas en la ciudad de Panamá y Tocumen.

## 3. Usuarios y actores

| Actor | Qué quiere | Restricción | Rol en Puente |
|---|---|---|---|
| Joven (18–29) | Trabajo rápido, cerca, compatible con estudios | Poco dinero para transporte; CV pobre o inexistente | Sube CV o foto, hace entrevista de perfil, ve matches y ruta de formación |
| Empresa | Mejor candidato con poco esfuerzo | Pocas vacantes, poco tiempo | Publica oferta (texto/foto/PDF), recibe lista corta explicada |
| Centro de formación | Llenar cursos con quien los aprovecha | Cupos y horarios fijos | Publica cursos/sesiones, recibe inscritos sugeridos |
| **Orientador humano** | Proceso justo y sin sesgos | Supervisa a muchos candidatos | Bandeja de revisión: aprueba o corrige matches, listas cortas y bloqueos |

Persona principal del demo: **Ana, 21 años, La Chorrera**. Ayudó 3 años en la fonda familiar (caja, inventario, atención). Estudia de noche. Presupuesto de transporte ≤ B/. 4 diarios. Sin CV formal.

## 4. Objetivos y no-objetivos

**Objetivos**
1. Convertir entradas sucias (ofertas y CVs) en datos estructurados sobre una taxonomía de habilidades común (ESCO-lite).
2. Recomendar vacantes **factibles** (traslado, horario, salario) con explicación por cada match.
3. Proponer una ruta de formación óptima que cierre la brecha de habilidades bajo cupos, horario, costo y transporte.
4. Detectar y bloquear ofertas discriminatorias y medir sesgo del matching con pruebas contrafactuales.
5. Mantener al orientador en control de las decisiones clave.

**No-objetivos (MVP)**
- No es un chatbot de consejos laborales (la regla de oro del reto).
- No se integra con WhatsApp/Telegram: canal único **web app**.
- No envía correos reales: la acción real es persistir agenda, listas cortas y bloqueos en la base de datos y notificarlos en la web.
- No reemplaza al orientador ni toma decisiones de contratación.

## 5. Alcance

| Agente | MVP 24 h | Stretch |
|---|---|---|
| 1. Inteligencia de mercado | Sí | Tendencias agregadas |
| 2. Perfil | Sí (CV texto/PDF/foto + entrevista guiada por texto) | Entrevista por nota de voz |
| 3. Matching (solver) | Sí | — |
| 4. Ruta de formación (solver) | Sí | — |
| 5. Postulación | Sí (CV/carta adaptados, agenda de entrevista y lista corta en BD) | Envío por correo |
| 6. Entrevista simulada | No | Sí |
| 7. Auditor de sesgo | Sí | Dashboard histórico |

## 6. Historias de usuario

**Joven**
- **J1.** Como joven sin CV, quiero responder una entrevista corta para que el sistema descubra habilidades que no sé nombrar. *Aceptación:* tras ≤ 8 preguntas se generan ≥ 3 habilidades mapeadas a la taxonomía, cada una con la evidencia citada de mis respuestas.
- **J2.** Como joven, quiero ver solo ofertas que puedo cumplir. *Aceptación:* ninguna recomendación supera mi tiempo máximo de traslado ni mi presupuesto de transporte; cada tarjeta muestra tiempo, costo diario y por qué encajo.
- **J3.** Como joven, quiero saber qué curso me abre más puertas. *Aceptación:* la ruta indica cursos, sesiones compatibles con mi horario, costo total y cuántas vacantes adicionales desbloquea.
- **J4.** Como joven, quiero postularme con un CV adaptado a la oferta. *Aceptación:* el CV adaptado solo contiene habilidades presentes en mi perfil (verificado por código).

**Empresa**
- **E1.** Como empresa, quiero pegar mi oferta como texto o foto. *Aceptación:* se extraen título, habilidades, horario, salario y ubicación; los requisitos discriminatorios se marcan y bloquean hasta corregirse.
- **E2.** Como empresa, quiero una lista corta explicada. *Aceptación:* recibo ≤ 5 candidatos aprobados por el orientador, con puntaje desglosado y franjas de entrevista propuestas.

**Centro de formación**
- **C1.** Como centro, quiero cargar cursos con cupos y horarios. *Aceptación:* el solver nunca asigna más inscritos que cupos.

**Orientador**
- **O1.** Como orientador, quiero revisar las decisiones clave antes de que se publiquen. *Aceptación:* listas cortas, bloqueos de ofertas y alertas de sesgo pasan por mi bandeja; puedo aprobar, editar o rechazar con comentario, y el cambio queda trazado.
- **O2.** Como orientador, quiero saber por qué el sistema decidió algo. *Aceptación:* cada decisión muestra el agente que la tomó, las restricciones activas, el puntaje desglosado y el resultado de la prueba contrafactual.

## 7. Matriz de trazabilidad: requisitos del reto → producto

| Requisito mínimo | Cómo lo cumple Puente | Evidencia en el demo |
|---|---|---|
| 1. ≥ 3 agentes con roles distintos que se comunican | 6 agentes en MVP orquestados por un supervisor LangGraph con estado compartido | Vista de traza de una corrida |
| 2. Herramienta que actúa | Escribe en BD: bloqueo de ofertas, agenda de entrevistas (`interview_slot`), listas cortas, inscripciones | Registros creados y visibles en empresa/joven |
| 3. Componente determinista | Matching con OR-Tools CP-SAT; ruta de formación con MIP; matriz de traslado; validadores; pruebas contrafactuales | Mostrar restricción violada que el LLM no puede saltarse |
| 4. Humano en el ciclo | `interrupt` de LangGraph antes de publicar lista corta, bloquear oferta o aceptar alerta de sesgo | Orientador corrige un match en vivo |
| 5. Trazabilidad | Langfuse + tabla `agent_trace` | Línea de tiempo por agente |
| 6. ≥ 15 evals | ≥ 20 casos en `apps/api/tests/evals` con métricas por agente | Tabla de resultados en README |
| 7. Guardrails | Inyección de prompt en CV/oferta, fuera de alcance, datos absurdos, PII | Caso malicioso bloqueado en vivo |

| Rúbrica | Peso | Respuesta del producto |
|---|---|---|
| Impacto y solución | 30 % | Foco en Panamá Oeste, datos INEC, restricción de traslado y costo |
| Diseño agéntico | 25 % | Roles claros, solvers deterministas, auditor contrafactual |
| Funcionamiento en vivo | 20 % | Guion end-to-end de 3 min con datos semilla reales |
| Robustez | 15 % | Evals + guardrails demostrados |
| Presentación y bitácora | 10 % | Docs en `/docs`, Bitácora de IA en README |

## 8. Métricas de éxito

**Del demo (medibles en evals)**
- 0 matches que violen restricciones duras (traslado, horario, salario, capacidad).
- Paridad contrafactual ≥ 95 %: cambiar nombre, género o corregimiento (con mismo tiempo de traslado) no cambia el resultado.
- Detección de requisitos discriminatorios: recall ≥ 90 % en el set de evals.
- Extracción de habilidades: F1 ≥ 0.8 contra etiquetas manuales.
- 100 % de entradas maliciosas del set bloqueadas o neutralizadas.

**De impacto (proyectadas, para el pitch)**
- Reducción de postulaciones inviables (traslado > límite) frente a la postulación masiva.
- Vacantes desbloqueadas por cada curso recomendado.
- Tiempo del orientador por candidato.

## 9. Supuestos y riesgos

- Los datos de ofertas y cursos se recolectan a mano de portales públicos e INADEH; los perfiles de jóvenes son **sintéticos** y se marcan como tales.
- La matriz de traslado es una estimación por corregimiento (tiempo y costo de bus/metro), documentada en las fuentes.
- Riesgos y mitigaciones en [06-plan-implementacion.md](06-plan-implementacion.md).
