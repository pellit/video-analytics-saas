#!/bin/sh
set -e

echo "🚀 Iniciando despliegue de Laravel..."

# Control: Permite saltar migraciones/seeders si la variable ENTRYPOINT_RUN_MIGRATIONS es "false"
# Esto es útil para ejecutar comandos puntuales en el contenedor (p.ej. composer require) sin que
# el entrypoint intente correr migraciones o seeders antes de que estén satisfechas las dependencias.
if [ "${ENTRYPOINT_RUN_MIGRATIONS:-true}" = "true" ]; then
	# 1. Correr migraciones (Estructura de la BD)
	echo "📦 Ejecutando migraciones de base de datos..."
	php artisan migrate --force

	# 2. Correr Seeders (Datos iniciales y SuperAdmin)
	# Nota: Como usamos 'firstOrCreate' en el código PHP, esto actúa como
	# una verificación: si existe no hace nada, si no existe lo crea.
	echo "🌱 Verificando/Creando SuperAdmin y datos base..."
	php artisan db:seed --force
else
	echo "⚠️ ENTRYPOINT_RUN_MIGRATIONS=false -> Saltando migrations y seeders"
fi

# 3. Limpiar cachés para asegurar que tome los cambios de .env y rutas
echo "🧹 Limpiando caché..."
php artisan config:clear
php artisan route:clear
php artisan view:clear

# 4. Ejecutar el comando principal del contenedor
echo "✅ Todo listo. Arrancando servidor..."
exec "$@"