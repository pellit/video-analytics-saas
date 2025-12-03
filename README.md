# 📹 Video Analytics SaaS Platform

Plataforma de análisis de video en tiempo real basada en microservicios. Utiliza Inteligencia Artificial (YOLO + Vosk) para detección de objetos, análisis de tráfico, seguridad y comprensión semántica de audio.

Orquestado con **Laravel**, visualizado con **Vue.js**, procesado por **Python Workers** y comunicado vía **Redis**.

-----

## 🏗️ Arquitectura del Sistema

El sistema sigue una arquitectura orientada a eventos desacoplada:

```mermaid
graph TD
    User((Usuario)) --> |HTTP/WebSockets| Frontend[Vue.js Dashboard]
    Frontend --> |API REST| Backend[Laravel API]
    
    subgraph "Core Infrastructure"
        Backend --> |Dispatch Jobs| Redis[(Redis Broker)]
        Backend --> |Data| DB[(MySQL/Postgres)]
    end
    
    subgraph "AI Engine Cluster"
        Redis --> |Consume Task| Worker[Python AI Worker]
        Worker --> |Load| Models[YOLOv8 / Vosk]
        Worker --> |Publish Events| Redis
    end
    
    Redis --> |Broadcast Events| Backend
```

### Servicios Principales

  * **API (`/backend`):** Laravel 10. Gestiona cámaras, usuarios, autenticación y orquesta el inicio/fin de streams.
  * **Frontend (`/frontend`):** Vue 3 + Vite. Panel de control reactivo.
  * **AI Worker (`/ai_engine`):** Python 3.11. Worker escalable que consume tareas de Redis, procesa video (OpenCV/YOLO) y audio (Vosk), y emite alertas.
  * **Broker:** Redis. Maneja las colas de trabajo y los eventos en tiempo real (Pub/Sub).

-----

## 🌿 Git Flow & Entornos

Utilizamos una estrategia de ramas estricta para garantizar la estabilidad en producción.

| Rama Git | Entorno | Configuración Docker | Propósito |
| :--- | :--- | :--- | :--- |
| `development` | **Local / Staging** | `docker-compose.yml` + `docker-compose.dev.yml` | Desarrollo activo, pruebas, hot-reloading. |
| `main` | **Producción** | `docker-compose.yml` (Base) | Versión estable, optimizada, sin herramientas de dev. |

-----

## 🚀 Guía de Desarrollo Local

Para trabajar en tu máquina con **Hot Reloading** (ver cambios al instante) y herramientas de ML.

### 1\. Requisitos

  * Docker & Docker Compose
  * Git

### 2\. Configuración Inicial

Asegúrate de tener el archivo `docker-compose.dev.yml` (no incluido en el repo por defecto, créalo si no existe para habilitar volúmenes espejo):

```bash
# Levantar el entorno de desarrollo (fusiona config base + dev)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### 3\. Accesos Locales

  * **Frontend:** [http://localhost:5173](https://www.google.com/search?q=http://localhost:5173)
  * **API Backend:** [http://localhost:8000](https://www.google.com/search?q=http://localhost:8000)
  * **Label Studio (Etiquetado):** [http://localhost:8080](https://www.google.com/search?q=http://localhost:8080) (Si está activado en dev)

### 4\. Reentrenamiento (Active Learning Loop)

En entorno local, los workers guardan imágenes con baja confianza en `./ai_engine/data_to_review`.

1.  Abre Label Studio en el puerto 8080.
2.  Importa las imágenes y corrige las detecciones.
3.  Exporta el dataset y reentrena YOLO.
4.  Reemplaza el modelo en `/ai_engine/models/yolov8n.pt`.

-----

## 🚢 Despliegue con Dockploy

Dockploy se encarga de construir las imágenes de producción. No es necesario subir el archivo `.dev.yml`.

### A. Entorno Staging (Pruebas)

  * **Conectar Repo:** `https://github.com/TU_USUARIO/video-analytics-saas.git`
  * **Branch:** Seleccionar `development`.
  * **Variables de Entorno:** Configurar DB y Redis (ver abajo).
  * **Funcionamiento:** Desplegará la última versión de desarrollo pero construyendo las imágenes finales (simulación real).

### B. Entorno Producción (Live)

  * **Conectar Repo:** Mismo repositorio.
  * **Branch:** Seleccionar `main`.
  * **Estrategia:** Solo hacer Merge a `main` cuando Staging esté verificado.

### Variables de Entorno Requeridas (Dockploy)

Añadir estas variables en la configuración del servicio en Dockploy:

```ini
# Base de Datos
DB_HOST=db
DB_DATABASE=saas_video
DB_USERNAME=root
DB_PASSWORD=secret_secure_password
MYSQL_ROOT_PASSWORD=secret_secure_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
  
Note: Avoid exposing internal services like Redis on the host in production/Dokploy. We intentionally don't publish the Redis host port in `docker-compose.yml` to prevent port collisions with other system services. Configure the host side mapping only in dev (docker-compose.dev.yml) if you need host access.

# Laravel
APP_ENV=production
APP_KEY=base64:TU_CLAVE_GENERADA_AQUI
APP_DEBUG=false
APP_URL=http://192.168.0.38:8000
VITE_API_URL=http://192.168.0.38:8000/api
VITE_STREAM_URL=http://192.168.0.38:5000/video_feed
FRONTEND_URL=http://192.168.0.38:5173
WORKER_API_KEY=your_worker_api_key_here
```

-----

## 📂 Estructura del Proyecto

```text
video-analytics-saas/
├── docker-compose.yml       # Configuración BASE (Producción)
├── docker-compose.dev.yml   # Configuración DEV (Local override)
├── backend/                 # Código Laravel (API)
│   ├── app/Jobs/            # Jobs que envían tareas a Python
│   └── Dockerfile           # PHP 8.2 FPM
├── frontend/                # Código Vue.js
│   └── Dockerfile           # Node Alpine
├── ai_engine/               # Código Python
│   ├── src/worker_manager.py # Entrypoint (Escucha Redis)
│   ├── models/              # Archivos .pt (YOLO) y modelos Vosk
│   └── Dockerfile           # Python 3.11 Slim + OpenCV
└── infrastructure/          # Configs de Nginx/Redis
```

## 🛠️ Comandos Útiles

```bash
# Entrar a la terminal de Laravel
docker-compose exec api bash

# Instalar dependencias PHP (si se agregan nuevas)
docker-compose run --rm api composer install

# Ver logs del Worker de IA
docker-compose logs -f ai_worker

# Limpiar todo (Reset de fábrica)
docker-compose down -v --remove-orphans
```



## 🛠️ El Flujo de Trabajo (Workflow)
Así es como trabajarás día a día:

A. En tu Computadora (Local Development)
Estás en la rama development. Para trabajar, necesitas fusionar el archivo base con el de desarrollo. No uses docker-compose up a secas. Usa este comando:

Bash+

# Levanta usando ambos archivos
COMPOSE_PROFILES=dev docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

Nota: En vez de usar `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`, ejecuta el comando con `COMPOSE_PROFILES=dev` para que los overrides (puertos y volúmenes orientados a dev) solo se apliquen cuando los quieras usar. Esto evita que servicios de dev expongan puertos en hosts compartidos como Dokploy.
Tip: Crea un alias en tu terminal o un archivo Makefile para no escribir eso siempre. Por ejemplo, make dev.

B. En Dockploy (Entorno de Staging / Pruebas)
Aquí quieres ver cómo se comporta la rama development en un servidor real.

⚠️ Nota importante: **No** incluyas `docker-compose.dev.yml` en el comando de despliegue dentro de Dockploy o tu CI/CD. El archivo `docker-compose.dev.yml` contiene ajustes para el entorno local (puertos publicados, volúmenes espejo, debug). Si lo incluyes en la ejecución del compose dentro de Dokploy, podrías provocar conflictos de puertos (por ejemplo el `api` intentando publicar 8000) o exponer servicios internos innecesarios.
Si necesitas exponer puertos específicos o usar overrides en Dockploy, hazlo mediante variables de entorno o mediante un `docker-compose.prod.yml` exclusivo de producción que use puertos/proxies adecuados.

En Dockploy, crea un Nuevo Proyecto (ej: video-saas-staging).

Conéctalo a tu repo GitHub.

Branch: Selecciona development.

Despliega.

¿Qué pasa aquí? Como Dockploy ejecuta docker-compose up estándar, *debería* ignorar el archivo `docker-compose.dev.yml`.
⚠️ Nota importante: **No** incluyas `docker-compose.dev.yml` en el comando de despliegue dentro de Dockploy o tu CI/CD. El archivo `docker-compose.dev.yml` contiene ajustes para el entorno local (puertos publicados, volúmenes espejo, debug). Si lo incluyes en la ejecución del compose dentro de Dokploy, podrías provocar conflictos de puertos (por ejemplo el `api` intentando publicar 8000) o exponer servicios internos innecesarios.
Si necesitas exponer puertos específicos o usar overrides en Dockploy, hazlo mediante variables de entorno o mediante un `docker-compose.prod.yml` exclusivo de producción que use puertos/proxies adecuados.

Resultado: Se desplegará la versión de desarrollo, pero usando contenedores construidos (build) igual que en producción. ¡Perfecto para probar antes de pasar a Main!

C. En Dockploy (Entorno de Producción)
En Dockploy, tienes tu proyecto principal (video-saas-prod).

Branch: Selecciona main.

Despliega.

Cómo gestionar las ramas en Git
Aquí tienes los comandos para organizar tu repo ahora mismo:

Bash

# 1. Crear y cambiar a la rama de desarrollo
git checkout -b development

# 2. Agregar tu archivo de configuración dev (si quieres compartirlo con el equipo)
git add docker-compose.dev.yml
git commit -m "chore: add development environment config"
git push -u origin development

# --- TRABAJAS, EDITAS CÓDIGO ---

# 3. Subir cambios a desarrollo
git add .
git commit -m "feat: improve yolo detection"
git push origin development 
# (Aquí Dockploy 'Staging' se actualiza si tienes auto-deploy)

# --- TODO ESTÁ LISTO PARA PRODUCCIÓN ---

# 4. Mezclar desarrollo en main
git checkout main
git merge development
git push origin main
# (Aquí Dockploy 'Producción' se actualiza)
Resumen Visual
Tu PC: Corre development + docker-compose.dev.yml.

Dockploy (Staging): Corre development (solo docker-compose.yml).

Dockploy (Prod): Corre main (solo docker-compose.yml).



## ¿Cómo acceder?
En lugar de escribir localhost en el navegador de tu computadora, debes escribir la IP Privada (LAN) o Pública del servidor.

Averigua la IP del servidor: Ejecuta en la terminal del servidor:

Bash

hostname -I
# Te devolverá algo como: 192.168.1.50  o  10.0.0.5
Usa esa IP en tu navegador:

Frontend: http://192.168.1.50:5173

Backend API: http://192.168.1.50:8000

Label Studio: http://192.168.1.50:8080

2. ¿Por qué te funcionará? (La configuración clave)
Para que esto sea posible, tuvimos que asegurarnos de dos cosas en los pasos anteriores (que ya incluí en tus archivos, pero es bueno que sepas por qué):

Frontend (Vite): Por defecto, Vite solo escucha en local. Para que te deje entrar por IP, el comando debe tener la bandera --host.

Tu configuración: command: npm run dev -- --host ✅ (Correcto)

Backend (Laravel): Por defecto, artisan serve solo escucha en local. Necesita --host=0.0.0.0.

Tu configuración: command: php artisan serve --host=0.0.0.0 ... ✅ (Correcto)



## Correr comando dentro de contenedor Docker
docker exec -it code-api-1 php artisan optimize:clear

## Correr tests dentro de contenedor Docker
docker exec -it code-api-1 php artisan test

> ⚠️ Nota: este proyecto requiere PHP 8.2 para instalar las dependencias de Composer.
> - Recomendado (modo seguro): ejecuta `composer install` dentro del contenedor Docker (usa `docker-compose run --rm api composer install` o `docker-compose exec api composer install` si el contenedor ya está levantado).
> - Alternativa (si no usas Docker): instala PHP 8.2 en tu máquina local (o usa una herramienta como phpenv/containers) antes de ejecutar `composer install`.
> - Evitar: `composer install --ignore-platform-reqs` solamente como último recurso de emergencia — puede que el código no funcione en PHP 8.1.

### Ejecutar Composer dentro del contenedor (recomendado)

Si montas la carpeta `backend` desde el host dentro del contenedor (p. ej. con `-v $(pwd)/backend:/var/www/html`) y el `vendor/` local no existe o está incompleto, el `entrypoint` podría lanzarse y ejecutar `php artisan` (migraciones/seeders) antes de instalar dependencias, provocando errores como "Trait Laravel\\Sanctum\\HasApiTokens not found".

Formas seguras de ejecutar Composer dentro del contenedor:

- Si el servicio `api` está corriendo (entrada por defecto ejecuta `entrypoint.sh`):
```bash
docker compose exec api composer install --no-interaction --optimize-autoloader --prefer-dist
```
- Si no está corriendo, o si prefieres un comando puntual que no ejecute `entrypoint.sh`, puedes saltar el entrypoint y ejecutar composer así:
```bash
docker compose run --rm --entrypoint "" -v $(pwd)/backend:/var/www/html api composer install --no-interaction --optimize-autoloader --prefer-dist
```
- Alternativa: exportar una variable para que `entrypoint.sh` no ejecute migraciones ni seeders (se puede usar si `entrypoint.sh` lo implementa):
```bash
ENTRYPOINT_RUN_MIGRATIONS=false docker compose run --rm -v $(pwd)/backend:/var/www/html api composer install
```

Esto permitirá que `composer` instale dependencias correctamente (p. ej. `laravel/sanctum`) sin arrancar de forma automática las migraciones que dependen de dependencias aún no instaladas.

## URL's Permitidas CORS
dev.pellit.com.ar 
api-dev.pellit.com.ar 
video-dev.pellit.com.ar 
cv.pellit.com.ar 
api-cv.pellit.com.ar 
video.pellit.com.ar;

Siguientes / mejoras:

Real-time:
Reemplazar SSE POC por un WebSocket o Laravel Echo server con Pusher o Soketi para mejorar escalabilidad.
Worker scaling:
Transicionar a worker pool / Kubernetes Job que procese streams en paralelo y use recursos limitados (GPU/CPU) apropiadamente; la implementación actual es multithread minimal, suficiente para testing.
Tests:
Añadir E2E test de overlay también espera que el canvas muestre el bbox (el test actual solo verifica lista). Puedo extender el E2E con una verificación visual del canvas o con assertions en DOM (lista).
Prod compose / deploy:
He dejado recomendaciones en README acerca de no usar docker-compose.dev.yml en Dockploy; si quieres, puedo crear docker-compose.prod.yml que haga build estático del frontend (Nginx) y sea safe para production.
Cleanup:
Eliminar api/test/worker-env debug route cuando termines de comprobar la env.

esta era la hoja de ruta que inicio el proyecto, estos e cumplen?


Aquí tienes la Hoja de Ruta Técnica y el código clave para transformar ese repo en tu SaaS.

1. Arquitectura de la Solución
Orquestador (Laravel API): Gestiona la base de datos de cámaras (mysql/pgsql), usuarios y envía órdenes ("Start/Stop") a Redis.
Cliente (Vue 3 + Tailwind): Panel visual para ver métricas y streams.
Bus de Mensajes (Redis): La cola donde Laravel pone tareas y Python publica eventos.
Worker de IA (Python Refactorizado):
Ya no es un script main.py que corre solo.
Es un Demonio que escucha Redis.
Usa YOLO para tráfico/seguridad.
Usa Vosk + SentenceTransformers para "entender conceptos" (NLP).
Base de Datos Vectorial (pgvector o ChromaDB): Para que la IA "entienda conceptos" (búsqueda semántica) en lugar de solo palabras clave exactas.

2. El Backend: Laravel (El Jefe)
Necesitas una estructura de base de datos para guardar la configuración de qué buscar (tráfico vs seguridad).
Migración: create_cameras_table.php
PHP
Schema::create('cameras', function (Blueprint $table) {
    $table->id();
    $table->string('name');
    $table->string('stream_url');
    $table->enum('type', ['traffic', 'security', 'retail']); // Define qué modelo/lógica usar
    $table->json('roi_points')->nullable(); // Región de interés (polígono)
    $table->boolean('is_active')->default(false);
    $table->timestamps();
});


El Controlador: CameraController.php
Cuando activas una cámara, Laravel no procesa el video, solo despacha la orden.
PHP
public function startAnalysis(Camera $camera)
{
    $camera->update(['is_active' => true]);

    // Enviamos la configuración completa a Python vía Redis
    Redis::publish('video_control', json_encode([
        'action' => 'START',
        'camera_id' => $camera->id,
        'url' => $camera->stream_url,
        'config' => [
            'mode' => $camera->type, // 'traffic' o 'security'
            'detect_classes' => $camera->type === 'traffic' ? [2, 3, 5, 7] : [0], // COCO IDs: 2=car, 0=person
            'semantic_search' => true // Activar análisis de conceptos
        ]
    ]));

    return response()->json(['status' => 'Stream initiated']);
}



3. El Worker Python (El Cerebro Refactorizado)
Aquí es donde reutilizamos el código del repositorio pellit/RealtimeVideoAnalytics. En lugar de ejecutar el bucle directamente, creamos una clase CameraProcess que hereda de multiprocessing.Process.
Necesitarás instalar sentence-transformers y chromadb para la parte de "entender conceptos".
Archivo: worker_manager.py (Este reemplaza al main.py original)
Python
import redis
import json
import multiprocessing
from app.video_analytics import VideoAnalyticsProcess # Tu lógica adaptada del repo original

# Conexión a Redis (El mismo hostname que en docker-compose)
r = redis.Redis(host='redis', port=6379, decode_responses=True)

# Diccionario para guardar los procesos activos: { "camera_id": ProcessObj }
active_processes = {}

def handle_message(message):
    data = json.loads(message['data'])
    cam_id = str(data['camera_id'])
    action = data['action']

    if action == 'START':
        if cam_id in active_processes and active_processes[cam_id].is_alive():
            print(f"Cámara {cam_id} ya está corriendo.")
            return

        print(f"Iniciando análisis para cámara {cam_id} tipo {data['config']['mode']}")
        
        # Lanzamos el proceso pesado en un núcleo aparte
        # Pasamos la URL y la Configuración (qué detectar, si usar audio, etc.)
        proc = VideoAnalyticsProcess(
            cam_id=cam_id, 
            url=data['url'], 
            config=data['config']
        )
        proc.start()
        active_processes[cam_id] = proc

    elif action == 'STOP':
        if cam_id in active_processes:
            print(f"Deteniendo cámara {cam_id}")
            active_processes[cam_id].terminate() # Matar proceso
            del active_processes[cam_id]

def main():
    pubsub = r.pubsub()
    pubsub.subscribe('video_control')
    print("Worker Maestro esperando comandos de Laravel...")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            handle_message(message)

if __name__ == "__main__":
    main()



4. Implementando "Entender Conceptos" (La parte Novedosa)
Para que tu app no solo transcriba palabras sino que entienda el contexto (ej: alguien grita "¡Fuego!" y el sistema lo detecta como "Peligro"), integras esto en tu bucle de análisis.
Dentro de tu clase de procesamiento (video_analytics.py):
Python
from sentence_transformers import SentenceTransformer
import numpy as np

# Cargar modelo ligero de embeddings (se hace una vez al inicio del proceso)
semantic_model = SentenceTransformer('all-MiniLM-L6-v2')

# Conceptos de "Peligro" pre-calculados (Vectores de referencia)
danger_concepts = {
    "robo": semantic_model.encode("Someone is stealing robbery thief"),
    "accidente": semantic_model.encode("Car crash accident collision"),
    "ayuda": semantic_model.encode("Help me emergency scream")
}

def analyze_audio_semantics(text_transcript):
    """
    Convierte el texto transcribido a vector y lo compara con conceptos de peligro.
    """
    # 1. Tokenizar y Vectorizar lo que se dijo
    current_vector = semantic_model.encode(text_transcript)
    
    for concept_name, concept_vector in danger_concepts.items():
        # 2. Calcular similitud (Coseno)
        similarity = np.dot(current_vector, concept_vector) / (np.linalg.norm(current_vector) * np.linalg.norm(concept_vector))
        
        # 3. Si se parece más del 70%, disparar alerta
        if similarity > 0.7:
            return concept_name # Retorna "robo", "accidente", etc.
    
    return None


Cuando el sistema detecta una similitud alta, envía el evento a Redis: Redis::publish('alerts', ...) y Laravel lo muestra en Vue como una notificación roja.

5. Docker Compose Integrado
Este archivo une todo. Usaremos la imagen oficial de Laravel (o una custom con PHP) y tu worker de Python.
YAML
version: '3.8'

services:
  # --- BACKEND LARAVEL ---
  api:
    image: bitnami/laravel:10
    container_name: app_backend
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=db
      - REDIS_HOST=redis
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app
    networks:
      - saas_net

  # --- FRONTEND VUE ---
  frontend:
    image: node:18-alpine
    container_name: app_frontend
    working_dir: /app
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
    command: npm run dev
    networks:
      - saas_net

  # --- PYTHON AI WORKER ---
  ai_worker:
    build: 
      context: ./python_engine # Tu carpeta con el código python refactorizado
      dockerfile: Dockerfile
    container_name: ai_worker_1
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu] # Si tienes GPU, esto es vital
    environment:
      - REDIS_HOST=redis
      - YOUTUBE_DL_CACHE_DIR=/tmp/yt
    volumes:
      - ./python_engine/models:/models
    depends_on:
      - redis
    command: python worker_manager.py # Corre el script que escucha Redis
    networks:
      - saas_net

  # --- INFRAESTRUCTURA ---
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    networks:
      - saas_net

  db:
    image: postgres:15 # Postgres es mejor para vectores (pgvector)
    environment:
      POSTGRES_DB: video_saas
      POSTGRES_PASSWORD: secret
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - saas_net

networks:
  saas_net:

volumes:
  pg_data:


Resumen de Funcionalidades Logradas
Escalabilidad: Si necesitas analizar 50 cámaras, simplemente subes más contenedores ai_worker en otros servidores apuntando al mismo Redis.
Tokenización y Conceptos: Gracias a SentenceTransformers y la comparación vectorial, el sistema entiende que "¡Auxilio!" y "¡Ayuda!" son semánticamente lo mismo (concepto de peligro).
Análisis de Tráfico: Laravel le dice a Python "Modo Tráfico", y Python configura YOLO para filtrar solo coches/buses/camiones y contar flujo.
Seguridad: Laravel le dice "Modo Seguridad", y Python busca personas + comportamientos anómalos.
¿Por dónde empezar?
Crea el proyecto Laravel y configura la conexión a Redis.
Crea el script worker_manager.py en Python que simplemente imprima "Recibí orden START" cuando Laravel se lo mande.
Una vez conectados, mueve la lógica de YOLO del repo viejo dentro de la clase VideoAnalyticsProcess.
Label Studio es una herramienta visual muy potente. En tu arquitectura SaaS, su rol es el "Human in the Loop": sirve para que tú (o tus empleados) corrijan los errores que comete la IA para que esta aprenda.
Dado que ya lo tienes corriendo en el puerto 8081, aquí tienes la guía paso a paso para usarlo en tu flujo de trabajo de Active Learning (Reentrenamiento).

1. Acceso y Configuración Inicial
Entra a la web: Abre tu navegador en http://TU-IP-SERVIDOR:8081.
Crea cuenta: La primera vez te pedirá crear un usuario (email y contraseña). Este será el "Super Admin".
Crea un Proyecto:
Haz clic en el botón azul "Create Project".
Project Name: Ponle algo como Correcciones YOLO.
Description: "Imágenes donde la IA tuvo baja confianza".
2. Configurar la Interfaz de Etiquetado
Esta es la parte más importante. Debes decirle a Label Studio que vas a trabajar con Cajas (Bounding Boxes).
Dentro de la creación del proyecto, ve a la pestaña Labeling Setup.
Busca Computer Vision > Object Detection with Bounding Boxes.
Define tus etiquetas: Borra las que vienen por defecto (Airplane, etc.) y escribe las clases exactas que tu modelo YOLO usa.
Si usas el modelo estándar (yolov8n.pt), las clases más comunes son:
person
car
bus
truck
motorcycle
Dale a Save.
3. Importar Imágenes (El flujo de trabajo)
En tu sistema, el Worker de Python guardará las imágenes difíciles en una carpeta. Para etiquetarlas:
Haz clic en el botón azul Import.
Arrastra las imágenes desde tu carpeta local (o la carpeta que descargaste del servidor).
Dale a Import.
(Nota: Label Studio permite "sincronizar" carpetas locales del servidor automáticamente, pero requiere una configuración extra en Docker. Por ahora, la subida manual es más segura).
4. El Proceso de Etiquetado (Tu trabajo manual)
Haz clic en la primera imagen de la lista (Tasks).
Se abrirá el editor visual.
Herramientas:
Selecciona la etiqueta abajo (ej. person).
Presiona la tecla 1, 2, 3 para cambiar rápido de etiqueta.
Dibujar: Haz clic y arrastra sobre el objeto.
Guardar:
Si terminaste esa imagen, dale a Submit (o Ctrl + Enter).
Si quieres saltarla, dale a Skip.

Shutterstock
Explorar
5. Exportar para Reentrenar (El objetivo final)
Una vez que has corregido 50 o 100 imágenes, es hora de enseñarle al modelo.
Ve al botón Export (arriba a la derecha).
Formato: Selecciona YOLO.
Descargarás un archivo .zip.
¿Qué tiene ese ZIP inside?
/images: Tus fotos.
/labels: Archivos .txt con las coordenadas normalizadas que YOLO entiende.
classes.txt: La lista de nombres.

6. Cómo cerrar el ciclo (Reentrenamiento)
Ahora tienes datos nuevos y limpios. Para mejorar tu IA:
Sube ese .zip a tu entorno de desarrollo local (tu PC con GPU).
Descomprímelo.
Ejecuta un comando de entrenamiento de YOLO (como vimos antes):
Python
from ultralytics import YOLO

# Cargar el modelo que usas actualmente
model = YOLO('yolov8n.pt') 

# Entrenar con TUS correcciones
# (data.yaml es un archivo que debes crear apuntando a tus carpetas nuevas)
model.train(data='mis_correcciones/data.yaml', epochs=50)


Esto generará un nuevo archivo best.pt.
Reemplaza el archivo en ai_engine/models/yolov8n.pt en tu proyecto y haz Redeploy.
¡Tu IA ahora es un poco más inteligente gracias a Label Studio!


4. Implementando "Conceptos" y "Tokenización" (Fase 2)
Para la parte de análisis avanzado (buscar "accidentes", "peleas", etc.), necesitas agregar una base de datos vectorial al docker-compose.
Agrega el servicio:
YAML
chromadb:
  image: chromadb/chroma
  ports:
    - "8001:8000"
  networks:
    - app_net




Flujo de Tokenización:
Tu worker de Audio (Vosk) extrae texto: "Help me please".
Python genera un Embedding (vector numérico) de esa frase usando OpenAI o un modelo local (HuggingFace).
Guardas ese vector en ChromaDB.
Búsqueda en Laravel:
Usuario busca: "Situación de peligro".
Laravel convierte "Situación de peligro" a vector.
Consulta a ChromaDB por vectores similares.
ChromaDB devuelve el timestamp donde se dijo "Help me please" (porque semánticamente están cerca).
Resumen de Escalabilidad
¿Tienes 10 cámaras? Un solo contenedor ai_worker puede bastar.
¿Tienes 100 cámaras? Ejecutas docker-compose up -d --scale ai_worker=10. Docker creará 10 copias de tu código Python y se repartirán el trabajo de Redis automáticamente.
¿El Backend está lento? Laravel maneja miles de usuarios sin problema, pero el procesamiento pesado siempre ocurre en los workers de Python aislados.

-----

## 🔌 API Externa para Terceros

El sistema incluye una API REST que permite a **aplicaciones de terceros** enviar frames de video para análisis sin necesidad de configurar cámaras en el sistema.

### Autenticación

Las apps externas se autentican mediante **API Keys** que los usuarios pueden crear desde su dashboard.

```bash
# Header de autenticación
X-API-Key: va_xxxxxxxxxxxxxxxxxxxx

# O alternativa con Bearer
Authorization: Bearer va_xxxxxxxxxxxxxxxxxxxx
```

### Endpoints Disponibles

#### 📤 Enviar Frame para Análisis

```http
POST /api/external/analyze/frame
```

**Headers:**
```
X-API-Key: va_xxxxxxxxxxxx
Content-Type: application/json
```

**Body (JSON - Base64):**
```json
{
  "frame": "data:image/jpeg;base64,/9j/4AAQ...",
  "detections": ["person", "car", "truck"],
  "metadata": {
    "source": "mobile-app",
    "location": "entrance"
  }
}
```

**Body (Multipart - File Upload):**
```bash
curl -X POST http://tu-servidor.com/api/external/analyze/frame \
  -H "X-API-Key: va_xxxxxxxxxxxx" \
  -F "frame=@/path/to/image.jpg" \
  -F "detections[]=person" \
  -F "detections[]=car"
```

**Respuesta Exitosa:**
```json
{
  "success": true,
  "message": "Frame queued for analysis",
  "job_id": "ext_abc123_1701619200",
  "detections_requested": ["person", "car"]
}
```

#### 📤 Enviar Batch de Frames

```http
POST /api/external/analyze/batch
```

**Body:**
```json
{
  "frames": [
    {
      "frame": "base64_data_1...",
      "detections": ["person"]
    },
    {
      "frame": "base64_data_2...",
      "detections": ["car", "truck"]
    }
  ]
}
```

**Respuesta:**
```json
{
  "success": true,
  "message": "2 frames queued for analysis",
  "job_ids": ["ext_abc123_1", "ext_abc123_2"]
}
```

#### 📊 Ver Estado de la API Key

```http
GET /api/external/status
```

**Respuesta:**
```json
{
  "name": "Mi App Mobile",
  "requests_today": 150,
  "rate_limit": 1000,
  "remaining": 850,
  "permissions": ["analyze_frames", "batch_analysis"],
  "is_active": true
}
```

### Códigos de Error

| Código | Significado |
|--------|-------------|
| `401` | API Key inválida o faltante |
| `403` | API Key desactivada o sin permisos |
| `429` | Rate limit excedido (máx. requests/día) |
| `422` | Datos inválidos (frame vacío, formato incorrecto) |

**Ejemplo de Error:**
```json
{
  "error": "Rate limit exceeded",
  "message": "Daily limit of 1000 requests reached",
  "retry_after": "2024-12-04T00:00:00Z"
}
```

### Rate Limiting

Cada API Key tiene un límite diario configurable (default: 1000 requests/día). El contador se reinicia a medianoche UTC.

### Gestión de API Keys (Para Usuarios)

Los usuarios autenticados pueden gestionar sus API Keys:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/user/api-keys` | GET | Listar todas las API Keys |
| `/api/user/api-keys` | POST | Crear nueva API Key |
| `/api/user/api-keys/{id}` | DELETE | Eliminar API Key |
| `/api/user/api-keys/{id}/regenerate` | POST | Regenerar el token |
| `/api/user/api-keys/{id}/usage` | GET | Ver estadísticas de uso |

**Crear API Key:**
```bash
curl -X POST http://tu-servidor.com/api/user/api-keys \
  -H "Authorization: Bearer {user_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mi App Android",
    "rate_limit": 500,
    "permissions": ["analyze_frames"]
  }'
```

**Respuesta:**
```json
{
  "message": "API Key created successfully",
  "key": {
    "id": 1,
    "name": "Mi App Android",
    "key": "va_abc123xyz789...",
    "rate_limit": 500,
    "is_active": true
  },
  "warning": "Store this key securely. It won't be shown again."
}
```

### Panel de Administración

Los administradores pueden ver el uso de todas las API Keys desde el **AdminDashboard**:

- 📊 Total de requests del sistema
- 📈 Requests y frames procesados hoy
- 🔑 Lista de todas las API Keys con estadísticas
- ⚙️ Activar/Desactivar API Keys remotamente

**Endpoints Admin:**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/admin/api/overview` | GET | Estadísticas globales |
| `/api/admin/api/usage` | GET | Datos por día (últimos 30 días) |
| `/api/admin/api/keys` | GET | Todas las API Keys del sistema |
| `/api/admin/api/keys/{id}/toggle` | POST | Activar/Desactivar una key |

### Flujo de Procesamiento

```mermaid
sequenceDiagram
    participant App as App Tercero
    participant API as Laravel API
    participant Redis as Redis
    participant Worker as AI Worker
    
    App->>API: POST /external/analyze/frame
    API->>API: Validar API Key
    API->>API: Verificar Rate Limit
    API->>API: Registrar Usage Log
    API->>Redis: Publish to 'external_frames'
    API-->>App: 200 OK + job_id
    Redis->>Worker: Consume frame
    Worker->>Worker: YOLO Detection
    Worker->>Redis: Publish results
```

### Ejemplo Completo de Integración

```python
import requests
import base64

API_KEY = "va_your_api_key_here"
API_URL = "https://tu-servidor.com/api/external/analyze/frame"

# Leer imagen y convertir a base64
with open("frame.jpg", "rb") as f:
    frame_base64 = base64.b64encode(f.read()).decode()

# Enviar para análisis
response = requests.post(
    API_URL,
    headers={"X-API-Key": API_KEY},
    json={
        "frame": f"data:image/jpeg;base64,{frame_base64}",
        "detections": ["person", "car", "bicycle"],
        "metadata": {
            "camera_id": "cam_001",
            "timestamp": "2024-12-03T10:30:00Z"
        }
    }
)

print(response.json())
# {'success': True, 'job_id': 'ext_abc123_1701619200', ...}
```

```javascript
// JavaScript / Node.js
const fs = require('fs');
const axios = require('axios');

const API_KEY = 'va_your_api_key_here';
const API_URL = 'https://tu-servidor.com/api/external/analyze/frame';

const frame = fs.readFileSync('frame.jpg');
const frameBase64 = `data:image/jpeg;base64,${frame.toString('base64')}`;

axios.post(API_URL, {
  frame: frameBase64,
  detections: ['person', 'car']
}, {
  headers: { 'X-API-Key': API_KEY }
})
.then(res => console.log(res.data))
.catch(err => console.error(err.response.data));
```

-----