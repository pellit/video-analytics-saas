import os

DEFAULT_JETSON_DATA_DIR = '/home/jetson/video-analytics-saas/data'
CUSTOM_JETSON_DATA_DIR = os.environ.get('JETSON_DATA_DIR_OVERRIDE')
CUSTOM_JETSON_INFERENCE_ROOT = os.environ.get('JETSON_INFERENCE_ROOT_OVERRIDE')


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
            print(f"📁 Jetson data dir detectado: {path}")
            return path

    print("⚠️ No se detectó ninguna ruta de modelos Jetson preconfigurada.")
    return None


def _configure_jetson_inference_root(data_dir_path):
    """Detecta la raíz del repo jetson-inference para usar download-models.sh."""
    existing = os.environ.get('JETSON_INFERENCE_ROOT')

    def _has_downloader(root_path):
        if not root_path:
            return False
        return os.path.exists(os.path.join(root_path, 'tools', 'download-models.sh'))

    if existing and _has_downloader(existing):
        print(f"📦 Jetson inference root detectado: {existing}")
        return existing

    base_hint = os.path.dirname(data_dir_path) if data_dir_path else None
    candidates = [
        CUSTOM_JETSON_INFERENCE_ROOT,
        base_hint,
        '/jetson-inference',
        '/opt/jetson-inference',
        '/usr/local/jetson-inference',
        os.path.expanduser('~/jetson-inference'),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        if _has_downloader(candidate):
            os.environ['JETSON_INFERENCE_ROOT'] = candidate
            print(f"📦 Jetson inference root detectado: {candidate}")
            return candidate

    if existing:
        print(f"⚠️ No se encontró download-models.sh en {existing}")
    else:
        print("⚠️ No se detectó jetson-inference root (download-models.sh).")
    return None


detected_data_dir = _configure_jetson_data_dir()
_configure_jetson_inference_root(detected_data_dir)

JETSON_DATA_DIR_ACTIVE = os.environ.get('JETSON_DATA_DIR')
JETSON_NETWORKS_DIR = (
    os.path.join(JETSON_DATA_DIR_ACTIVE, 'networks')
    if JETSON_DATA_DIR_ACTIVE else None
)
JETSON_MODELS_MANIFEST = (
    os.path.join(JETSON_NETWORKS_DIR, 'models.json')
    if JETSON_NETWORKS_DIR else None
)


def ensure_jetson_models():
    """Descarga modelos faltantes usando jetson-inference si están disponibles."""
    jets_root = os.environ.get('JETSON_INFERENCE_ROOT')
    data_dir = os.environ.get('JETSON_DATA_DIR')
    if not jets_root or not data_dir:
        return
    required = [
        "Action-ResNet18/resnet-18-kinetics-moments.onnx",
        "Action-ResNet18/labels.txt",
        "Pose-ResNet18-Body/human_pose.json",
        "Pose-ResNet18-Body/pose_resnet18_body.onnx",
        "MonoDepth-FCN-ResNet18/monodepth_fcn_resnet18.onnx",
    ]
    missing = []
    for rel in required:
        if not os.path.exists(os.path.join(data_dir, rel)):
            missing.append(rel)
    if not missing:
        return
    downloader = os.path.join(jets_root, "tools", "download-models.sh")
    if not os.path.exists(downloader):
        print("⚠️ download-models.sh no encontrado; no se pueden descargar modelos automáticamente.")
        return
    print("⬇️ Descargando modelos Jetson faltantes...")
    os.system(f"cd {os.path.dirname(downloader)} && ./download-models.sh")
    still_missing = [
        rel for rel in missing if not os.path.exists(os.path.join(data_dir, rel))
    ]
    if still_missing:
        print("⚠️ Estos modelos aún faltan tras la descarga automática:")
        for rel in still_missing:
            print(f"    - {os.path.join(data_dir, rel)}")
    else:
        print("✅ Modelos Jetson descargados correctamente.")
