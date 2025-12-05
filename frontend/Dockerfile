# Build stage
FROM node:20-alpine as builder

WORKDIR /app

# Copiamos package.json y lock primero
COPY package*.json ./

# Instalamos dependencias
RUN npm install

# Copiamos el código
COPY . .

# Build para producción
RUN npm run build

# Production stage - servidor estático con nginx
FROM nginx:alpine

# Copiar build de producción
COPY --from=builder /app/dist /usr/share/nginx/html

# Copiar configuración de nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
