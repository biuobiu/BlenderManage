import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "source"))

from core.data_manager import DataManager


class TestDataManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.orig_base = os.path.join(os.path.expanduser("~"), ".BlenderManager")

    def test_read_json_nonexistent(self):
        dm = DataManager()
        result = dm.read_json("nonexistent/file.json")
        self.assertIsNone(result)

    def test_write_and_read_json(self):
        dm = DataManager()
        test_data = {"key": "value", "num": 42}
        dm.write_json("test_dir/test.json", test_data)
        result = dm.read_json("test_dir/test.json")
        self.assertEqual(result, test_data)

    def test_file_exists(self):
        dm = DataManager()
        self.assertFalse(dm.file_exists("nonexistent.json"))
        dm.write_json("exists.json", {"ok": True})
        self.assertTrue(dm.file_exists("exists.json"))

    def test_delete_file(self):
        dm = DataManager()
        dm.write_json("to_delete.json", {"a": 1})
        self.assertTrue(dm.file_exists("to_delete.json"))
        dm.delete_file("to_delete.json")
        self.assertFalse(dm.file_exists("to_delete.json"))

    def test_load_notes_empty(self):
        dm = DataManager()
        notes = dm.load_notes()
        self.assertIsInstance(notes, dict)

    def test_save_and_load_notes(self):
        dm = DataManager()
        notes = {"render1.png": "great render", "render2.jpg": "needs work"}
        dm.save_notes(notes)
        loaded = dm.load_notes()
        self.assertEqual(loaded, notes)

    def test_load_base_meshes_empty(self):
        dm = DataManager()
        meshes = dm.load_base_meshes()
        self.assertIsInstance(meshes, dict)

    def test_get_installed_versions_empty(self):
        dm = DataManager()
        versions = dm.get_installed_versions()
        self.assertIsInstance(versions, list)

    def test_singleton(self):
        dm1 = DataManager()
        dm2 = DataManager()
        self.assertIs(dm1, dm2)


if __name__ == "__main__":
    unittest.main()
