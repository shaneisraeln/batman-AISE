# BATMAN dashboard container (build + static serve via vite preview).
FROM node:20-alpine AS build
WORKDIR /app
# VITE_BASE lets the SPA be served under a sub-path (e.g. /app/) behind a proxy.
ARG VITE_BASE=/
ENV VITE_BASE=${VITE_BASE}
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
EXPOSE 4173
# Serve the built SPA. The gateway URL is set via VITE_API_BASE at build time,
# or the app uses relative /v1 paths behind a reverse proxy.
CMD ["serve", "-s", "dist", "-l", "4173"]
