#!/bin/sh
set -e

echo "🚀 Iniciando despliegue de Laravel..."

# 1. Correr migraciones (Estructura de la BD)
echo "📦 Ejecutando migraciones de base de datos..."
php artisan migrate --force

# 2. Correr Seeders (Datos iniciales y SuperAdmin)
# Nota: Como usamos 'firstOrCreate' en el código PHP, esto actúa como 
# una verificación: si existe no hace nada, si no existe lo crea.
echo "🌱 Verificando/Creando SuperAdmin y datos base..."
php artisan db:seed --force

# 3. Limpiar cachés para asegurar que tome los cambios de .env y rutas
echo "🧹 Limpiando caché..."
php artisan config:clear
php artisan route:clear
php artisan view:clear

# 4. Ejecutar el comando principal del contenedor
echo "✅ Todo listo. Arrancando servidor..."
exec "$@"