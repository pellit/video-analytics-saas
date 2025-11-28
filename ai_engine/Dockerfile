FROM python:3.11-slim

WORKDIR /app

# CORRECCIÓN:
# 1. Usamos 'libgl1' en lugar de 'libgl1-mesa-glx' (que es el nombre antiguo/obsoleto).
# 2. Agregamos libsm6 y libxext6 que OpenCV suele necesitar para evitar errores futuros.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/worker_manager.py"]
