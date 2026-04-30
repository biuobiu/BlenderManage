import json
import os

from .exceptions import ConfigError, FileReadError, FileWriteError
from .logger import Logger

log = Logger()

CONFIG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".BlenderManager", "config.json")

DEFAULT_SETTINGS = {
    "version": "1.0.2",
    "selected_theme": "darkly",
    "auto_update_checkbox": True,
    "bm_auto_update_checkbox": False,
    "launch_on_startup": False,
    "run_in_background": True,
    "chunk_size_multiplier": 3,
    "window_alpha": 0.98,
    "treeview_font_size": 12,
    "treeview_heading_font_size": 10,
    "treeview_font_family": "Segoe UI",
    "button_font_family": "Segoe UI",
    "button_font_size": 11,
    "show_addon_management": True,
    "show_project_management": True,
    "show_render_management": True,
    "show_version_management": True,
    "show_worktime_label": True,
    "auto_activate_plugin": True,
    "language": "zh_CN",
    "selected_main_version": "",
}


class ConfigManager:
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
        self._config = {}
        self._config_path = CONFIG_FILE_PATH
        self.load()

    def load(self):
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r") as f:
                    self._config = json.load(f)
                log.info("Config loaded successfully.")
            except (json.JSONDecodeError, FileNotFoundError) as e:
                log.warning(f"Error reading config: {e}. Using defaults.")
                self.reset_to_defaults()
        else:
            self.reset_to_defaults()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w") as f:
                json.dump(self._config, f, indent=4)
            log.info("Config saved.")
        except Exception as e:
            raise FileWriteError(self._config_path, str(e))

    def reset_to_defaults(self):
        self._config = DEFAULT_SETTINGS.copy()
        self.save()

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value

    def set_many(self, items):
        self._config.update(items)

    def save_setting(self, key, value):
        self.set(key, value)
        self.save()

    def get_all(self):
        return self._config.copy()

    def get_tab_visibility(self):
        return {
            "Addon Management": self.get("show_addon_management", True),
            "Project Management": self.get("show_project_management", True),
            "Render Management": self.get("show_render_management", True),
            "Version Management": self.get("show_version_management", True),
        }
