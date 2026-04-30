import re

from core.exceptions import VersionError
from core.logger import Logger

log = Logger()


class VersionService:
    def parse_version(self, version_string):
        try:
            return tuple(map(int, version_string.split(".")))
        except ValueError:
            raise VersionError(f"Invalid version format: {version_string}")

    def is_newer(self, current, latest):
        try:
            cur = self.parse_version(current)
            lat = self.parse_version(latest)
            return lat > cur
        except VersionError as e:
            log.error(f"Version comparison failed: {e}")
            return False

    def extract_version_from_text(self, text):
        matches = re.findall(r"\b(\d+\.\d+\.\d+)\b", text)
        if not matches:
            matches = re.findall(r"v(\d+\.\d+\.\d+)", text)
        if not matches:
            matches = re.findall(r"(\d+\.\d+)(?:\.\d+)?", text)
        return matches

    def get_latest_from_list(self, versions):
        if not versions:
            return None
        def sort_key(v):
            try:
                return list(map(int, v.split(".")))
            except ValueError:
                return [0, 0, 0]
        return sorted(versions, key=sort_key)[-1]

    def get_latest_blender_version(self):
        import requests
        try:
            response = requests.get(
                "https://www.blender.org/download/",
                timeout=10,
                headers={"User-Agent": "BlenderManager/1.0"}
            )
            response.raise_for_status()
            versions = self.extract_version_from_text(response.text)
            return self.get_latest_from_list(versions)
        except Exception as e:
            log.error(f"Failed to fetch Blender version: {e}")
            return None

    def get_installed_blender_version(self, blender_exe_path):
        import subprocess
        try:
            result = subprocess.run(
                [blender_exe_path, "--version"],
                capture_output=True, text=True, timeout=15
            )
            versions = self.extract_version_from_text(result.stdout)
            return versions[0] if versions else None
        except Exception as e:
            log.error(f"Failed to get installed Blender version: {e}")
            return None
