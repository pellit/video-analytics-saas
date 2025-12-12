import sys

file_path = './ai_engine/src/inference_api.py'

# Leemos el archivo actual
with open(file_path, 'r') as f:
    content = f.read()

# 1. Definimos el bloque de código ROTO (el que pusimos antes)
broken_code = """        # 1. Crear buffer de salida visual si no existe
        if not hasattr(net, 'overlay'):
            net.overlay = jetson.utils.cudaAllocMapped(width=cuda_img.width, height=cuda_img.height, format=cuda_img.format)
        # 2. Procesar (Calcular profundidad)
        net.Process(cuda_img)
        # 3. Visualizar (Pintar el mapa de profundidad en el buffer)
        net.Visualize(net.overlay)
        depth_img = net.overlay"""

# 2. Definimos el bloque de código CORREGIDO
# Usamos '_run_depthnet_on_video.overlay' en lugar de 'net.overlay'
# Las funciones en Python SI permiten atributos dinámicos.
fixed_code = """        # 1. Crear buffer de salida visual si no existe (Guardado en la función)
        if not hasattr(_run_depthnet_on_video, 'overlay'):
            _run_depthnet_on_video.overlay = jetson.utils.cudaAllocMapped(width=cuda_img.width, height=cuda_img.height, format=cuda_img.format)
        
        # 2. Procesar (Calcular profundidad)
        net.Process(cuda_img)
        
        # 3. Visualizar (Pintar el mapa de profundidad en el buffer)
        net.Visualize(_run_depthnet_on_video.overlay)
        
        depth_img = _run_depthnet_on_video.overlay"""

# 3. Reemplazamos
if broken_code in content:
    new_content = content.replace(broken_code, fixed_code)
    with open(file_path, 'w') as f:
        f.write(new_content)
    print("✅ Archivo inference_api.py ARREGLADO correctamente.")
else:
    # Si no encuentra el bloque exacto, intentamos una búsqueda más laxa o avisamos
    # (Probablemente espacios o tabulaciones, intentamos reemplazo simple de texto)
    print("⚠️ No encontré el bloque exacto, intentando reemplazo genérico...")
    new_content = content.replace("net.overlay", "_run_depthnet_on_video.overlay")
    if new_content != content:
        with open(file_path, 'w') as f:
            f.write(new_content)
        print("✅ Archivo corregido (Reemplazo genérico).")
    else:
        print("❌ No se pudo encontrar el código a corregir. Verifica el archivo manualmente.")

