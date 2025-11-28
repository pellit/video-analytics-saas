FROM python:3.11-slim

WORKDIR /app

# Instalar librerías gráficas para OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usamos -u para ver logs en tiempo real (unbuffered)
CMD ["python", "-u", "src/worker_manager.py"]