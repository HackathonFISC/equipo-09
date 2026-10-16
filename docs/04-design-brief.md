# 04 · Design brief — Puente

## 1. Objetivo del diseño

Que cada actor entienda en segundos **qué decidió el sistema, por qué y qué puede hacer**. La interfaz es la prueba visible de que hay agentes que perciben, deciden y actúan, y de que un humano tiene el control.

## 2. Audiencias y contexto de uso

| Audiencia | Dispositivo | Necesidad | Tono |
|---|---|---|---|
| Joven | Celular, datos limitados | Pasos cortos, sin jerga, saber cuánto le cuesta llegar | Cercano, español panameño simple, tú |
| Empresa | Laptop | Pegar oferta rápido y ver candidatos listos | Profesional, directo |
| Centro de formación | Laptop | Cargar cursos y ver inscritos | Neutro |
| Orientador | Laptop, pantalla grande | Revisar muchas decisiones con contexto | Denso, preciso, usted |
| Jurado (demo) | Proyector | Ver el flujo de agentes de punta a punta | Claro, legible a distancia |

## 3. Principios

1. **Explicabilidad visible.** Cada match muestra el desglose (habilidades, traslado en minutos, costo diario en B/., horario, salario) antes que el puntaje. La frase del LLM acompaña, no reemplaza, los números.
2. **Lo factible primero.** Nunca se muestra una oferta inviable para el joven; si se oculta algo, se dice cuántas y por qué ("3 ofertas descartadas: más de 90 min de viaje").
3. **El humano decide.** Las acciones del orientador son botones primarios; las propuestas del sistema se marcan como "Propuesta del agente X".
4. **Agentes con nombre.** Cada estado de "procesando" nombra al agente que trabaja (Mercado, Perfil, Matching, Formación, Postulación, Auditor) con su ícono y color. La traza usa los mismos.
5. **Justicia transparente.** Las alertas de sesgo y los bloqueos se muestran con la regla o la prueba contrafactual que los disparó.
6. **Mobile-first para jóvenes, denso para orientador.**

## 4. Identidad visual inicial

- **Base:** componentes shadcn/ui de `packages/ui` (ya en el boilerplate), Tailwind 4, modo claro y oscuro (`mode-toggle` del boilerplate).
- **Tipografía:** Inter (UI) y JetBrains Mono (trazas, puntajes).
- **Paleta:**
  - Primario: azul profundo `#1E3A8A` (confianza institucional).
  - Acento: verde `#16A34A` (factible / aprobado).
  - Advertencia HITL: ámbar `#D97706` (espera revisión).
  - Bloqueo: rojo `#DC2626` (discriminación / guardrail).
  - Neutros: escala slate.
- **Color por agente** (chips y línea de tiempo): Mercado índigo, Perfil cian, Matching azul, Formación violeta, Postulación verde, Auditor ámbar, Orientador gris oscuro.
- **Íconos:** lucide-react (ya incluido).
- **Contraste WCAG AA**, foco visible, objetivos táctiles ≥ 44 px, sin depender solo del color (íconos + texto en estados).

## 5. Pantallas clave

1. **Tarjeta de oportunidad (joven).** Título, empresa, corregimiento; fila de chips: `⏱ 45 min` `B/. 2.50/día` `Horario compatible` `B/. 650`; barra de cobertura de habilidades; "Por qué encajas" (2 líneas); botón "Postularme". Variante "Te falta: Excel básico → curso INADEH".
2. **Entrevista de perfil.** Una pregunta por pantalla, barra de progreso (≤ 8), habilidades descubiertas apareciendo en vivo con la evidencia subrayada.
3. **Ingesta de oferta (empresa).** Panel izquierdo con el texto/foto original, panel derecho con lo extraído editable; requisitos discriminatorios resaltados en rojo con sugerencia de reemplazo.
4. **Bandeja del orientador.** Tabla con tipo, agente, antigüedad, impacto; detalle en panel lateral con propuesta, explicación, traza y botones Aprobar / Editar / Rechazar.
5. **Lista corta (orientador → empresa).** Candidatos ordenados, desglose por columna, arrastrar para reordenar, quitar con motivo.
6. **Traza de agentes.** Línea de tiempo vertical: agente, decisión, razón, duración; los pasos HITL marcados en ámbar. Es la pantalla que se proyecta al jurado.
7. **Resultado de auditoría.** Tabla de pares contrafactuales (original vs. variante) y paridad por variable.

## 6. Guion visual del demo (3 min)

| Tiempo | Pantalla | Mensaje |
|---|---|---|
| 0:00–0:20 | Portada + dato INEC | 19.9 % de desempleo juvenil; Panamá Oeste el más afectado |
| 0:20–0:50 | Empresa pega oferta con "buena presencia, 18–25" | Mercado extrae, Auditor bloquea, orientador corrige |
| 0:50–1:30 | Ana sin CV hace la entrevista | Perfil descubre "manejo de caja", "inventario", "atención al cliente" con evidencia |
| 1:30–2:10 | Matching | Ana ve 4 ofertas factibles; una en Tocumen descartada por 110 min; ruta de formación desbloquea 3 más |
| 2:10–2:40 | Bandeja del orientador | Aprueba lista corta; se agendan entrevistas (acción real en BD) |
| 2:40–3:00 | Traza + evals + guardrail | Línea de tiempo por agente; prompt-injection en un CV neutralizada |

## 7. Fuera de alcance de diseño
Branding final, landing pública, ilustraciones personalizadas.
