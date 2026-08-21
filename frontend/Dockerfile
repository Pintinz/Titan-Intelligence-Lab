# TitanIQ frontend — production image. No Dockerfile existed anywhere in the repo before this
# (Production Readiness Audit §9). Static build served by nginx; VITE_* build args must be
# supplied at build time (Vite inlines them into the JS bundle, they cannot be injected at
# container-start like a backend env var — see frontend/src/lib/env.ts's production-required
# VITE_API_BASE_URL guard, which this build will fail loudly against if omitted).

# ---- Build stage -----------------------------------------------------------------------------
FROM node:22-slim AS builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_SUPABASE_URL=${VITE_SUPABASE_URL} \
    VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}

RUN npm run build

# ---- Runtime stage ----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
