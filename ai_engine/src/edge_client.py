"""
Edge Inference Client
=====================

Cliente para comunicarse con dispositivos edge (Jetson Nano, etc.)
que ejecutan la API de inferencia.

Permite al servidor principal delegar la detección a dispositivos edge
mientras mantiene el control del streaming y la interfaz.

Usage:
    from .edge_client import EdgeInferenceClient
    
    client = EdgeInferenceClient("http://jetson-nano:5050")
    
    # Detectar en un frame
    detections = await client.detect(frame)
    
    # Detectar múltiples frames
    results = await client.detect_batch(frames)
"""

import os
import asyncio
import base64
import time
import cv2
import numpy as np
import requests
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

# Optional: async HTTP client
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class EdgeDetection:
    """Detection result from edge device."""
    class_name: str
    class_id: int
    confidence: float
    bbox: Tuple[float, float, float, float]  # Normalized (x1, y1, x2, y2)
    bbox_pixels: Tuple[int, int, int, int]   # Pixels (x1, y1, x2, y2)


@dataclass 
class EdgeInferenceResult:
    """Complete inference result from edge device."""
    success: bool
    detections: List[EdgeDetection]
    count: int
    inference_time_ms: float
    model: str
    device: str
    image_size: Tuple[int, int]
    network_time_ms: float = 0  # Time spent in network transfer


class EdgeInferenceClient:
    """
    Client for edge inference API.
    
    Supports multiple edge devices with load balancing.
    Falls back to local inference if edge devices are unavailable.
    """
    
    def __init__(
        self,
        edge_urls: str | List[str],
        timeout: float = 5.0,
        max_retries: int = 2,
        fallback_local: bool = True
    ):
        """
        Initialize edge inference client.
        
        Args:
            edge_urls: URL(s) of edge inference API (e.g., "http://jetson:5050")
            timeout: Request timeout in seconds
            max_retries: Number of retries on failure
            fallback_local: Whether to fall back to local inference on failure
        """
        if isinstance(edge_urls, str):
            self.edge_urls = [edge_urls]
        else:
            self.edge_urls = edge_urls
        
        self.timeout = timeout
        self.max_retries = max_retries
        self.fallback_local = fallback_local
        
        # Track device health for load balancing
        self._device_health: Dict[str, Dict[str, Any]] = {}
        self._current_device_idx = 0
        
        # Async client (if available)
        self._async_client = None
        if HTTPX_AVAILABLE:
            self._async_client = httpx.AsyncClient(timeout=timeout)
        
        # Thread pool for sync operations
        self._executor = ThreadPoolExecutor(max_workers=4)
        
        # Initialize health status
        for url in self.edge_urls:
            self._device_health[url] = {
                "healthy": True,
                "last_check": 0,
                "avg_latency_ms": 0,
                "error_count": 0
            }
    
    def _encode_frame(self, frame: np.ndarray, quality: int = 85) -> str:
        """Encode frame to base64 JPEG."""
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buffer.tobytes()).decode('utf-8')
    
    def _get_best_device(self) -> str:
        """Get the best available edge device URL (round-robin with health check)."""
        healthy_devices = [
            url for url, health in self._device_health.items()
            if health["healthy"]
        ]
        
        if not healthy_devices:
            # All devices unhealthy, try the first one anyway
            return self.edge_urls[0]
        
        # Simple round-robin among healthy devices
        self._current_device_idx = (self._current_device_idx + 1) % len(healthy_devices)
        return healthy_devices[self._current_device_idx]
    
    def _update_device_health(self, url: str, success: bool, latency_ms: float = 0):
        """Update device health status."""
        health = self._device_health[url]
        
        if success:
            health["healthy"] = True
            health["error_count"] = 0
            # Exponential moving average for latency
            alpha = 0.3
            health["avg_latency_ms"] = (
                alpha * latency_ms + (1 - alpha) * health["avg_latency_ms"]
            )
        else:
            health["error_count"] += 1
            if health["error_count"] >= 3:
                health["healthy"] = False
        
        health["last_check"] = time.time()
    
    def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[str]] = None,
        max_detections: int = 100
    ) -> EdgeInferenceResult:
        """
        Detect objects in a frame using edge device.
        
        Args:
            frame: OpenCV image (BGR)
            confidence_threshold: Minimum confidence
            classes: Filter by class names
            max_detections: Maximum detections
            
        Returns:
            EdgeInferenceResult with detections
        """
        url = self._get_best_device()
        
        # Encode frame
        encode_start = time.perf_counter()
        image_b64 = self._encode_frame(frame)
        encode_time = (time.perf_counter() - encode_start) * 1000
        
        # Prepare request
        payload = {
            "image_base64": image_b64,
            "confidence_threshold": confidence_threshold,
            "max_detections": max_detections
        }
        if classes:
            payload["classes"] = classes
        
        # Send request with retries
        for attempt in range(self.max_retries + 1):
            try:
                network_start = time.perf_counter()
                response = requests.post(
                    f"{url}/detect",
                    json=payload,
                    timeout=self.timeout
                )
                network_time = (time.perf_counter() - network_start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Update health
                    self._update_device_health(url, True, network_time)
                    
                    # Parse detections
                    detections = [
                        EdgeDetection(
                            class_name=d["class_name"],
                            class_id=d["class_id"],
                            confidence=d["confidence"],
                            bbox=tuple(d["bbox"]),
                            bbox_pixels=tuple(d["bbox_pixels"])
                        )
                        for d in data["detections"]
                    ]
                    
                    return EdgeInferenceResult(
                        success=True,
                        detections=detections,
                        count=data["count"],
                        inference_time_ms=data["inference_time_ms"],
                        model=data["model"],
                        device=data["device"],
                        image_size=tuple(data["image_size"]),
                        network_time_ms=network_time
                    )
                else:
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
                    
            except Exception as e:
                self._update_device_health(url, False)
                
                if attempt < self.max_retries:
                    # Try another device
                    url = self._get_best_device()
                    continue
                
                # All retries failed
                if self.fallback_local:
                    return self._fallback_local_detect(frame, confidence_threshold, classes)
                else:
                    return EdgeInferenceResult(
                        success=False,
                        detections=[],
                        count=0,
                        inference_time_ms=0,
                        model="error",
                        device=url,
                        image_size=(frame.shape[1], frame.shape[0]),
                        network_time_ms=0
                    )
    
    async def detect_async(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        classes: Optional[List[str]] = None
    ) -> EdgeInferenceResult:
        """Async version of detect (requires httpx)."""
        if not HTTPX_AVAILABLE:
            # Fall back to sync version in thread
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor,
                lambda: self.detect(frame, confidence_threshold, classes)
            )
        
        url = self._get_best_device()
        image_b64 = self._encode_frame(frame)
        
        payload = {
            "image_base64": image_b64,
            "confidence_threshold": confidence_threshold
        }
        if classes:
            payload["classes"] = classes
        
        try:
            network_start = time.perf_counter()
            response = await self._async_client.post(f"{url}/detect", json=payload)
            network_time = (time.perf_counter() - network_start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                self._update_device_health(url, True, network_time)
                
                detections = [
                    EdgeDetection(
                        class_name=d["class_name"],
                        class_id=d["class_id"],
                        confidence=d["confidence"],
                        bbox=tuple(d["bbox"]),
                        bbox_pixels=tuple(d["bbox_pixels"])
                    )
                    for d in data["detections"]
                ]
                
                return EdgeInferenceResult(
                    success=True,
                    detections=detections,
                    count=data["count"],
                    inference_time_ms=data["inference_time_ms"],
                    model=data["model"],
                    device=data["device"],
                    image_size=tuple(data["image_size"]),
                    network_time_ms=network_time
                )
        except Exception as e:
            self._update_device_health(url, False)
            if self.fallback_local:
                return self._fallback_local_detect(frame, confidence_threshold, classes)
        
        return EdgeInferenceResult(
            success=False,
            detections=[],
            count=0,
            inference_time_ms=0,
            model="error",
            device=url,
            image_size=(frame.shape[1], frame.shape[0])
        )
    
    def detect_batch(
        self,
        frames: List[np.ndarray],
        confidence_threshold: float = 0.5,
        classes: Optional[List[str]] = None
    ) -> List[EdgeInferenceResult]:
        """
        Batch detection for multiple frames.
        
        More efficient than calling detect() multiple times.
        """
        url = self._get_best_device()
        
        # Encode all frames
        images_b64 = [self._encode_frame(f) for f in frames]
        
        payload = {
            "images": images_b64,
            "confidence_threshold": confidence_threshold
        }
        if classes:
            payload["classes"] = classes
        
        try:
            network_start = time.perf_counter()
            response = requests.post(
                f"{url}/detect/batch",
                json=payload,
                timeout=self.timeout * len(frames)
            )
            network_time = (time.perf_counter() - network_start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                self._update_device_health(url, True, network_time / len(frames))
                
                results = []
                for result_data in data["results"]:
                    detections = [
                        EdgeDetection(
                            class_name=d["class_name"],
                            class_id=d["class_id"],
                            confidence=d["confidence"],
                            bbox=tuple(d["bbox"]),
                            bbox_pixels=tuple(d["bbox_pixels"])
                        )
                        for d in result_data["detections"]
                    ]
                    
                    results.append(EdgeInferenceResult(
                        success=True,
                        detections=detections,
                        count=result_data["count"],
                        inference_time_ms=result_data["inference_time_ms"],
                        model=result_data["model"],
                        device=result_data["device"],
                        image_size=tuple(result_data["image_size"]),
                        network_time_ms=network_time / len(frames)
                    ))
                
                return results
        except Exception as e:
            self._update_device_health(url, False)
        
        # Return errors for all frames
        return [
            EdgeInferenceResult(
                success=False,
                detections=[],
                count=0,
                inference_time_ms=0,
                model="error",
                device=url,
                image_size=(f.shape[1], f.shape[0])
            )
            for f in frames
        ]
    
    def _fallback_local_detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float,
        classes: Optional[List[str]]
    ) -> EdgeInferenceResult:
        """Fall back to local detection if edge devices are unavailable."""
        try:
            from .models import get_detector
            
            detector = get_detector()
            if not hasattr(detector, '_loaded') or not detector._loaded:
                detector.load_model()
                detector._loaded = True
            
            start = time.perf_counter()
            results = detector.detect(frame, confidence=confidence_threshold)
            inference_time = (time.perf_counter() - start) * 1000
            
            h, w = frame.shape[:2]
            class_names = detector.get_class_names()
            
            detections = []
            for det in results:
                if hasattr(det, 'xyxy'):
                    for i in range(len(det.xyxy)):
                        class_id = int(det.class_id[i]) if det.class_id is not None else 0
                        conf = float(det.confidence[i]) if det.confidence is not None else 1.0
                        class_name = class_names[class_id] if class_id < len(class_names) else f"class_{class_id}"
                        
                        if classes and class_name not in classes:
                            continue
                        
                        x1, y1, x2, y2 = map(int, det.xyxy[i])
                        detections.append(EdgeDetection(
                            class_name=class_name,
                            class_id=class_id,
                            confidence=conf,
                            bbox=(x1/w, y1/h, x2/w, y2/h),
                            bbox_pixels=(x1, y1, x2, y2)
                        ))
            
            return EdgeInferenceResult(
                success=True,
                detections=detections,
                count=len(detections),
                inference_time_ms=inference_time,
                model="local_fallback",
                device="server",
                image_size=(w, h)
            )
        except Exception as e:
            print(f"⚠️ Local fallback detection failed: {e}")
            return EdgeInferenceResult(
                success=False,
                detections=[],
                count=0,
                inference_time_ms=0,
                model="error",
                device="server",
                image_size=(frame.shape[1], frame.shape[0])
            )
    
    def check_health(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Check health of an edge device."""
        if url is None:
            url = self._get_best_device()
        
        try:
            response = requests.get(f"{url}/health", timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                self._update_device_health(url, True)
                return {
                    "url": url,
                    "healthy": True,
                    **data
                }
        except Exception as e:
            self._update_device_health(url, False)
            return {
                "url": url,
                "healthy": False,
                "error": str(e)
            }
    
    def get_all_devices_status(self) -> List[Dict[str, Any]]:
        """Get status of all edge devices."""
        results = []
        for url in self.edge_urls:
            results.append(self.check_health(url))
        return results
    
    async def close(self):
        """Close async client."""
        if self._async_client:
            await self._async_client.aclose()
        self._executor.shutdown(wait=False)


# Singleton instance (configured via environment)
_edge_client: Optional[EdgeInferenceClient] = None


def get_edge_client() -> Optional[EdgeInferenceClient]:
    """Get configured edge inference client."""
    global _edge_client
    
    if _edge_client is not None:
        return _edge_client
    
    # Check if edge inference is enabled
    edge_urls = os.environ.get('EDGE_INFERENCE_URLS', '')
    if not edge_urls:
        # Also check for single URL
        single_url = os.environ.get('JETSON_INFERENCE_URL', '')
        if single_url:
            edge_urls = single_url
    
    if not edge_urls:
        return None
    
    # Parse URLs (comma-separated)
    urls = [u.strip() for u in edge_urls.split(',') if u.strip()]
    
    if not urls:
        return None
    
    _edge_client = EdgeInferenceClient(
        edge_urls=urls,
        timeout=float(os.environ.get('EDGE_INFERENCE_TIMEOUT', '5.0')),
        fallback_local=os.environ.get('EDGE_FALLBACK_LOCAL', 'true').lower() == 'true'
    )
    
    print(f"✅ Edge inference client configured for: {urls}")
    return _edge_client
