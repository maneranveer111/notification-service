FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker-entrypoint.d/10-config.sh /docker-entrypoint.d/10-config.sh
RUN chmod +x /docker-entrypoint.d/10-config.sh
EXPOSE 80
