"""
MediaMTX Streamer Module
========================
Maneja el streaming de video hacia MediaMTX usando FFmpeg.
Soporta múltiples cámaras simultáneas.
"""

import os
import subprocess
import threading
import time
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum


class StreamStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class StreamInfo:
    camera_id: str
    rtsp_url: str
    width: int
    height: int
    fps: int
    status: StreamStatus
    process: Optional[subprocess.Popen]
    error_message: Optional[str] = None
    started_at: Optional[float] = None
    frames_sent: int = 0


class MediaMTXStreamer:
    """
    Gestiona streams FFmpeg hacia MediaMTX.
    Un proceso FFmpeg por cámara.
    """
    
    def __init__(self):
        self.streams: Dict[str, StreamInfo] = {}
        self.lock = threading.Lock()
        self.mediamtx_host = os.environ.get('MEDIAMTX_RTSP_URL', 'rtsp://media_server:8554')
        self.enabled = os.environ.get('MEDIAMTX_ENABLED', 'true').lower() == 'true'
        
        print(f"📡 MediaMTX Streamer initialized")
        print(f"   Host: {self.mediamtx_host}")
        print(f"   Enabled: {self.enabled}")
    
    def get_rtsp_url(self, camera_id: str) -> str:
        """Genera la URL RTSP para una cámara."""
        return f"{self.mediamtx_host}/live/camera_{camera_id}"
    
    def start_stream(
        self, 
        camera_id: str, 
        width: int, 
        height: int, 
        fps: int = 25
    ) -> bool:
        """
        Inicia un stream FFmpeg para una cámara.
        
        Args:
            camera_id: ID de la cámara
            width: Ancho del video
            height: Alto del video
            fps: Frames por segundo
            
        Returns:
            True si el stream se inició correctamente
        """
        if not self.enabled:
            print(f"⚠️ MediaMTX disabled, skipping stream for camera {camera_id}")
            return False
        
        with self.lock:
            # Si ya existe, detenerlo primero
            if camera_id in self.streams:
                self._stop_stream_internal(camera_id)
            
            rtsp_url = self.get_rtsp_url(camera_id)
            
            # Comando FFmpeg optimizado para baja latencia
            command = [
                'ffmpeg',
                '-y',
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-s', f'{width}x{height}',
                '-r', str(fps),
                '-i', '-',
                # Encoding
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-profile:v', 'baseline',
                '-level', '3.0',
                # Bitrate (ajustar según calidad deseada)
                '-b:v', '1500k',
                '-maxrate', '2000k',
                '-bufsize', '3000k',
                # GOP size (keyframe cada 2 segundos)
                '-g', str(fps * 2),
                '-keyint_min', str(fps),
                # Output
                '-f', 'rtsp',
                '-rtsp_transport', 'tcp',
                rtsp_url
            ]
            
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=10**6  # 1MB buffer
                )
                
                stream_info = StreamInfo(
                    camera_id=camera_id,
                    rtsp_url=rtsp_url,
                    width=width,
                    height=height,
                    fps=fps,
                    status=StreamStatus.RUNNING,
                    process=process,
                    started_at=time.time()
                )
                
                self.streams[camera_id] = stream_info
                
                print(f"✅ Stream started for camera {camera_id}")
                print(f"   RTSP URL: {rtsp_url}")
                print(f"   Resolution: {width}x{height} @ {fps}fps")
                
                # Iniciar thread de monitoreo
                threading.Thread(
                    target=self._monitor_stream,
                    args=(camera_id,),
                    daemon=True
                ).start()
                
                return True
                
            except Exception as e:
                print(f"❌ Error starting stream for camera {camera_id}: {e}")
                self.streams[camera_id] = StreamInfo(
                    camera_id=camera_id,
                    rtsp_url=rtsp_url,
                    width=width,
                    height=height,
                    fps=fps,
                    status=StreamStatus.ERROR,
                    process=None,
                    error_message=str(e)
                )
                return False
    
    def send_frame(self, camera_id: str, frame) -> bool:
        """
        Envía un frame al stream FFmpeg.
        
        Args:
            camera_id: ID de la cámara
            frame: Frame numpy array (BGR)
            
        Returns:
            True si el frame se envió correctamente
        """
        if not self.enabled:
            return False
        
        with self.lock:
            stream = self.streams.get(camera_id)
            
            if not stream or stream.status != StreamStatus.RUNNING:
                return False
            
            if stream.process is None or stream.process.poll() is not None:
                stream.status = StreamStatus.ERROR
                return False
            
            try:
                stream.process.stdin.write(frame.tobytes())
                stream.frames_sent += 1
                return True
            except (BrokenPipeError, IOError) as e:
                print(f"⚠️ Stream error for camera {camera_id}: {e}")
                stream.status = StreamStatus.ERROR
                stream.error_message = str(e)
                return False
    
    def stop_stream(self, camera_id: str) -> bool:
        """Detiene el stream de una cámara."""
        with self.lock:
            return self._stop_stream_internal(camera_id)
    
    def _stop_stream_internal(self, camera_id: str) -> bool:
        """Detiene el stream internamente (ya con lock)."""
        stream = self.streams.get(camera_id)
        if not stream:
            return False
        
        if stream.process:
            try:
                stream.process.stdin.close()
                stream.process.terminate()
                stream.process.wait(timeout=5)
            except Exception as e:
                print(f"⚠️ Error stopping stream {camera_id}: {e}")
                try:
                    stream.process.kill()
                except:
                    pass
        
        stream.status = StreamStatus.STOPPED
        print(f"🛑 Stream stopped for camera {camera_id}")
        return True
    
    def _monitor_stream(self, camera_id: str):
        """Thread que monitorea el estado del stream."""
        while True:
            time.sleep(5)
            
            with self.lock:
                stream = self.streams.get(camera_id)
                if not stream or stream.status == StreamStatus.STOPPED:
                    return
                
                if stream.process and stream.process.poll() is not None:
                    # Proceso terminó
                    stderr = ""
                    try:
                        stderr = stream.process.stderr.read().decode()
                    except:
                        pass
                    
                    print(f"⚠️ FFmpeg process died for camera {camera_id}")
                    if stderr:
                        print(f"   Error: {stderr[-500:]}")
                    
                    stream.status = StreamStatus.ERROR
                    stream.error_message = stderr[-200:] if stderr else "Process terminated"
                    return
    
    def get_status(self, camera_id: str = None) -> dict:
        """
        Obtiene el estado de los streams.
        
        Args:
            camera_id: Si se especifica, solo ese stream
            
        Returns:
            Dict con información de estado
        """
        with self.lock:
            if camera_id:
                stream = self.streams.get(camera_id)
                if not stream:
                    return {"error": "Stream not found"}
                return {
                    "camera_id": stream.camera_id,
                    "rtsp_url": stream.rtsp_url,
                    "status": stream.status.value,
                    "resolution": f"{stream.width}x{stream.height}",
                    "fps": stream.fps,
                    "frames_sent": stream.frames_sent,
                    "uptime": time.time() - stream.started_at if stream.started_at else 0,
                    "error": stream.error_message
                }
            
            return {
                "enabled": self.enabled,
                "mediamtx_host": self.mediamtx_host,
                "streams": {
                    cam_id: {
                        "status": s.status.value,
                        "rtsp_url": s.rtsp_url,
                        "frames_sent": s.frames_sent,
                        "error": s.error_message
                    }
                    for cam_id, s in self.streams.items()
                }
            }
    
    def stop_all(self):
        """Detiene todos los streams."""
        with self.lock:
            for camera_id in list(self.streams.keys()):
                self._stop_stream_internal(camera_id)
            print("🛑 All streams stopped")


# Singleton instance
_streamer_instance: Optional[MediaMTXStreamer] = None


def get_mediamtx_streamer() -> MediaMTXStreamer:
    """Obtiene la instancia singleton del streamer."""
    global _streamer_instance
    if _streamer_instance is None:
        _streamer_instance = MediaMTXStreamer()
    return _streamer_instance
