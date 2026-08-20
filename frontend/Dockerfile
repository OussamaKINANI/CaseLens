# syntax=docker/dockerfile:1

FROM node:24-alpine AS build

WORKDIR /app

COPY frontend/package.json ./
COPY frontend/package-lock.json ./

RUN npm ci

COPY frontend/ ./

RUN npm run build


FROM nginx:alpine AS runtime

COPY frontend/nginx.conf \
    /etc/nginx/conf.d/default.conf

COPY --from=build \
    /app/dist \
    /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK \
    --interval=10s \
    --timeout=3s \
    --retries=5 \
    CMD wget \
        --quiet \
        --tries=1 \
        --spider \
        http://127.0.0.1/ \
        || exit 1