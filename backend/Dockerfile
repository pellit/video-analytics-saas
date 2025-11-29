FROM php:8.2-fpm

# 1. Dependencias del sistema
RUN apt-get update && apt-get install -y \
    git \
    curl \
    libpng-dev \
    libonig-dev \
    libxml2-dev \
    zip \
    unzip \
    && docker-php-ext-install pdo_mysql mbstring exif pcntl bcmath gd

# 2. Redis
RUN pecl install redis && docker-php-ext-enable redis

# 3. Composer
COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

WORKDIR /var/www/html

# 4. Copiar código y dependencias
COPY . .
RUN composer install --no-interaction --optimize-autoloader --no-dev

# 5. Permisos
RUN chown -R www-data:www-data /var/www/html/storage /var/www/html/bootstrap/cache

# --- NUEVO: Configuración del Entrypoint ---
# Copiamos el script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# Le damos permisos de ejecución (CRÍTICO)
RUN chmod +x /usr/local/bin/entrypoint.sh

# Le decimos a Docker que use este script como puerta de entrada
ENTRYPOINT ["entrypoint.sh"]

# El comando por defecto sigue siendo el mismo (se pasará al entrypoint como "$@")
CMD ["php", "artisan", "serve", "--host=0.0.0.0", "--port=8000"]
