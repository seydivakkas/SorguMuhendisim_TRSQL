# Multi-stage Dockerfile for TRSQL L0 Frontend (React + TypeScript + Vite -> Nginx)
# Offline note: for air-gapped environments, pre-populate npm cache or build dist/ beforehand.

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html
ENV TRSQL_API_UPSTREAM="http://api:8000"
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
