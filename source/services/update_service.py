import os
import platform
import re
import subprocess
import sys
import threading
import zipfile

import requests

from core.config import ConfigManager
from core.exceptions import NetworkError, VersionError
from core.logger import Logger

log = Logger()


class UpdateService:
    BM_RELEASES_URL = "https://github.com/verlorengest/BlenderManager/releases"

    def __init__(self):
        self.config = ConfigManager()
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def reset_cancel(self):
        self._cancel_event.clear()

    def check_bm_latest_version(self):
        try:
            response = requests.get(self.BM_RELEASES_URL, timeout=10)
            response.raise_for_status()
            versions = re.findall(r"v(\d+\.\d+\.\d+)", response.text)
            if not versions:
                return None

            def sort_key(v):
                return list(map(int, v.split(".")))
            return sorted(versions, key=sort_key)[-1]
        except Exception as e:
            log.error(f"Failed to check BM updates: {e}")
            return None

    def download_file(self, url, dest_path, progress_callback=None):
        if self._cancel_event.is_set():
            return False

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._cancel_event.is_set():
                        f.close()
                        os.remove(dest_path)
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            progress_callback(downloaded / total_size * 100)
            return True
        except Exception as e:
            log.error(f"Download failed: {e}")
            raise NetworkError(url, str(e))

    def run_updater(self, zip_path):
        app_dir = os.getcwd()
        python_exe = sys.executable
        updater_script = os.path.join(app_dir, "updater.py")
        updater_exe = os.path.join(app_dir, "updater.exe")

        if os.path.exists(updater_exe):
            cmd = [updater_exe, "--zip-path", zip_path]
        elif os.path.exists(updater_script):
            cmd = [python_exe, updater_script, "--zip-path", zip_path]
        else:
            raise FileNotFoundError("No updater found (updater.exe or updater.py)")

        subprocess.Popen(cmd)
        return True
