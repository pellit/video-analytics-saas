import os
import sys
import time

# Asegurar que el repo raíz esté en PYTHONPATH para imports relativos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ai_engine.src.core.providers import VirtualProvider
from ai_engine.src.core.physics_engine import PhysicsEngine


def test_virtual_provider_basic():
    data_file = os.path.join(os.path.dirname(__file__), 'data', 'sample_sim.json')
    physics = PhysicsEngine()
    provider = VirtualProvider(data_file, physics_engine=physics)

    # Leer varios frames
    frames = []
    for i in range(5):
        fd = provider.get_next_frame()
        assert fd is not None, f"Frame {i} fue None"
        assert hasattr(fd, 'timestamp')
        frames.append(fd)

    # Release debe limpiar recursos
    provider.release()
    assert provider.data == []


if __name__ == '__main__':
    # Ejecutar prueba localmente
    start = time.time()
    test_virtual_provider_basic()
    print('Test passed in', time.time() - start)
