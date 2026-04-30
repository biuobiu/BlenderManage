import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import Logger, load_path_overrides
from gui.base_app import BlenderManagerApp

log = Logger()

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".BlenderManager", "config.json")


def _init_i18n():
    lang = "zh_CN"
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            lang = cfg.get("language", "zh_CN")
    except Exception:
        pass
    from i18n import init
    init(language=lang)


def main():
    try:
        _init_i18n()
        load_path_overrides(CONFIG_PATH)
        log.info("Starting Blender Manager...")
        app = BlenderManagerApp()
        app.mainloop()
    except Exception as e:
        log.critical(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
