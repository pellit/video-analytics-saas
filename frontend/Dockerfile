FROM node:18-alpine

WORKDIR /app

# 1. Copiar package.json primero (para aprovechar caché de Docker)
COPY package*.json ./

# 2. Instalar dependencias
RUN npm install

# 3. Copiar el resto del código
COPY . .

# 4. Exponer puerto y ejecutar (Usamos --host para que se vea desde fuera)
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
