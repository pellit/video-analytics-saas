# CAMBIO CRÍTICO: Debe ser 20
FROM node:20-alpine

WORKDIR /app

# Copiamos package.json y lock primero
COPY package*.json ./

# Instalamos dependencias
RUN npm install

# Copiamos el código
COPY . .

# Exponemos y corremos
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
