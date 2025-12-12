import os

DEFAULT_JETSON_DATA_DIR = '/home/jetson/video-analytics-saas/data'
CUSTOM_JETSON_DATA_DIR = os.environ.get('JETSON_DATA_DIR_OVERRIDE')


def _configure_jetson_data_dir():
    candidate = None
    if CUSTOM_JETSON_DATA_DIR:
        candidate = CUSTOM_JETSON_DATA_DIR
    elif os.path.isdir(DEFAULT_JETSON_DATA_DIR):
        candidate = DEFAULT_JETSON_DATA_DIR

    if candidate and os.path.isdir(candidate):
        if not os.environ.get('JETSON_DATA_DIR'):
            os.environ['JETSON_DATA_DIR'] = candidate
        root_guess = os.path.dirname(candidate)
        os.environ.setdefault('JETSON_INFERENCE_ROOT', root_guess)
        print(f"📁 Jetson data dir: {os.environ['JETSON_DATA_DIR']}")


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
