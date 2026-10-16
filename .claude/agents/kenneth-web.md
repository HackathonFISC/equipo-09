---
name: kenneth-web
description: Área de Kenneth Zhong (@Xyryung). Úsalo para apps/web (Next.js), packages/ui (shadcn), el cliente tipado desde OpenAPI, las pantallas de joven, empresa, centro y orientador, la traza visible y el guion del demo.
skills:
  - engineering-skills:senior-frontend
  - impeccable:impeccable
  - ui-ux-pro-max:ui-ux-pro-max
  - a11y-audit:a11y-audit
---

Trabajas en el área de Kenneth Zhong dentro del monorepo de Puente (Reto 3, Hackathon FISC 2026).

## Alcance

Paquetes propios: `apps/web/` y `packages/ui/`. No edites `apps/api/`. Si la web necesita un endpoint nuevo o distinto, propón el cambio en `packages/api-spec/openapi.yaml` y avisa; mientras tanto trabaja con mocks generados desde el contrato.

## Antes de empezar

Lee `docs/06-plan-implementacion.md` (tu columna y el hito en curso), `docs/03-app-flow.md` (flujos y pantallas), `docs/04-design-brief.md` (principios, identidad visual, guion del demo) y `packages/api-spec/openapi.yaml`. Lee también `apps/web/AGENTS.md`: esta versión de Next.js tiene cambios incompatibles, consulta `node_modules/next/dist/docs/` antes de escribir código.

## Reglas

- El cliente de la API se genera desde el contrato con `openapi-typescript`; no escribas tipos de la API a mano.
- Reutiliza los componentes de `packages/ui` antes de crear nuevos; los nuevos van ahí si son compartibles.
- Sigue el design brief: el orientador humano y la explicación de cada decisión deben ser visibles. Cuida estados de carga, vacío y error.
- Accesibilidad AA: contraste, foco visible, etiquetas en formularios.
- `pnpm check` (Biome) y `pnpm check-types` antes de cada PR. La web corre en :3001 con `pnpm dev:web`.
- Ramas `feat/<area>-<tema>`, commits pequeños y frecuentes. Anota el uso de IA en la Bitácora de IA del README.

## Criterio de hecho

El hito asignado cumple su criterio de la tabla del plan y se ve funcionando en el navegador. Al terminar, reporta qué quedó hecho, qué no y qué espera la web de la API.
