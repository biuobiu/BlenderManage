import json
import os
import platform
import subprocess
import sys

from .exceptions import PlatformError

_PATH_OVERRIDES = {}
_OVERRIDE_FILE = None


def _get_override(key, default):
    return _PATH_OVERRIDES.get(key, default)


def set_path_overrides(overrides):
    _PATH_OVERRIDES.clear()
    for k, v in overrides.items():
        if v:
            _PATH_OVERRIDES[k] = os.path.normpath(v)


def get_path_overrides():
    return dict(_PATH_OVERRIDES)


def save_path_overrides(config_path):
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        existing = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                existing = json.load(f)
        existing["path_overrides"] = dict(_PATH_OVERRIDES)
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=4)
    except Exception as e:
        raise RuntimeError(f"Failed to save path overrides: {e}")


def load_path_overrides(config_path):
    try:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                data = json.load(f)
            overrides = data.get("path_overrides", {})
            set_path_overrides(overrides)
    except Exception:
        pass


def get_system_platform():
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    raise PlatformError(f"Unsupported operating system: {system}")


def get_blender_config_path():
    system = platform.system()
    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            return os.path.join(appdata, "Blender Foundation", "Blender")
        raise EnvironmentError("APPDATA environment variable is not set.")
    elif system == "Darwin":
        paths = [
            os.path.expanduser("~/Library/Application Support/Blender"),
            "/Applications/Blender.app/Contents/Resources/config",
            os.path.expanduser("~/.blender"),
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        raise EnvironmentError("Blender config path not found on macOS.")
    elif system == "Linux":
        paths = [
            os.path.expanduser("~/.config/blender"),
            os.path.expanduser("~/.blender"),
            "/usr/share/blender/config",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        raise EnvironmentError("Blender config path not found on Linux.")
    raise PlatformError(f"Unsupported OS: {system}")


def normalize_path(path):
    return os.path.normpath(os.path.abspath(path))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def get_blender_manager_dir():
    return _get_override("blender_manager_dir",
                         os.path.join(os.path.expanduser("~"), ".BlenderManager"))


def get_blender_versions_dir():
    return _get_override("blender_versions_dir",
                         os.path.join(get_blender_manager_dir(), "BlenderVersions"))


def _detect_latest_version(versions_dir):
    if not os.path.exists(versions_dir):
        return None
    vers = sorted([d for d in os.listdir(versions_dir)
                   if os.path.isdir(os.path.join(versions_dir, d))], reverse=True)
    return vers[0] if vers else None


def get_selected_main_version():
    try:
        cfg = os.path.join(get_blender_manager_dir(), "config.json")
        if os.path.exists(cfg):
            with open(cfg, "r") as f:
                data = json.load(f)
            ver = data.get("selected_main_version", "")
            if ver and os.path.isdir(os.path.join(get_blender_versions_dir(), ver)):
                return ver
        latest = _detect_latest_version(get_blender_versions_dir())
        return latest
    except Exception:
        return _detect_latest_version(get_blender_versions_dir())


def get_blender_install_dir():
    ver = get_selected_main_version()
    if ver:
        return os.path.join(get_blender_versions_dir(), ver)
    return get_blender_versions_dir()


def get_blender_executable():
    system = get_system_platform()
    base = get_blender_install_dir()
    if system == "windows":
        return os.path.join(base, "blender.exe")
    elif system == "macos":
        return os.path.join(base, "Blender.app", "Contents", "MacOS", "Blender")
    return os.path.join(base, "blender")


def open_file_with_default_app(file_path):
    try:
        if sys.platform.startswith("darwin"):
            subprocess.call(("open", file_path))
        elif sys.platform.startswith("win"):
            os.startfile(file_path)
        elif sys.platform.startswith("linux"):
            subprocess.call(("xdg-open", file_path))
    except Exception as e:
        raise RuntimeError(f"Could not open file: {file_path}") from e


def get_user_data_dir():
    return _get_override("user_data_dir",
                         os.path.join(get_blender_manager_dir(), "mngaddon"))


def get_paths_dir():
    return _get_override("paths_dir",
                         os.path.join(get_blender_manager_dir(), "paths"))


def get_assets_dir():
    return _get_override("assets_dir", "")


def resource_path(relative_path):
    overridden = get_assets_dir()
    if overridden:
        return os.path.join(overridden, relative_path)
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)
