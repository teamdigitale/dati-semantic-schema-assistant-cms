FROM node:22-alpine AS build

WORKDIR /workspace

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build

FROM node:22-alpine AS runtime

LABEL org.opencontainers.image.title="Schema Assistant web"

WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /workspace/dist/ndc-platform-ai/browser ./public
COPY apps/web/server.mjs ./server.mjs
COPY apps/web/security-headers.mjs ./security-headers.mjs

USER node
EXPOSE 8080

CMD ["node", "server.mjs"]
