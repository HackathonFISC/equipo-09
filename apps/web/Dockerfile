# Web de Puente (Next.js). Contexto de build: la RAÍZ del monorepo (usa el workspace de pnpm).
FROM node:22-slim

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install -g pnpm@11.22.0

WORKDIR /repo
# 1) Manifiestos del workspace: la instalación se reutiliza mientras no cambie el lockfile.
#    `.env.schema` va antes porque el postinstall corre `varlock codegen` sobre apps/web.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.json ./
COPY apps/web/package.json apps/web/.env.schema apps/web/
COPY apps/api/package.json apps/api/
# La app de docs (Fumadocs) no va en la imagen, pero es parte del workspace y del lockfile:
# sin su manifiesto, `--frozen-lockfile` falla.
COPY apps/docs/package.json apps/docs/
COPY packages/ui/package.json packages/ui/
COPY packages/config/package.json packages/config/
COPY packages/api-spec/package.json packages/api-spec/
RUN pnpm install --frozen-lockfile

# 2) Código. NEXT_PUBLIC_* se incrusta en el bundle del navegador al compilar.
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_MOCKS=nunca
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_API_MOCKS=$NEXT_PUBLIC_API_MOCKS \
    NODE_ENV=production
RUN pnpm --filter web build

EXPOSE 3001
WORKDIR /repo/apps/web
CMD ["./node_modules/.bin/next", "start", "--port", "3001", "--hostname", "0.0.0.0"]
