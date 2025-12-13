import os

DEFAULT_JETSON_DATA_DIR = '/home/jetson/video-analytics-saas/data'
CUSTOM_JETSON_DATA_DIR = os.environ.get('JETSON_DATA_DIR_OVERRIDE')


def _configure_jetson_data_dir():
    candidates = [
        CUSTOM_JETSON_DATA_DIR,
        os.environ.get('JETSON_DATA_DIR'),
        '/usr/local/bin',
        '/jetson-inference/data',
        DEFAULT_JETSON_DATA_DIR,
    ]

    for path in candidates:
        if not path:
            continue
        networks_path = os.path.join(path, 'networks')
        if os.path.isdir(networks_path):
            os.environ['JETSON_DATA_DIR'] = path
            os.environ.setdefault('JETSON_INFERENCE_ROOT', os.path.dirname(path))
            print(f"📁 Jetson data dir detectado: {path}")
            return

    print("⚠️ No se detectó ninguna ruta de modelos Jetson preconfigurada.")


_configure_jetson_data_dir()

JETSON_DATA_DIR_ACTIVE = os.environ.get('JETSON_DATA_DIR')
JETSON_NETWORKS_DIR = (
    os.path.join(JETSON_DATA_DIR_ACTIVE, 'networks')
    if JETSON_DATA_DIR_ACTIVE else None
)
JETSON_MODELS_MANIFEST = (
    os.path.join(JETSON_NETWORKS_DIR, 'models.json')
    if JETSON_NETWORKS_DIR else None
)
