# Production frontend image: build the static bundle with the context base and
# API URL baked in, then serve it with `vite preview` (no dev server, no proxy).
#
# Provide the context/base and API URL WHEN BUILDING the image, e.g.:
#   docker build --build-arg APP_BASE=/material-planning/ \
#                --build-arg VITE_API_BASE_URL=https://host:14020 -t frontend .
# (docker-compose.yml passes these from ${APP_BASE} / ${VITE_API_BASE_URL}.)

# ---- 1. Build ----
FROM node:22-slim AS build
ARG APP_BASE=/
ARG VITE_API_BASE_URL=
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# Vite bakes these into the compiled assets at build time.
ENV APP_BASE=${APP_BASE}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npx vite build

# ---- 2. Serve the static build ----
FROM node:22-slim AS runtime
ARG APP_BASE=/
WORKDIR /app
# APP_BASE is needed at preview time so `vite preview` serves under the base.
ENV APP_BASE=${APP_BASE}
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/vite.config.ts ./vite.config.ts
EXPOSE 5173
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
