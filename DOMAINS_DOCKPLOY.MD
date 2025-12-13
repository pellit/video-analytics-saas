# Configuración de dominios y rutas en Dockploy

Esta guía documenta cómo configurar los dominios, rutas y puertos para cada servicio del stack en Dockploy usando un solo dominio (`dev.pellit.com.ar`). Incluye recomendaciones adicionales para variables de entorno y proxy.

---

## Tabla de servicios, rutas y puertos

| Servicio      | Nombre Compose   | Dominio              | Ruta externa (Path) | Puerto interno | Ejemplo Dockploy           |
|--------------|------------------|----------------------|---------------------|---------------|----------------------------|
| Frontend     | frontend         | dev.pellit.com.ar    | `/`                 | 80 o 3000     | Host: dev.pellit.com.ar, Path: /     |
| Backend API  | api              | dev.pellit.com.ar    | `/api`              | 8000          | Host: dev.pellit.com.ar, Path: /api  |
| AI Worker    | ai_worker        | dev.pellit.com.ar    | `/worker`           | 5000          | Host: dev.pellit.com.ar, Path: /worker |
| VLM Service  | vlm_service      | dev.pellit.com.ar    | `/vlm`              | 5100          | Host: dev.pellit.com.ar, Path: /vlm  |
| Media Server | media_server     | dev.pellit.com.ar    | `/mediamtx`         | 8554, 8888, 8889, 1935, 9997 | Host: dev.pellit.com.ar, Path: /mediamtx |

---

## Ejemplo de configuración por servicio en Dockploy

### frontend
- Host: `dev.pellit.com.ar`
- Path: `/`
- Container Port: `80` (Nginx) o `3000` (Node.js)
- Strip Path: Activado
- Variables de entorno:
  - `VITE_API_URL=https://dev.pellit.com.ar/api`
  - `VITE_STREAM_URL=https://dev.pellit.com.ar/video_feed`
  - `VITE_MEDIAMTX_WEBRTC_URL=https://dev.pellit.com.ar:8889`
  - `VITE_MEDIAMTX_HLS_URL=https://dev.pellit.com.ar:8888`
  - `VITE_USE_MEDIAMTX=true`

### api (Laravel)
- Host: `dev.pellit.com.ar`
- Path: `/api`
- Container Port: `8000`
- Strip Path: Activado
- Variables de entorno:
  - `APP_KEY=<clave Laravel>`
  - `DB_HOST=db`
  - `REDIS_HOST=redis`

### ai_worker
- Host: `dev.pellit.com.ar`
- Path: `/worker`
- Container Port: `5000`
- Strip Path: Activado
- Variables de entorno:
  - `BACKEND_API_URL=https://dev.pellit.com.ar/api`
  - `MEDIAMTX_RTSP_URL=rtsp://media_server:8554`
  - `VLM_SERVICE_URL=http://vlm_service:5100`
  - `WORKER_API_KEY=<clave si usas auth>`

### vlm_service
- Host: `dev.pellit.com.ar`
- Path: `/vlm`
- Container Port: `5100`
- Strip Path: Activado
- Variables de entorno:
  - `REDIS_HOST=redis`
  - `VLM_MODEL=vikhyatk/moondream2`

### media_server
- Host: `dev.pellit.com.ar`
- Path: `/mediamtx`
- Container Port: `8554`, `8888`, `8889`, `1935`, `9997`
- Strip Path: Activado
- Variables de entorno:
  - `SERVER_IP=<ip servidor>`
  - `MEDIAMTX_RECORD=no`

---

## Recomendaciones adicionales

- **SSL:** Activa HTTPS y Let's Encrypt en Dockploy para el dominio principal.
- **Strip Path:** Mantén activado para que el path externo no se duplique en el servicio.
- **Variables de entorno:** Configura en Dockploy según el servicio y revisa que coincidan con los nombres usados en el compose.
- **CORS:** Permite el dominio principal en todos los servicios que expongan APIs.
- **Proxy:** Si usas Nginx/Traefik, asegúrate de que las rutas estén correctamente mapeadas a los puertos internos.
- **Red interna:** Todos los servicios deben estar en la misma red de Docker Compose (`saas_net` o similar).
- **Prefijo de proyecto (recomendado):** Usa `PROJECT_NAME` para prefijar routers/servicios en los labels de Traefik y así evitar colisiones con otras aplicaciones desplegadas en Dokploy.
- **TRAEFIK_NETWORK:** Define `TRAEFIK_NETWORK` con la red que Traefik usa en Dokploy (por ejemplo `dokploy-network`) y añádela a las labels `traefik.docker.network`.
- **Pre-despliegue:** Antes de desplegar, comprueba y detén stacks Dokploy con routers que puedan colisionar: `dokploy rm <project>` o `docker rm -f <container>`.
- **Pruebas:** Verifica cada endpoint tras el despliegue accediendo a las rutas recomendadas.

---

## Ejemplo de acceso
- Frontend: `https://dev.pellit.com.ar/`
- API: `https://dev.pellit.com.ar/api`
- AI Worker: `https://dev.pellit.com.ar/worker`
- VLM: `https://dev.pellit.com.ar/vlm`
- MediaMTX: `https://dev.pellit.com.ar/mediamtx`

---

Si necesitas agregar más servicios, sigue el mismo patrón: un path único por servicio bajo el mismo dominio y configura el puerto interno según el Dockerfile.


## Example
Environment Settings
You can add environment variables to your resource.


VITE_API_URL=https://dev.pellit.com.ar/api
VITE_STREAM_URL=https://dev.pellit.com.ar/video_feed
VITE_MEDIAMTX_WEBRTC_URL=https://dev.pellit.com.ar:8889
VITE_MEDIAMTX_HLS_URL=https://dev.pellit.com.ar:8888
VITE_USE_MEDIAMTX=true
BACKEND_API_URL=https://dev.pellit.com.ar/api
MEDIAMTX_RTSP_URL=rtsp://media_server:8554
VLM_SERVICE_URL=http://vlm_service:5100

APP_URL=https://dev.pellit.com.ar
FRONTEND_URL=https://dev.pellit.com.ar
SESSION_DOMAIN=.dev.pellit.com.ar
SANCTUM_STATEFUL_DOMAINS=dev.pellit.com.ar
SESSION_SECURE_COOKIE=true
SESSION_SAME_SITE=lax
CORS_ALLOWED_ORIGINS=https://dev.pellit.com.ar

SERVER_IP=38.51.69.71

APP_KEY=base64:DVG8yzj55RRSy64k+lBeqWpK1Hik5SGdj4bt5TNmXvw=
APP_DEBUG=false
DB_HOST=db
REDIS_CLIENT=phpredis
REDIS_HOST=redis
REDIS_PASSWORD=null
REDIS_PORT=6379

SENTINEL_CLIENT_ID=0c9453fe-4888-41fa-b95e-cb1fad99e7ce
SENTINEL_CLIENT_SECRET=PLAK1ea8916e682443e981803318c819c48b
