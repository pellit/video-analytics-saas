import sys
import os

file_path = './ai_engine/src/inference_api.py'

if not os.path.exists(file_path):
    print(f"❌ Error: No encuentro el archivo en {file_path}")
    sys.exit(1)

with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
fixed = False

for line in lines:
    # Buscamos la línea exacta que está fallando en tus logs
    if "cv2.applyColorMap" in line:
        # Obtenemos la indentación (los espacios al inicio) para no romper el código
        indent = line[:line.find(line.strip())]
        
        # Extraemos el nombre de la variable que se está pasando (ej: 'normalized')
        # Asumimos formato: heatmap = cv2.applyColorMap(VARIABLE, ...)
        parts = line.split('(')
        if len(parts) > 1:
            var_name = parts[1].split(',')[0].strip()
            
            # --- AQUÍ ESTÁ LA MAGIA ---
            # Insertamos la conversión explícita justo antes del error
            new_lines.append(f"{indent}# FIX: Convertir a uint8 obligatoriamente para OpenCV\n")
            new_lines.append(f"{indent}{var_name} = {var_name}.astype(np.uint8)\n")
            new_lines.append(f"{indent}# -----------------------------------------------\n")
            fixed = True
            
    new_lines.append(line)

if fixed:
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print("✅ Archivo inference_api.py PARCHADO: Se agregó .astype(np.uint8)")
else:
    print("⚠️ No encontré la línea 'cv2.applyColorMap'. Verifica tu código manualmente.")

