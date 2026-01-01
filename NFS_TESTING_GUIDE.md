# 🧪 Guía de Testing - NFS Implementation

**Fecha:** 1 de enero de 2026

---

## 1️⃣ Setup Inicial

### 1.1 Verificar que el código está en la rama correcta

```bash
cd /home/pta/video-analytics-saas
git branch -a
# Debe mostrar: * feature/mediamtx-hybrid-architecture
```

### 1.2 Compilar el código para verificar sintaxis

```bash
python3 -m py_compile ai_engine/src/inference_api.py
echo "✅ Syntax check passed"
```

### 1.3 Crear carpeta de logs

```bash
mkdir -p /home/pta/video-analytics-saas/logs
chmod 755 /home/pta/video-analytics-saas/logs
```

---

## 2️⃣ Test 1: Health Check al Iniciar

### 2.1 Iniciar la API

```bash
cd /home/pta/video-analytics-saas
python3 -m uvicorn ai_engine.src.inference_api:app \
  --host 0.0.0.0 \
  --port 5050 \
  --reload
```

### 2.2 Buscar el output esperado

En la consola debes ver:

```
🚀 Starting Inference API...
🔍 NFS HEALTH CHECK
======================================================================
👤 Running as user: root
✅ NFS mounts detected:
   (lista de montajes NFS)
📂 NFS_MEDIA_ROOT: /home/pta/pta-app/media
✅ Demo videos directory exists
   📹 Videos found: X
======================================================================
```

### 2.3 Verificar archivo de logs

```bash
tail -20 logs/nfs_analyzer.log

# Esperado:
# 📋 NFS Analyzer initialized...
# 🔍 NFS HEALTH CHECK
# 👤 Running as user: root
# ✅ NFS mounts detected:
```

---

## 3️⃣ Test 2: Validación de Rutas

### 3.1 Test 2A: File Path Válido

```bash
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/pta/pta-app/media/demo_videos/test.mp4",
    "frame_stride": 1,
    "max_frames": 1800,
    "hit_threshold": 0.1,
    "return_images": false
  }'
```

**Esperado:**
- Status: 200
- Logs muestren: `✅ ALL VALIDATIONS PASSED`
- Análisis del video completo

### 3.2 Test 2B: File Path No Encontrado

```bash
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/pta/pta-app/media/demo_videos/noexiste.mp4",
    "frame_stride": 1,
    "max_frames": 1800,
    "hit_threshold": 0.1,
    "return_images": false
  }'
```

**Esperado:**
- Status: 404
- Error: "Video path not found"
- Logs muestren:
  ```
  ❌ FILE NOT FOUND: /home/pta/pta-app/media/demo_videos/noexiste.mp4
  📋 NFS Mounts:
     (lista de montajes)
  📋 Directory listing:
     (archivos que sí existen)
  ```

### 3.3 Test 2C: Path Traversal Prevention

```bash
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "../../../../etc/passwd",
    "frame_stride": 1,
    "max_frames": 1800,
    "hit_threshold": 0.1,
    "return_images": false
  }'
```

**Esperado:**
- Status: 400
- Error: "Invalid file_path - path traversal not allowed"
- Logs muestren:
  ```
  ❌ SECURITY VIOLATION: Path traversal attempt detected
  candidate: ...
  base_dir: /home/pta/pta-app/media
  ```

### 3.4 Test 2D: File Path Vacío

```bash
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "",
    "frame_stride": 1,
    "max_frames": 1800,
    "hit_threshold": 0.1,
    "return_images": false
  }'
```

**Esperado:**
- Status: 400
- Error: "file_path is required"

---

## 4️⃣ Test 3: Logging Detallado

### 3.1 Monitorear logs en tiempo real

```bash
# En terminal 1: Iniciar API
python3 -m uvicorn ai_engine.src.inference_api:app --host 0.0.0.0 --port 5050

# En terminal 2: Monitorear logs
tail -f logs/nfs_analyzer.log
```

### 3.2 Hacer un request

```bash
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/pta/pta-app/media/demo_videos/test.mp4",
    "frame_stride": 1,
    "max_frames": 100,
    "hit_threshold": 0.1,
    "return_images": false
  }'
```

### 3.3 Verificar en logs

Debes ver:

```
=====================================================================
🎬 DETECT HIT FAST FROM NFS VIDEO
=====================================================================
📥 NFS request received
   file_path: /home/pta/pta-app/media/demo_videos/test.mp4
   frame_stride: 1
   max_frames: 100
   hit_threshold: 0.1
   return_images: false

==========================================================================
🔍 NFS VIDEO PATH RESOLUTION
==========================================================================
📥 Request received
   file_path: /home/pta/pta-app/media/demo_videos/test.mp4
   ...
   ✓ file_path provided
   ✓ Path traversal protection OK
   ✓ Checking file existence...
   ✓ File exists
   ✓ Checking read permissions...
   ✓ Read permission OK
   ℹ File size: 125.45MB
   ✓ File is not empty
==========================================================================
✅ ALL VALIDATIONS PASSED
==========================================================================

✅ Path validated and resolved to: /home/pta/pta-app/media/demo_videos/test.mp4
🎯 Starting hit detection analysis...
✅ Analysis completed successfully in 12.45s
=====================================================================
```

---

## 5️⃣ Test 4: Casos de Error

### 4.1 Montar NFS (si no está)

```bash
# En servidor de análisis (API server)
sudo mount -t nfs <IP_SERVIDOR>:/home/pta/pta-app/media /home/pta/pta-app/media

# Verificar
mount | grep nfs
```

### 4.2 Test sin NFS montada

Desmontar NFS:
```bash
sudo umount /home/pta/pta-app/media
```

Hacer request:
```bash
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/home/pta/pta-app/media/demo_videos/test.mp4"}'
```

Verificar logs:
```bash
tail logs/nfs_analyzer.log | grep -A 10 "FILE NOT FOUND"
# Debe mostrar:
# ❌ FILE NOT FOUND
# 📋 NFS Mounts:
#    ⚠️ No NFS mounts found!
```

### 4.3 Test sin permisos de lectura

```bash
# Cambiar permisos (como root)
sudo chmod 000 /home/pta/pta-app/media/demo_videos/test.mp4

# Hacer request
curl -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/home/pta/pta-app/media/demo_videos/test.mp4"}'

# Restaurar permisos
sudo chmod 644 /home/pta/pta-app/media/demo_videos/test.mp4
```

Verificar logs:
```bash
tail logs/nfs_analyzer.log | grep -A 5 "PERMISSION DENIED"
```

---

## 6️⃣ Test 5: Análisis de Performance

### 5.1 Medir tiempo de ejecución

```bash
curl -w "\nTotal time: %{time_total}s\n" \
  -X POST http://localhost:5050/detect/hit/fast/nfs/video \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/pta/pta-app/media/demo_videos/test.mp4",
    "frame_stride": 1,
    "max_frames": 1800,
    "hit_threshold": 0.1,
    "return_images": false
  }'
```

### 5.2 Comparar con upload HTTP

Medir tiempo con endpoint tradicional (con upload):
```bash
curl -w "\nUpload HTTP time: %{time_total}s\n" \
  -X POST http://localhost:5050/detect/hit/fast/video \
  -F "file=@/home/pta/pta-app/media/demo_videos/test.mp4" \
  -F "frame_stride=1" \
  -F "max_frames=1800"
```

**Esperado:** NFS debe ser 40-60% más rápido

---

## 7️⃣ Test 6: Búsqueda de Errores en Logs

### 6.1 Ver todos los errores

```bash
grep "❌" logs/nfs_analyzer.log
```

### 6.2 Ver todas las validaciones exitosas

```bash
grep "✅" logs/nfs_analyzer.log
```

### 6.3 Ver advertencias

```bash
grep "⚠️" logs/nfs_analyzer.log
```

### 6.4 Contar requests

```bash
grep -c "🎬 DETECT HIT FAST FROM NFS VIDEO" logs/nfs_analyzer.log
```

---

## 8️⃣ Test 7: Estrés (Múltiples Requests)

### 7.1 Script de testing

```bash
#!/bin/bash
for i in {1..5}; do
  echo "Request $i..."
  curl -s -X POST http://localhost:5050/detect/hit/fast/nfs/video \
    -H "Content-Type: application/json" \
    -d '{
      "file_path": "/home/pta/pta-app/media/demo_videos/test.mp4",
      "frame_stride": 1,
      "max_frames": 100,
      "hit_threshold": 0.1,
      "return_images": false
    }' | jq '.success'
  sleep 2
done
```

### 7.2 Ejecutar

```bash
chmod +x test_nfs.sh
./test_nfs.sh
```

### 7.3 Verificar en logs

```bash
# Contar requests completados
grep -c "ALL VALIDATIONS PASSED" logs/nfs_analyzer.log

# Contar errors
grep -c "❌" logs/nfs_analyzer.log
```

---

## 9️⃣ Checklist Final

- [ ] Health check en startup muestra NFS mounts
- [ ] Archivos válidos se analizan correctamente (Status 200)
- [ ] Archivos no encontrados retornan 404 con diagnóstico
- [ ] Path traversal es bloqueado (Status 400)
- [ ] Sin permisos retorna 403
- [ ] Logs se crean en `logs/nfs_analyzer.log`
- [ ] Tiempo total es 40-60% más rápido que HTTP upload
- [ ] Múltiples requests funcionan sin errores
- [ ] Errores tienen información diagnóstica útil

---

## 🚀 Conclusión

Si todos los tests pasan, la implementación NFS está **COMPLETAMENTE FUNCIONAL** ✅

Ventajas implementadas:
- ⚡ 40-60% más rápido (sin subir archivo)
- 💚 Menor consumo de ancho de banda
- 🔄 Mejor para archivos grandes (>100MB)
- 📋 Logging detallado para debugging
- 🔒 Path traversal protection
- 🏥 Health check en startup
- 📊 Diagnósticos automáticos de errores
