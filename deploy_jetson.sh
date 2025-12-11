#!/bin/bash
# =============================================================
# Script de Deploy para Jetson Nano
# =============================================================
#
# Este script prepara y despliega la API de inferencia en una Jetson Nano.
#
# USO:
#   ./deploy_jetson.sh <jetson-ip> [jetson-user]
#
# EJEMPLO:
#   ./deploy_jetson.sh 192.168.1.100 jetson
#
# REQUISITOS EN JETSON:
#   - JetPack SDK instalado
#   - Docker con nvidia-runtime
#   - SSH habilitado
#
# =============================================================

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funciones de log
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verificar argumentos
if [ -z "$1" ]; then
    echo "Uso: $0 <jetson-ip> [jetson-user]"
    echo ""
    echo "Ejemplo: $0 192.168.1.100 jetson"
    exit 1
fi

JETSON_IP="$1"
JETSON_USER="${2:-jetson}"
REMOTE_DIR="~/inference"

log_info "Desplegando en Jetson Nano: ${JETSON_USER}@${JETSON_IP}"
echo ""

# ============================================================
# 1. Verificar conectividad
# ============================================================
log_info "Verificando conexión SSH..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" "echo 'SSH OK'" &>/dev/null; then
    log_error "No se puede conectar a ${JETSON_USER}@${JETSON_IP}"
    log_warn "Asegúrate de tener configurada la autenticación SSH (ssh-copy-id)"
    exit 1
fi
log_success "Conexión SSH establecida"

# ============================================================
# 2. Verificar Docker en Jetson
# ============================================================
log_info "Verificando Docker en Jetson..."
if ! ssh "${JETSON_USER}@${JETSON_IP}" "docker --version" &>/dev/null; then
    log_error "Docker no está instalado en la Jetson"
    log_warn "Instala docker con: sudo apt-get install -y docker.io nvidia-docker2"
    exit 1
fi
log_success "Docker disponible"

# Verificar nvidia runtime
if ssh "${JETSON_USER}@${JETSON_IP}" "docker info 2>/dev/null | grep -q nvidia"; then
    log_success "NVIDIA runtime disponible"
else
    log_warn "NVIDIA runtime no detectado (puede estar ok si usas docker-compose)"
fi

# ============================================================
# 3. Crear directorio remoto
# ============================================================
log_info "Creando directorio remoto..."
ssh "${JETSON_USER}@${JETSON_IP}" "mkdir -p ${REMOTE_DIR}"
log_success "Directorio ${REMOTE_DIR} creado"

# ============================================================
# 4. Transferir archivos
# ============================================================
log_info "Transfiriendo archivos... (esto puede tomar un momento)"

# Lista de archivos a transferir
FILES_TO_TRANSFER=(
    "docker-compose.jetson.yml"
    "ai_engine/Dockerfile.jetson"
    "ai_engine/requirements.jetson.txt"
    "ai_engine/src/__init__.py"
    "ai_engine/src/inference_api.py"
    "ai_engine/src/models/"
    "ai_engine/models/"
)

# Crear estructura de directorios en remoto
ssh "${JETSON_USER}@${JETSON_IP}" "mkdir -p ${REMOTE_DIR}/ai_engine/src ${REMOTE_DIR}/ai_engine/models"

# Transferir cada archivo/directorio
for item in "${FILES_TO_TRANSFER[@]}"; do
    if [ -e "$item" ]; then
        log_info "  → $item"
        scp -r "$item" "${JETSON_USER}@${JETSON_IP}:${REMOTE_DIR}/${item%/*}/" 2>/dev/null || \
        scp -r "$item" "${JETSON_USER}@${JETSON_IP}:${REMOTE_DIR}/$item" 2>/dev/null || true
    else
        log_warn "  ⚠ $item no existe (ignorando)"
    fi
done

# Transferir docker-compose al directorio raíz de inference
scp docker-compose.jetson.yml "${JETSON_USER}@${JETSON_IP}:${REMOTE_DIR}/docker-compose.yml"

log_success "Archivos transferidos"

# ============================================================
# 5. Construir imagen Docker
# ============================================================
log_info "Construyendo imagen Docker en Jetson... (esto puede tomar varios minutos)"
ssh "${JETSON_USER}@${JETSON_IP}" "cd ${REMOTE_DIR} && docker-compose build --no-cache" || {
    log_error "Error construyendo imagen Docker"
    log_warn "Revisa los logs con: ssh ${JETSON_USER}@${JETSON_IP} 'cd ${REMOTE_DIR} && docker-compose logs'"
    exit 1
}
log_success "Imagen Docker construida"

# ============================================================
# 6. Iniciar servicio
# ============================================================
log_info "Iniciando servicio de inferencia..."
ssh "${JETSON_USER}@${JETSON_IP}" "cd ${REMOTE_DIR} && docker-compose up -d"
log_success "Servicio iniciado"

# ============================================================
# 7. Verificar funcionamiento
# ============================================================
log_info "Esperando a que el servicio esté listo..."
sleep 10

# Intentar health check
for i in {1..6}; do
    if ssh "${JETSON_USER}@${JETSON_IP}" "curl -sf http://localhost:5050/health" &>/dev/null; then
        log_success "¡Servicio funcionando correctamente!"
        break
    fi
    
    if [ $i -eq 6 ]; then
        log_warn "El servicio aún no responde. Puede estar cargando el modelo."
        log_info "Verifica manualmente con: curl http://${JETSON_IP}:5050/health"
    else
        log_info "Esperando... (intento $i/6)"
        sleep 10
    fi
done

# ============================================================
# 8. Mostrar resumen
# ============================================================
echo ""
echo "============================================================"
echo -e "${GREEN}¡Deploy completado!${NC}"
echo "============================================================"
echo ""
echo "API de Inferencia disponible en:"
echo -e "  ${BLUE}http://${JETSON_IP}:5050${NC}"
echo ""
echo "Endpoints:"
echo "  - GET  /health         - Health check"
echo "  - GET  /models         - Listar modelos"
echo "  - POST /detect         - Detectar objetos (JSON)"
echo "  - POST /detect/upload  - Detectar objetos (file upload)"
echo "  - POST /detect/batch   - Detección batch"
echo "  - POST /detect/faces   - Detección de rostros"
echo ""
echo "Configuración en servidor principal:"
echo "  Añade a tu .env:"
echo -e "  ${YELLOW}JETSON_INFERENCE_URL=http://${JETSON_IP}:5050${NC}"
echo ""
echo "Comandos útiles:"
echo "  - Ver logs:     ssh ${JETSON_USER}@${JETSON_IP} 'cd ${REMOTE_DIR} && docker-compose logs -f'"
echo "  - Reiniciar:    ssh ${JETSON_USER}@${JETSON_IP} 'cd ${REMOTE_DIR} && docker-compose restart'"
echo "  - Detener:      ssh ${JETSON_USER}@${JETSON_IP} 'cd ${REMOTE_DIR} && docker-compose down'"
echo ""
echo "============================================================"
