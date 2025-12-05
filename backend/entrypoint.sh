#!/bin/sh
set -e

echo "🚀 Iniciando despliegue de Laravel..."

# 0. Crear .env desde variables de entorno si no existe
if [ ! -f .env ]; then
    echo "📝 Creando .env desde variables de entorno..."
    cat > .env << EOF
APP_NAME="${APP_NAME:-Video SaaS}"
APP_ENV=${APP_ENV:-production}
APP_KEY=${APP_KEY}
APP_DEBUG=${APP_DEBUG:-false}
APP_URL=${APP_URL:-http://localhost}

FRONTEND_URL=${FRONTEND_URL:-http://localhost:3000}

DB_CONNECTION=${DB_CONNECTION:-mysql}
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-3306}
DB_DATABASE=${DB_DATABASE:-saas_video_dev}
DB_USERNAME=${DB_USERNAME:-root}
DB_PASSWORD=${DB_PASSWORD:-secret}

REDIS_HOST=${REDIS_HOST:-redis}
REDIS_PORT=${REDIS_PORT:-6379}
REDIS_PASSWORD=${REDIS_PASSWORD:-null}

MAIL_MAILER=${MAIL_MAILER:-log}
MAIL_HOST=${MAIL_HOST:-localhost}
MAIL_PORT=${MAIL_PORT:-587}
MAIL_USERNAME=${MAIL_USERNAME:-}
MAIL_PASSWORD=${MAIL_PASSWORD:-}
MAIL_FROM_ADDRESS=${MAIL_FROM_ADDRESS:-noreply@example.com}
MAIL_FROM_NAME="${MAIL_FROM_NAME:-Video SaaS}"

CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS:-*}

WORKER_API_KEY=${WORKER_API_KEY:-}
EOF
    echo "✅ .env creado"
fi

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