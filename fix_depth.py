import sys

file_path = './ai_engine/src/inference_api.py'

with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False

for i, line in enumerate(lines):
    # Buscamos la línea del error
    if 'depth_img = net.Process(cuda_img, disparity=False)' in line:
        # Reemplazamos esa línea por la lógica correcta de 3 pasos
        indent = line[:line.find('depth_img')] # Mantener indentación
        new_lines.append(indent + "# --- CORRECCIÓN DEPTHNET ---\n")
        new_lines.append(indent + "# 1. Crear buffer de salida visual si no existe\n")
        new_lines.append(indent + "if not hasattr(net, 'overlay'):\n")
        new_lines.append(indent + "    net.overlay = jetson.utils.cudaAllocMapped(width=cuda_img.width, height=cuda_img.height, format=cuda_img.format)\n")
        new_lines.append(indent + "# 2. Procesar (Calcular profundidad)\n")
        new_lines.append(indent + "net.Process(cuda_img)\n")
        new_lines.append(indent + "# 3. Visualizar (Pintar el mapa de profundidad en el buffer)\n")
        new_lines.append(indent + "net.Visualize(net.overlay)\n")
        new_lines.append(indent + "depth_img = net.overlay\n")
        new_lines.append(indent + "# ---------------------------\n")
    else:
        new_lines.append(line)

with open(file_path, 'w') as f:
    f.writelines(new_lines)

print("✅ Archivo inference_api.py corregido con éxito.")
