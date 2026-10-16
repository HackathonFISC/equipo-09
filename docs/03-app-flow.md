# 03 · App flow — Puente

Flujos por actor, grafo de agentes y mapa de pantallas. Canal único: **web app** (`apps/web`).

## 1. Arquitectura de agentes y punto de intervención humana

Este es el diagrama de arquitectura que pide el reto: agentes, herramientas, flujos y HITL.

```mermaid
flowchart TD
  IN1[/Oferta: texto, foto, PDF/] --> SUP{Supervisor}
  IN2[/CV: PDF, foto o nada + entrevista/] --> SUP
  IN3[/Cursos y sesiones/] --> DB[(BD)]

  SUP --> GR[Guardrails de entrada]
  GR -->|bloqueado| ERR[Respuesta de rechazo]
  GR --> MER[1 · Inteligencia de mercado<br/>LLM extrae · reglas detectan discriminación]
  GR --> PER[2 · Perfil<br/>LLM entrevista · código valida evidencia]

  MER -->|discriminatoria| H1[[HITL · bloqueo de oferta]]
  MER -->|limpia| DB
  H1 -->|liberar / editar| DB
  PER --> DB

  DB --> MAT[3 · Matching<br/>OR-Tools CP-SAT]
  MAT --> AUD[7 · Auditor<br/>contrafactuales deterministas]
  AUD -->|paridad baja| H3[[HITL · alerta de sesgo]]
  AUD -->|ok| POS[5 · Postulación<br/>CV/carta + agenda]
  H3 -->|re-correr sin variable| MAT
  POS --> H2[[HITL · lista corta]]
  H2 -->|aprobar / reordenar| ACT[(Acción: lista corta enviada,<br/>entrevistas agendadas)]

  DB --> FOR[4 · Ruta de formación<br/>OR-Tools MIP]
  FOR --> ACT2[(Acción: cupo reservado)]

  classDef hitl fill:#fde68a,stroke:#b45309,color:#000
  class H1,H2,H3 hitl
```

Todas las cajas escriben en `agent_trace` y en Langfuse.

## 2. Secuencia de una corrida de matching

```mermaid
sequenceDiagram
  actor O as Orientador
  participant W as Web
  participant A as API
  participant G as Grafo LangGraph
  participant S as Solver CP-SAT
  participant D as BD

  O->>W: "Ejecutar matching"
  W->>A: POST /match-runs
  A->>G: start(thread_id)
  A-->>W: 202 {threadId}
  G->>S: candidatos, vacantes, matriz de traslado
  S-->>G: asignación + desglose
  G->>G: Auditor: re-ejecuta con nombre/género/corregimiento cambiados
  G->>D: match_result, audit_check, agent_trace
  G->>G: Postulación: CV adaptado + verificador
  G->>D: review_task(lista_corta)
  G-->>G: interrupt()
  W->>A: GET /reviews (polling)
  O->>W: Aprueba y quita un candidato
  W->>A: POST /reviews/{id}/decision
  A->>G: Command(resume=decisión)
  G->>D: application, interview_slot, estado "enviada"
  W->>A: GET /traces/{threadId}
```

## 3. Flujos por actor

### 3.1 Joven
```mermaid
flowchart LR
  A[Inicio] --> B[Registro: corregimiento,<br/>presupuesto, tiempo máx., horario]
  B --> C{¿Tiene CV?}
  C -->|Sí| D[Sube PDF o foto]
  C -->|No| E[Entrevista guiada ≤ 8 preguntas]
  D --> E2[Entrevista corta para completar]
  E --> F[Perfil: habilidades + evidencia]
  E2 --> F
  F --> G[Mis oportunidades<br/>tarjetas con tiempo, costo y por qué]
  G --> H[Ruta de formación]
  G --> I[Postulación: CV adaptado]
  I --> J[Estado: lista corta / entrevista]
```

### 3.2 Empresa
```mermaid
flowchart LR
  A[Nueva oferta] --> B[Pega texto o sube foto/PDF]
  B --> C[Revisión de lo extraído]
  C --> D{¿Requisito discriminatorio?}
  D -->|Sí| E[Oferta bloqueada<br/>sugerencia de redacción]
  E --> F[Orientador decide]
  D -->|No| G[Publicada]
  F --> G
  G --> H[Lista corta aprobada<br/>con puntajes y franjas de entrevista]
```

### 3.3 Orientador (HITL)
```mermaid
flowchart LR
  A[Bandeja de revisión] --> B{Tipo}
  B --> C[Bloqueo de oferta]
  B --> D[Lista corta]
  B --> E[Alerta de sesgo]
  C & D & E --> F[Ve propuesta + explicación + traza]
  F --> G{Decisión}
  G -->|Aprobar| H[Grafo continúa]
  G -->|Editar| I[Cambios + comentario] --> H
  G -->|Rechazar| J[Comentario obligatorio] --> H
```

### 3.4 Centro de formación
Registro de centro → alta de cursos con habilidades y sesiones (cupos, horario) → vista de inscritos sugeridos por la ruta de formación.

## 4. Mapa de pantallas

| Ruta | Actor | Contenido |
|---|---|---|
| `/` | Todos | Selector de rol (demo) |
| `/joven/registro` | Joven | Datos de traslado, presupuesto, horario |
| `/joven/perfil` | Joven | Subir CV, entrevista, habilidades con evidencia |
| `/joven/oportunidades` | Joven | Tarjetas de match con desglose |
| `/joven/formacion` | Joven | Ruta de formación |
| `/joven/postulaciones` | Joven | Estado y entrevistas |
| `/empresa/ofertas/nueva` | Empresa | Ingesta de oferta |
| `/empresa/ofertas/[id]` | Empresa | Detalle, hallazgos, lista corta |
| `/centro/cursos` | Centro | Cursos y sesiones |
| `/orientador` | Orientador | Bandeja de revisión |
| `/orientador/revision/[id]` | Orientador | Detalle de decisión + traza |
| `/orientador/corridas/[id]` | Orientador | Resultado de matching y auditoría |
| `/trazas/[threadId]` | Orientador / jurado | Línea de tiempo por agente |

Estados por pantalla: **vacío** (con acción siguiente), **procesando** (agente activo mostrado por nombre), **esperando revisión**, **error** (mensaje en español y reintento), **bloqueado por guardrail** (razón visible).
