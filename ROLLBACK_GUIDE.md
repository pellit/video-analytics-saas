# 🔄 Guía de Rollback - Volver a Arquitectura MJPEG Legacy

## Información de Backup

| Concepto | Valor |
|----------|-------|
| **Tag de backup** | `v1.0-mjpeg-legacy` |
| **Rama legacy** | `development` |
| **Rama nueva** | `feature/mediamtx-hybrid-architecture` |
| **Fecha backup** | 5 de Diciembre 2025 |

---

## ⚡ Rollback Rápido (1 minuto)

Si algo falla con la nueva arquitectura MediaMTX:

```bash
# 1. Detener servicios actuales
cd /home/pta/video-analytics-saas/video-analytics-saas
docker-compose -f docker-compose.mediamtx.yml down

# 2. Volver a la rama development (legacy)
git checkout development

# 3. Levantar con docker-compose original
docker-compose up -d --build

# ¡Listo! El sistema vuelve a MJPEG
```

---

## 📋 Rollback Detallado

### Paso 1: Detener Servicios MediaMTX

```bash
# Detener todos los contenedores de la nueva arquitectura
docker-compose -f docker-compose.mediamtx.yml down -v

# Verificar que no queden contenedores
docker ps -a | grep -E "mediamtx|saas"
```

### Paso 2: Cambiar de Rama

```bash
# Volver a la rama development (versión legacy estable)
git checkout development

# O volver al tag específico
git checkout v1.0-mjpeg-legacy
```

### Paso 3: Reconstruir Servicios Legacy

```bash
# Limpiar imágenes anteriores (opcional)
docker system prune -f

# Reconstruir con docker-compose original
docker-compose build --no-cache
docker-compose up -d
```

### Paso 4: Verificar Funcionamiento

```bash
# Ver logs del worker
docker logs -f video-analytics-saas-ai_worker-1

# Probar endpoint MJPEG
curl -I http://localhost:5000/video_feed

# Probar API
curl http://localhost:8000/api/health
```

---

## 🔀 Diferencias Entre Arquitecturas

| Aspecto | Legacy (MJPEG) | Nueva (MediaMTX) |
|---------|----------------|------------------|
| **Docker Compose** | `docker-compose.yml` | `docker-compose.mediamtx.yml` |
| **Streaming** | MJPEG via Python | WebRTC/HLS via MediaMTX |
| **Dibujo cajas** | En servidor (CPU) | En cliente (GPU) |
| **Escalabilidad** | ~5-10 usuarios | ~100+ usuarios |
| **Latencia** | 500ms-2s | <100ms |
| **Puertos** | 5000 | 8888, 8889 |
| **Grabación** | Manual | Automática |

---

## 📁 Archivos Importantes

### Arquitectura Legacy (Rama: development)
```
docker-compose.yml          # Compose original sin MediaMTX
docker-compose.dev.yml      # Desarrollo sin MediaMTX
ai_engine/src/worker_manager.py  # Con endpoint /video_feed MJPEG
frontend/src/components/UserDashboard.vue  # Con <img> para MJPEG
```

### Arquitectura Nueva (Rama: feature/mediamtx-hybrid-architecture)
```
docker-compose.mediamtx.yml # Compose con MediaMTX
ai_engine/src/worker_manager.py  # Con FFmpeg push a RTSP
ai_engine/src/mediamtx_streamer.py  # Nuevo módulo streamer
frontend/src/components/SmartPlayer.vue  # Nuevo componente WebRTC
frontend/src/components/SystemHealth.vue # Panel de monitoreo
```

---

## 🛠️ Comandos Útiles

### Ver todas las ramas
```bash
git branch -a
```

### Ver todos los tags
```bash
git tag -l
```

### Comparar cambios entre ramas
```bash
git diff development feature/mediamtx-hybrid-architecture --stat
```

### Volver a un commit específico
```bash
# Ver historial
git log --oneline -20

# Volver a commit específico
git checkout <commit-hash>
```

---

## ⚠️ Notas Importantes

1. **Base de datos:** Los datos de MySQL se mantienen en el volumen `db_data`, no se pierden al cambiar de rama.

2. **Grabaciones:** Si usaste grabación en MediaMTX, los archivos están en `./recordings/`. No se borran automáticamente.

3. **Configuración:** Las variables de entorno en `.env` pueden diferir entre arquitecturas. Revisa antes de hacer rollback.

4. **Redis:** Los datos en Redis son efímeros. Se pierden al reiniciar pero no afectan funcionalidad.

---

## 📞 Soporte

Si tienes problemas con el rollback:

1. Verificar logs: `docker-compose logs -f`
2. Limpiar todo y empezar de cero:
   ```bash
   docker-compose down -v
   docker system prune -af
   git checkout development
   docker-compose up -d --build
   ```

---

*Documento creado: 5 de Diciembre 2025*
