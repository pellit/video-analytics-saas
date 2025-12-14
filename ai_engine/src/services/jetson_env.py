import os
import shutil
import urllib.request

DEFAULT_JETSON_DATA_DIR = '/home/jetson/video-analytics-saas/data'
CUSTOM_JETSON_DATA_DIR = os.environ.get('JETSON_DATA_DIR_OVERRIDE')
CUSTOM_JETSON_INFERENCE_ROOT = os.environ.get('JETSON_INFERENCE_ROOT_OVERRIDE')

GOOGLE_DRIVE_MODELS = {
    "Action-ResNet18/resnet-18-kinetics-moments.onnx": "1_FW4jU9G0j-z9OFBhULz47xLRf8GDnsU",
    "Action-ResNet18/resnet-34-kinetics-moments.onnx": "10By0Loxtu-VWNi84bStWkGwbYfnW9Il1",
    "Action-ResNet18/resnet-50-kinetics.onnx": "1cz5Gnh-bfWkBBitsxK17s1N2R0uv_e_o",
    "Action-ResNet18/resnext-101-kinetics.onnx": "1X4NBid0lyWl7CRsa9kZS1HmXMgb-vsXU",
}


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
        "Action-ResNet18/resnet-34-kinetics-moments.onnx",
        "Action-ResNet18/resnet-50-kinetics.onnx",
        "Action-ResNet18/resnext-101-kinetics.onnx",
        "Action-ResNet18/labels.txt",
        "Pose-ResNet18-Body/human_pose.json",
        "Pose-ResNet18-Body/pose_resnet18_body.onnx",
        "MonoDepth-FCN-ResNet18/monodepth_fcn_resnet18.onnx",
    ]
    missing = [
        rel for rel in required if not os.path.exists(os.path.join(data_dir, rel))
    ]
    if not missing:
        return
    downloader = os.path.join(jets_root, "tools", "download-models.sh")
    if os.path.exists(downloader):
        print("⬇️ Descargando modelos Jetson faltantes...")
        os.system(f"cd {os.path.dirname(downloader)} && ./download-models.sh")
    else:
        print("⚠️ download-models.sh no encontrado; probando mirrors alternativos.")
    still_missing = _refresh_missing(data_dir, missing)
    if still_missing:
        downloaded = _download_from_drive_batch(still_missing, data_dir)
        if downloaded:
            still_missing = _refresh_missing(data_dir, still_missing)
    if still_missing:
        print("⚠️ Estos modelos aún faltan tras los intentos automáticos:")
        for rel in still_missing:
            print(f"    - {os.path.join(data_dir, rel)}")
    else:
        print("✅ Modelos Jetson descargados correctamente.")


def _refresh_missing(base_dir, entries):
    return [
        rel for rel in entries if not os.path.exists(os.path.join(base_dir, rel))
    ]


def _download_file_from_drive(file_id, destination):
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
    tmp_path = f"{destination}.part"
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    try:
        with urllib.request.urlopen(url) as response, open(tmp_path, 'wb') as tmp_file:
            shutil.copyfileobj(response, tmp_file)
        os.replace(tmp_path, destination)
        print(f"⬇️ Descargado desde Google Drive: {destination}")
        return True
    except Exception as exc:
        print(f"⚠️ No se pudo descargar {destination}: {exc}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _download_from_drive_batch(missing, base_dir):
    downloaded = []
    for rel in missing:
        file_id = GOOGLE_DRIVE_MODELS.get(rel)
        if not file_id:
            continue
        dest = os.path.join(base_dir, rel)
        if _download_file_from_drive(file_id, dest):
            downloaded.append(rel)
    return downloaded
