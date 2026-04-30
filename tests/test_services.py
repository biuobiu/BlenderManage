import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "source"))

from services.version_service import VersionService
from services.update_service import UpdateService
from services.network_service import NetworkService


class TestVersionService(unittest.TestCase):
    def setUp(self):
        self.svc = VersionService()

    def test_parse_version(self):
        self.assertEqual(self.svc.parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(self.svc.parse_version("4.5.6"), (4, 5, 6))

    def test_is_newer_true(self):
        self.assertTrue(self.svc.is_newer("1.0.0", "1.0.1"))
        self.assertTrue(self.svc.is_newer("1.0.0", "2.0.0"))
        self.assertTrue(self.svc.is_newer("1.0.0", "1.1.0"))

    def test_is_newer_false(self):
        self.assertFalse(self.svc.is_newer("2.0.0", "1.0.0"))
        self.assertFalse(self.svc.is_newer("1.0.1", "1.0.0"))
        self.assertFalse(self.svc.is_newer("1.0.0", "1.0.0"))

    def test_extract_version_from_text(self):
        text = "Blender v4.2.0 released"
        versions = self.svc.extract_version_from_text(text)
        self.assertIn("4.2.0", versions)

    def test_get_latest_from_list(self):
        versions = ["1.0.0", "2.0.0", "1.5.0", "3.0.0"]
        self.assertEqual(self.svc.get_latest_from_list(versions), "3.0.0")

    def test_get_latest_from_list_single(self):
        self.assertEqual(self.svc.get_latest_from_list(["1.0.0"]), "1.0.0")

    def test_get_latest_from_list_empty(self):
        self.assertIsNone(self.svc.get_latest_from_list([]))


class TestUpdateService(unittest.TestCase):
    def setUp(self):
        self.svc = UpdateService()

    def test_init(self):
        self.assertIsNotNone(self.svc)

    def test_cancel(self):
        self.svc.cancel()
        self.svc.reset_cancel()


class TestNetworkService(unittest.TestCase):
    def test_check_url_accessible_invalid(self):
        result = NetworkService.check_url_accessible("https://invalid.url.example", timeout=2)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
