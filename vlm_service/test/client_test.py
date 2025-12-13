import requests
import base64
import json

# Configuración
API_URL = "http://localhost:5100"
IMAGE_PATH = "prueba.jpg"  # Asegúrate de tener una imagen aquí

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def test_analyze():
    print("--- Probando /analyze ---")
    b64_img = encode_image(IMAGE_PATH)
    
    payload = {
        "image_base64": b64_img,
        "prompt": "Describe this image in detail.",
        # "prompt_key": "general_describe" # Opcional
    }
    
    try:
        response = requests.post(f"{API_URL}/analyze", json=payload)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Éxito ({data['processing_time_ms']:.0f}ms):")
            print(data['response'])
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error de conexión: {e}")

def test_analyze_url():
    print("\n--- Probando /analyze-url ---")
    payload = {
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
        "prompt": "What objects are in this image?"
    }
    
    response = requests.post(f"{API_URL}/analyze-url", json=payload)
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    # Primero verificamos salud
    health = requests.get(f"{API_URL}/health").json()
    print(f"Estado del servicio: {health}")
    
    test_analyze()
    test_analyze_url()
    
    
# curl -X POST "http://localhost:5100/analyze-url" \
#      -H "Content-Type: application/json" \
#      -d '{
#            "image_url": "https://cdn.pixabay.com/photo/2015/04/23/22/00/tree-736885_1280.jpg",
#            "prompt": "Describe the lighting in this image."
#          }'