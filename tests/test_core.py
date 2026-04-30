import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "source"))

from core.config import ConfigManager, DEFAULT_SETTINGS
from core.exceptions import (
    BlenderManagerError, ConfigError, FileReadError, FileWriteError,
    NetworkError, VersionError, ThreadError, PlatformError, ValidationError
)
from core.utils import (
    get_system_platform, normalize_path, ensure_dir,
    get_blender_manager_dir, get_blender_versions_dir,
    get_blender_install_dir, get_blender_executable
)


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_cfg = os.path.join(os.path.expanduser("~"), ".BlenderManager", "config.json")
        self.test_cfg = os.path.join(self.tmp_dir, "test_config.json")

    def test_default_settings_contains_required_keys(self):
        required = ["version", "selected_theme", "auto_update_checkbox",
                     "run_in_background", "window_alpha"]
        for key in required:
            self.assertIn(key, DEFAULT_SETTINGS, f"Missing key: {key}")

    def test_default_version(self):
        self.assertEqual(DEFAULT_SETTINGS["version"], "1.0.2")

    def test_default_theme(self):
        self.assertEqual(DEFAULT_SETTINGS["selected_theme"], "darkly")


class TestExceptions(unittest.TestCase):
    def test_blender_manager_error_is_base(self):
        self.assertTrue(issubclass(ConfigError, BlenderManagerError))
        self.assertTrue(issubclass(FileReadError, BlenderManagerError))
        self.assertTrue(issubclass(FileWriteError, BlenderManagerError))
        self.assertTrue(issubclass(NetworkError, BlenderManagerError))
        self.assertTrue(issubclass(VersionError, BlenderManagerError))
        self.assertTrue(issubclass(ThreadError, BlenderManagerError))
        self.assertTrue(issubclass(PlatformError, BlenderManagerError))
        self.assertTrue(issubclass(ValidationError, BlenderManagerError))

    def test_file_read_error_message(self):
        e = FileReadError("/path/to/file")
        self.assertIn("/path/to/file", str(e))

    def test_network_error_url(self):
        e = NetworkError(url="https://example.com")
        self.assertEqual(e.url, "https://example.com")


class TestUtils(unittest.TestCase):
    def test_get_system_platform_returns_string(self):
        plat = get_system_platform()
        self.assertIn(plat, ["windows", "linux", "macos"])

    def test_normalize_path(self):
        p = normalize_path("/foo/bar/../baz")
        self.assertTrue(p.endswith("baz"))

    def test_ensure_dir(self):
        with tempfile.TemporaryDirectory() as td:
            test_dir = os.path.join(td, "a", "b", "c")
            result = ensure_dir(test_dir)
            self.assertTrue(os.path.exists(result))

    def test_get_blender_manager_dir(self):
        d = get_blender_manager_dir()
        self.assertTrue(d.endswith(".BlenderManager"))

    def test_get_blender_versions_dir(self):
        d = get_blender_versions_dir()
        self.assertTrue(d.endswith("BlenderVersions"))
        self.assertIn(".BlenderManager", d)

    def test_get_blender_install_dir(self):
        d = get_blender_install_dir()
        self.assertTrue(d.endswith("blender"))

    def test_get_blender_executable(self):
        exe = get_blender_executable()
        self.assertTrue(exe.endswith(".exe") or "Blender.app" in exe or exe.endswith("blender"))


if __name__ == "__main__":
    unittest.main()
