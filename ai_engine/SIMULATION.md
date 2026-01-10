# Simulación y Testing con `VirtualProvider`

Este documento explica cómo usar el `VirtualProvider` para pruebas y cómo generar los datos de simulación desde una grabación real.

Archivos añadidos:
- `ai_engine/src/core/providers.py` — contiene `VirtualProvider` y `CameraProvider`.
- `ai_engine/tests/data/sample_sim.json` — ejemplo de 10 frames para probar.
- `ai_engine/tests/test_virtual_provider.py` — test básico que valida la carga y procesamiento.
- `tools/record_session.py` — herramienta para grabar sesiones reales y generar JSON.

1) Ejecutar la prueba unitaria

Instala dependencias del proyecto (virtualenv recomendado) y ejecuta:

```bash
pip install -r ai_engine/requirements.txt
pytest ai_engine/tests/test_virtual_provider.py -q
```

2) Grabar una sesión real y generar JSON

Usa la herramienta `tools/record_session.py` para convertir un video en JSON:

```bash
python tools/record_session.py path/to/video.mp4 ai_engine/tests/data/my_session.json
```

3) Usar la simulación desde la API

Sube el JSON resultante al endpoint `/coach/analyze` (el servidor detecta JSON y usa `VirtualProvider`):

```bash
curl -X POST "http://localhost:5050/coach/analyze" \
  -F "file=@ai_engine/tests/data/my_session.json" \
  -F "mode=soccer"
```

4) Usar la simulación localmente (script)

Puedes ejecutar un snippet rápido en Python para validar la integración:

```python
from ai_engine.src.core.providers import VirtualProvider
from ai_engine.src.core.physics_engine import PhysicsEngine
from ai_engine.src.orchestrator import ServiceContainer, CoachOrchestrator

physics = PhysicsEngine()
provider = VirtualProvider('ai_engine/tests/data/sample_sim.json', physics_engine=physics)
svc = ServiceContainer()
svc.initialize()
coach = CoachOrchestrator(mode='soccer', config={}, services=svc)
result = coach.process_session(provider)
print(result['meta']['stats'])
```

Notas:
- Los JSON deben seguir la estructura del ejemplo: `frame`, `floor_y`, `ball` (bbox) y `pose` con `box` y `kpts`.
- `VirtualProvider` pasa los datos por `PhysicsEngine` para mantener consistencia con el pipeline real.

Si quieres, puedo añadir más tests automáticos (p. ej. verificar que el `TechnicalEvaluator` cuente correctamente juggling sobre la simulación). Solo dime qué métricas quieres validar.
