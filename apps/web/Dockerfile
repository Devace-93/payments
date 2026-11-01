# accounts web (Qwik City SSR on Bun).
#
# Build context is the REPO ROOT (`/home/enrique/accounts`), because the app
# imports the shared feature-flag registry from packages/shared and bundles
# the session.js widget from packages/session-js.
#
#   docker build -f apps/web/Dockerfile -t accounts-web .
#
# In deploy/docker-compose.yml this is:
#   web: { build: { context: .., dockerfile: apps/web/Dockerfile } }

# ─── Build stage ──────────────────────────────────────────────────────────────
FROM oven/bun:1 AS build
WORKDIR /repo

# Shared registry (feature switches) is imported by the app.
COPY packages/shared ./packages/shared
COPY apps/web ./apps/web

# session.js widget: bundled into apps/web/public so the web service serves it
# at /session.js (static file, see CONTRACT.md → session.js widget).
COPY packages/session-js ./packages/session-js
WORKDIR /repo/packages/session-js
RUN bun install --frozen-lockfile || bun install
RUN bun run build

WORKDIR /repo/apps/web
RUN bun install --frozen-lockfile || bun install

# Build-time public config. Vite inlines VITE_* at build time, so these must be
# present during `bun run build` (passed via compose build.args from .env). All
# optional — the app degrades gracefully when unset (PostHog / metrics / retro
# no-op).
ARG VITE_API_URL=/api
ARG VITE_APP_URL
ARG VITE_POSTHOG_KEY
ARG VITE_POSTHOG_HOST=https://us.i.posthog.com
ARG VITE_INFO_URL=https://info.3m4.net
ARG VITE_METRICS_PROJECT_KEY
ARG VITE_METRICS_TRACKER_URL=https://metrics.3m4.net/m.js
ARG VITE_RETRO_PROJECT_KEY
ARG VITE_RETRO_WIDGET_URL=https://retro.3m4.net/widget.js
ENV VITE_API_URL=$VITE_API_URL \
    VITE_APP_URL=$VITE_APP_URL \
    VITE_POSTHOG_KEY=$VITE_POSTHOG_KEY \
    VITE_POSTHOG_HOST=$VITE_POSTHOG_HOST \
    VITE_INFO_URL=$VITE_INFO_URL \
    VITE_METRICS_PROJECT_KEY=$VITE_METRICS_PROJECT_KEY \
    VITE_METRICS_TRACKER_URL=$VITE_METRICS_TRACKER_URL \
    VITE_RETRO_PROJECT_KEY=$VITE_RETRO_PROJECT_KEY \
    VITE_RETRO_WIDGET_URL=$VITE_RETRO_WIDGET_URL
RUN bun run build

# ─── Runtime stage ────────────────────────────────────────────────────────────
FROM oven/bun:1-slim AS runtime
WORKDIR /repo/apps/web

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000

# Built SSR server + client assets + deps.
COPY --from=build /repo/apps/web/server ./server
COPY --from=build /repo/apps/web/dist ./dist
COPY --from=build /repo/apps/web/node_modules ./node_modules
COPY --from=build /repo/apps/web/package.json ./package.json

EXPOSE 3000

# Start the standalone Node-API HTTP server with Bun (node:http compatible).
CMD ["bun", "./server/entry.node-server.js"]
