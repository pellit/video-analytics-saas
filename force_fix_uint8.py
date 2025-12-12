import sys
import os
import numpy as np # Importamos por si acaso, aunque es texto

file_path = './ai_engine/src/inference_api.py'

if not os.path.exists(file_path):
    print(f"❌ Error: No encuentro el archivo {file_path}")
    sys.exit(1)

with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
target_line_part = "heatmap = cv2.applyColorMap(normalized, cv2.COLORMAP_PLASMA)"
fix_line_part = "normalized = normalized.astype(np.uint8)"
patched = False

for i, line in enumerate(lines):
    # Si encontramos la línea que da el error en los logs
    if target_line_part in line:
        # Verificamos si ya intentamos arreglarlo antes para no duplicar
        if i > 0 and fix_line_part in lines[i-1]:
            print("⚠️ El parche ya parece estar aplicado. El problema podría ser otro.")
            new_lines.append(line)
            continue
            
        # Obtenemos la indentación exacta (los espacios al inicio)
        indentation = line[:line.find(line.strip())]
        
        # INYECTAMOS LA SOLUCIÓN
        print(f"🔧 Parchando línea {i+1}...")
        new_lines.append(f"{indentation}# FIX FINAL: Forzar conversión a enteros de 8 bits\n")
        new_lines.append(f"{indentation}normalized = normalized.astype(np.uint8)\n")
        new_lines.append(line) # Ponemos la línea original después
        patched = True
    else:
        new_lines.append(line)

if patched:
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print("✅ ¡ÉXITO! Archivo modificado. Se forzó la conversión a uint8.")
else:
    print("❌ NO SE ENCONTRÓ la línea exacta del error.")
    print("Por favor, verifica que tu archivo contenga:")
    print(f"'{target_line_part}'")

