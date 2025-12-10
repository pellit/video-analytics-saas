# 1. En la Jetson, clonar la rama
git clone -b feature/jetson-edge-inference https://github.com/pellit/video-analytics-saas.git
cd video-analytics-saas

# 2. Construir y ejecutar
docker-compose -f docker-compose.jetson.yml up -d

# 3. Verificar
curl http://localhost:5050/health


./deploy_jetson.sh 192.168.0.37 jetson