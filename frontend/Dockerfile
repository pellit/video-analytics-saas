# Build stage
FROM node:20-alpine as builder

WORKDIR /app

# Build arguments para variables de entorno de Vite
ARG VITE_API_URL=/api
ARG VITE_STREAM_URL=/video_feed

# Convertir ARGs a ENV para que Vite las use durante el build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_STREAM_URL=$VITE_STREAM_URL

# Copiamos package.json y lock primero
COPY package*.json ./

# Instalamos dependencias
RUN npm install

# Copiamos el código
COPY . .

# Build para producción
RUN npm run build

# Production stage - servidor estático con nginx
# Build cache buster: 2025-12-08-v3-storage-proxy
FROM nginx:alpine

# Copiar build de producción
COPY --from=builder /app/dist /usr/share/nginx/html

# Copiar configuración de nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
