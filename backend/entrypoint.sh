#!/bin/sh
set -e

echo "🚀 Iniciando despliegue de Laravel..."

# Wait for MySQL to be ready
wait_for_mysql() {
    echo "⏳ Esperando a que MySQL esté listo..."
    # Aumentamos reintentos y tiempo de espera para entornos donde MySQL tarda en inicializar
    max_attempts=${DB_WAIT_MAX_ATTEMPTS:-60}
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # Ejecutamos un chequeo más verboso para poder depurar en caso de error
        # Ejecutar chequeo y capturar salida para depuración
        db_host=${DB_HOST:-db}
        db_port=${DB_PORT:-3306}
        db_user=${DB_USERNAME:-root}
        db_pass=${DB_PASSWORD:-secret}
        ping_output=$(php -r "try { new PDO('mysql:host=' . '${db_host}' . ';port=' . '${db_port}', '${db_user}', '${db_pass}'); echo 'ok'; } catch(Exception \$e) { echo 'ERR: ' . $e->getMessage(); exit(1); }" 2>&1 || true)
        echo "   [mysql_ping] $ping_output"
        if echo "$ping_output" | grep -q '^ok'; then
            echo "✅ MySQL está listo!"
            return 0
        fi
        echo "   Intento $attempt/$max_attempts - MySQL no disponible aún..."
        sleep ${DB_WAIT_SLEEP:-3}
        attempt=$((attempt + 1))
    done
    
    echo "❌ Error: MySQL no respondió después de $max_attempts intentos"
    return 1
}

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
	# Wait for MySQL before running migrations
	wait_for_mysql

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

# 4. Create storage symlink (for public access to uploaded files)
echo "🔗 Creando storage link..."
php artisan storage:link --force 2>/dev/null || true

# 5. Create required directories
echo "📁 Creando directorios de storage..."
mkdir -p storage/app/public/satellite/thumbs
mkdir -p storage/app/public/cad_renders
chmod -R 775 storage

# 6. Ejecutar el comando principal del contenedor
echo "✅ Todo listo. Arrancando servidor..."
exec "$@"