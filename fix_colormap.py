import sys

file_path = './ai_engine/src/inference_api.py'

# Leemos el archivo
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
found = False

for line in lines:
    # Buscamos la línea que normaliza la imagen (justo antes del error)
    if 'cv2.normalize' in line and 'cv2.NORM_MINMAX' in line:
        new_lines.append(line)
        # AGREGAMOS ESTA LÍNEA MÁGICA:
        # Convierte los decimales (float) a enteros (uint8) para que OpenCV no se queje
        new_lines.append("        normalized = normalized.astype(np.uint8)\n")
        found = True
    else:
        new_lines.append(line)

if found:
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print("✅ Archivo inference_api.py corregido: Se agregó conversión a uint8.")
else:
    print("⚠️ No encontré la línea de normalización. Puede que el código sea diferente al esperado.")

