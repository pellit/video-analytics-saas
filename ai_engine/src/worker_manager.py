import redis
import json
import time
import os

# Configuración Redis
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

def process_video(task_data):
    """Simulación del proceso de video (Aquí irá tu lógica YOLO)"""
    camera_id = task_data.get('camera_id')
    url = task_data.get('url')
    print(f"🎥 [WORKER] Iniciando análisis en Cámara {camera_id} ({url})")
    
    # Simular bucle de procesamiento
    # En el futuro, aquí instancias la clase VideoAnalyticsProcess
    for i in range(5):
        time.sleep(2)
        print(f"👁️ [WORKER] Detectando en cámara {camera_id}... Frame {i}")
        # Simular envío de evento a Laravel
        r.publish('camera_events', json.dumps({
            'camera_id': camera_id,
            'event': 'person_detected',
            'confidence': 0.95
        }))

def main():
    print(f"🚀 Worker de IA iniciado. Conectando a Redis en {REDIS_HOST}...")
    pubsub = r.pubsub()
    pubsub.subscribe('video_control')

    print("✅ Esperando comandos de Laravel en el canal 'video_control'...")

    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                data = json.loads(message['data'])
                print(f"📩 Mensaje recibido: {data}")
                
                if data.get('action') == 'START':
                    process_video(data)
                elif data.get('action') == 'STOP':
                    print(f"🛑 Deteniendo cámara {data.get('camera_id')}")
            except Exception as e:
                print(f"❌ Error procesando mensaje: {e}")

if __name__ == "__main__":
    main()
