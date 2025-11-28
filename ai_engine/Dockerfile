FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema para OpenCV (glib)
RUN apt-get update && apt-get install -y --no-install-recommends     libgl1-mesa-glx     libglib2.0-0     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/worker_manager.py"]
