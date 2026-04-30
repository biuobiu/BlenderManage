import os
import platform
import subprocess
import sys
import tempfile
import zipfile
import tarfile

import requests

from core.exceptions import NetworkError
from core.logger import Logger
from core.utils import get_system_platform

log = Logger()


class NetworkService:
    @staticmethod
    def fetch_text(url, timeout=10):
        try:
            response = requests.get(url, timeout=timeout, headers={
                "User-Agent": "BlenderManager/1.0"
            })
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise NetworkError(url, str(e))

    @staticmethod
    def download_file(url, dest_path, timeout=30):
        try:
            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return dest_path
        except Exception as e:
            raise NetworkError(url, str(e))

    @staticmethod
    def check_url_accessible(url, timeout=5):
        try:
            response = requests.head(url, timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def open_url_in_browser(url):
        import webbrowser
        webbrowser.open(url)
