FROM python:3.11-slim

WORKDIR /app

# Instalar librerías gráficas para OpenCV + Node.js para yt-dlp YouTube + ffmpeg para streams
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usamos -u para ver logs en tiempo real (unbuffered)
CMD ["python", "-u", "src/worker_manager.py"]