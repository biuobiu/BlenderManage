import json
import os

from .exceptions import FileReadError, FileWriteError
from .logger import Logger
from .utils import ensure_dir, get_blender_manager_dir, get_paths_dir, get_user_data_dir

log = Logger()

CONFIG_DIRS = {
    "blender_versions": "BlenderVersions",
    "mngaddon": "mngaddon",
    "paths": "paths",
    "renders": "renders",
}


class DataManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._base_dir = get_blender_manager_dir()
        self._ensure_directories()

    def _ensure_directories(self):
        ensure_dir(self._base_dir)
        for name, subdir in CONFIG_DIRS.items():
            ensure_dir(os.path.join(self._base_dir, subdir))
        log.info("Data directories ensured.")

    def read_json(self, relative_path):
        file_path = os.path.join(self._base_dir, relative_path)
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise FileReadError(file_path, f"Invalid JSON: {e}")
        except IOError as e:
            raise FileReadError(file_path, str(e))

    def write_json(self, relative_path, data):
        file_path = os.path.join(self._base_dir, relative_path)
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
            log.debug(f"Written: {relative_path}")
        except IOError as e:
            raise FileWriteError(file_path, str(e))

    def read_absolute_json(self, file_path):
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise FileReadError(file_path, f"Invalid JSON: {e}")
        except IOError as e:
            raise FileReadError(file_path, str(e))

    def write_absolute_json(self, file_path, data):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            raise FileWriteError(file_path, str(e))

    def file_exists(self, relative_path):
        return os.path.exists(os.path.join(self._base_dir, relative_path))

    def delete_file(self, relative_path):
        file_path = os.path.join(self._base_dir, relative_path)
        if os.path.exists(file_path):
            os.remove(file_path)
            log.info(f"Deleted: {relative_path}")

    def get_installed_versions(self):
        versions_dir = os.path.join(self._base_dir, "BlenderVersions")
        if not os.path.exists(versions_dir):
            return []
        return sorted([
            d for d in os.listdir(versions_dir)
            if os.path.isdir(os.path.join(versions_dir, d))
        ])

    def get_render_folder_path(self):
        data = self.read_json("paths/renderfolderpath.json")
        if data and "render_folder_path" in data:
            return data["render_folder_path"]
        return os.path.join(get_blender_manager_dir(), "renders")

    def save_render_folder_path(self, path):
        self.write_json("paths/renderfolderpath.json", {"render_folder_path": path})

    def load_notes(self):
        data = self.read_json("paths/render_notes.json")
        return data if data else {}

    def save_notes(self, notes_data):
        self.write_json("paths/render_notes.json", notes_data)

    def load_project_times(self):
        data = self.read_json("mngaddon/project_time.json")
        return data if data else {}

    def save_project_times(self, data):
        self.write_json("mngaddon/project_time.json", data)

    def load_base_meshes(self):
        data = self.read_json("paths/base_mesh_path.json")
        return data if data else {}

    def save_base_meshes(self, data):
        self.write_json("paths/base_mesh_path.json", data)

    def load_user_input(self):
        data = self.read_json("mngaddon/user_input.json")
        return data if data else {}

    def save_user_input(self, data):
        self.write_json("mngaddon/user_input.json", data)

    def load_project_settings(self):
        data = self.read_json("mngaddon/settings.json")
        return data if data else {}
