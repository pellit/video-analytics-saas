"""
VLM Service - FastAPI Server
=============================

Microservicio independiente para análisis de imágenes con Moondream2.

Endpoints:
- POST /analyze: Analiza imagen (base64) con prompt
- POST /analyze-url: Analiza imagen desde URL
- GET /health: Health check
- GET /status: Estado detallado del servicio
- GET /prompts: Lista prompts predefinidos

Redis:
- Subscribe: vlm_requests (para procesamiento asíncrono)
- Publish: vlm_response_{request_id}
"""

import os
import json
import base64
import threading
import time
from io import BytesIO
from typing import Optional, Dict, Any, List

import cv2
import numpy as np
import redis
import requests
from PIL import Image
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .vlm_engine import MoondreamAnalyzer, get_prompt, list_prompts, PREDEFINED_PROMPTS

# ============================================================================
# Configuration
# ============================================================================

REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
VLM_MODEL = os.environ.get('VLM_MODEL', 'vikhyatk/moondream2')
VLM_REVISION = os.environ.get('VLM_REVISION', '2024-08-26')
LAZY_LOAD = os.environ.get('VLM_LAZY_LOAD', 'true').lower() == 'true'
PRELOAD_MODEL = os.environ.get('VLM_PRELOAD', 'false').lower() == 'true'

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="VLM Service",
    description="Vision Language Model microservice using Moondream2",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Global State
# ============================================================================

vlm_analyzer: Optional[MoondreamAnalyzer] = None
redis_client: Optional[redis.Redis] = None

# ============================================================================
# Request/Response Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Request para analizar imagen con base64"""
    image_base64: str = Field(..., description="Imagen codificada en base64")
    prompt: str = Field(..., description="Prompt o pregunta para el análisis")
    prompt_key: Optional[str] = Field(None, description="Clave de prompt predefinido (opcional)")

class AnalyzeUrlRequest(BaseModel):
    """Request para analizar imagen desde URL"""
    image_url: str = Field(..., description="URL de la imagen")
    prompt: str = Field(..., description="Prompt o pregunta para el análisis")
    prompt_key: Optional[str] = Field(None, description="Clave de prompt predefinido (opcional)")

class AnalyzeResponse(BaseModel):
    """Response del análisis"""
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None

class StatusResponse(BaseModel):
    """Response de estado del servicio"""
    enabled: bool
    loaded: bool
    loading: bool
    model: str
    revision: str
    error: Optional[str] = None
    prompts_available: int

class HealthResponse(BaseModel):
    """Response de health check"""
    status: str
    model_loaded: bool
    redis_connected: bool

# ============================================================================
# Helper Functions
# ============================================================================

def get_vlm_analyzer() -> MoondreamAnalyzer:
    """Obtiene o crea la instancia del analizador VLM."""
    global vlm_analyzer
    if vlm_analyzer is None:
        vlm_analyzer = MoondreamAnalyzer(model_id=VLM_MODEL, revision=VLM_REVISION)
    return vlm_analyzer

def get_redis_client() -> Optional[redis.Redis]:
    """Obtiene o crea la conexión Redis."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True
            )
            redis_client.ping()
            print(f"✅ Conectado a Redis: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            print(f"⚠️ No se pudo conectar a Redis: {e}")
            redis_client = None
    return redis_client

def decode_base64_image(base64_str: str) -> np.ndarray:
    """Decodifica imagen base64 a numpy array."""
    # Remove header if present
    if ',' in base64_str:
        base64_str = base64_str.split(',')[1]
    
    img_data = base64.b64decode(base64_str)
    img_array = np.frombuffer(img_data, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("No se pudo decodificar la imagen")
    
    return img

def download_image(url: str) -> np.ndarray:
    """Descarga imagen desde URL."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    img_array = np.frombuffer(response.content, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("No se pudo decodificar la imagen de la URL")
    
    return img

def resolve_prompt(prompt: str, prompt_key: Optional[str]) -> str:
    """Resuelve el prompt, usando prompt_key si está disponible."""
    if prompt_key:
        predefined = get_prompt(prompt_key)
        if predefined:
            return predefined
    return prompt

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    analyzer = get_vlm_analyzer()
    r = get_redis_client()
    
    return HealthResponse(
        status="ok",
        model_loaded=analyzer.is_loaded(),
        redis_connected=r is not None
    )

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Estado detallado del servicio."""
    analyzer = get_vlm_analyzer()
    status = analyzer.get_status()
    
    return StatusResponse(
        enabled=True,
        loaded=status["loaded"],
        loading=status["loading"],
        model=status["model_id"],
        revision=status["revision"],
        error=status["error"],
        prompts_available=len(PREDEFINED_PROMPTS)
    )

@app.get("/prompts")
async def get_prompts() -> Dict[str, str]:
    """Lista todos los prompts predefinidos disponibles."""
    return list_prompts()

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(request: AnalyzeRequest):
    """
    Analiza una imagen codificada en base64.
    
    - **image_base64**: Imagen en formato base64
    - **prompt**: Pregunta o instrucción para el análisis
    - **prompt_key**: (Opcional) Clave de prompt predefinido
    """
    start_time = time.time()
    
    try:
        # Decodificar imagen
        image = decode_base64_image(request.image_base64)
        
        # Resolver prompt
        prompt = resolve_prompt(request.prompt, request.prompt_key)
        
        # Analizar
        analyzer = get_vlm_analyzer()
        response = analyzer.analyze_image(image, prompt)
        
        # Verificar errores
        if response.startswith("Error:"):
            return AnalyzeResponse(
                success=False,
                error=response,
                processing_time_ms=(time.time() - start_time) * 1000
            )
        
        return AnalyzeResponse(
            success=True,
            response=response,
            processing_time_ms=(time.time() - start_time) * 1000
        )
        
    except Exception as e:
        return AnalyzeResponse(
            success=False,
            error=str(e),
            processing_time_ms=(time.time() - start_time) * 1000
        )

@app.post("/analyze-url", response_model=AnalyzeResponse)
async def analyze_image_url(request: AnalyzeUrlRequest):
    """
    Analiza una imagen desde una URL.
    
    - **image_url**: URL de la imagen a analizar
    - **prompt**: Pregunta o instrucción para el análisis
    - **prompt_key**: (Opcional) Clave de prompt predefinido
    """
    start_time = time.time()
    
    try:
        # Descargar imagen
        image = download_image(request.image_url)
        
        # Resolver prompt
        prompt = resolve_prompt(request.prompt, request.prompt_key)
        
        # Analizar
        analyzer = get_vlm_analyzer()
        response = analyzer.analyze_image(image, prompt)
        
        # Verificar errores
        if response.startswith("Error:"):
            return AnalyzeResponse(
                success=False,
                error=response,
                processing_time_ms=(time.time() - start_time) * 1000
            )
        
        return AnalyzeResponse(
            success=True,
            response=response,
            processing_time_ms=(time.time() - start_time) * 1000
        )
        
    except Exception as e:
        return AnalyzeResponse(
            success=False,
            error=str(e),
            processing_time_ms=(time.time() - start_time) * 1000
        )

@app.post("/preload")
async def preload_model(background_tasks: BackgroundTasks):
    """
    Pre-carga el modelo VLM en background.
    Útil para calentar el servicio antes de usarlo.
    """
    analyzer = get_vlm_analyzer()
    
    if analyzer.is_loaded():
        return {"status": "already_loaded", "message": "El modelo ya está cargado"}
    
    if analyzer.is_loading():
        return {"status": "loading", "message": "El modelo está cargando"}
    
    # Cargar en background
    background_tasks.add_task(analyzer.ensure_loaded)
    
    return {"status": "started", "message": "Carga del modelo iniciada en background"}

# ============================================================================
# Redis Async Processing
# ============================================================================

def process_redis_request(data: dict):
    """Procesa una solicitud recibida por Redis."""
    request_id = data.get('request_id')
    reply_channel = data.get('reply_channel', f'vlm_response_{request_id}')
    
    try:
        image_base64 = data.get('image_base64')
        image_url = data.get('image_url')
        prompt = data.get('prompt', 'Describe this image.')
        prompt_key = data.get('prompt_key')
        
        # Obtener imagen
        if image_base64:
            image = decode_base64_image(image_base64)
        elif image_url:
            image = download_image(image_url)
        else:
            raise ValueError("Se requiere image_base64 o image_url")
        
        # Resolver prompt
        prompt = resolve_prompt(prompt, prompt_key)
        
        # Analizar
        analyzer = get_vlm_analyzer()
        response = analyzer.analyze_image(image, prompt)
        
        # Publicar respuesta
        r = get_redis_client()
        if r:
            r.publish(reply_channel, json.dumps({
                'request_id': request_id,
                'success': not response.startswith("Error:"),
                'response': response if not response.startswith("Error:") else None,
                'error': response if response.startswith("Error:") else None
            }))
            
    except Exception as e:
        r = get_redis_client()
        if r:
            r.publish(reply_channel, json.dumps({
                'request_id': request_id,
                'success': False,
                'error': str(e)
            }))

def redis_listener_loop():
    """Loop que escucha solicitudes en Redis."""
    r = get_redis_client()
    if r is None:
        print("⚠️ Redis no disponible, listener deshabilitado")
        return
    
    pubsub = r.pubsub()
    pubsub.subscribe('vlm_requests')
    
    print("👂 Escuchando Redis 'vlm_requests'...")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                data = json.loads(message['data'])
                print(f"📩 VLM request recibido: {data.get('request_id', 'unknown')}")
                
                # Procesar en thread separado
                threading.Thread(
                    target=process_redis_request,
                    args=(data,),
                    daemon=True
                ).start()
                
            except Exception as e:
                print(f"❌ Error procesando mensaje Redis: {e}")

# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Evento de inicio del servicio."""
    print("🚀 VLM Service iniciando...")
    print(f"   Model: {VLM_MODEL}")
    print(f"   Revision: {VLM_REVISION}")
    print(f"   Lazy Load: {LAZY_LOAD}")
    print(f"   Redis: {REDIS_HOST}:{REDIS_PORT}")
    
    # Inicializar conexión Redis
    get_redis_client()
    
    # Iniciar listener Redis en thread separado
    threading.Thread(target=redis_listener_loop, daemon=True).start()
    
    # Pre-cargar modelo si está configurado
    if PRELOAD_MODEL:
        print("⏳ Pre-cargando modelo VLM...")
        analyzer = get_vlm_analyzer()
        threading.Thread(target=analyzer.ensure_loaded, daemon=True).start()
    
    print("✅ VLM Service listo")

@app.on_event("shutdown")
async def shutdown_event():
    """Evento de cierre del servicio."""
    print("👋 VLM Service cerrando...")
