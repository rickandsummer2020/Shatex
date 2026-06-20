"""Unit tests for ShareX file info model."""

import os
import tempfile
import unittest
from pathlib import Path

from sharex.models.file_info import FileInfo


class TestFileInfo(unittest.TestCase):
    """Tests for FileInfo model."""

    def setUp(self) -> None:
        """Set up test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.txt"
        self.test_file.write_text("Hello, World!")

        self.test_dir = Path(self.temp_dir) / "subdir"
        self.test_dir.mkdir()
        (self.test_dir / "file1.txt").write_text("File 1")
        (self.test_dir / "file2.txt").write_text("File 2")

    def tearDown(self) -> None:
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_from_file(self) -> None:
        """Test creating from file."""
        info = FileInfo.from_path(str(self.test_file))
        self.assertEqual(info.name, "test.txt")
        self.assertFalse(info.is_directory)
        self.assertEqual(info.size, 13)

    def test_from_directory(self) -> None:
        """Test creating from directory."""
        info = FileInfo.from_path(str(self.test_dir))
        self.assertTrue(info.is_directory)
        self.assertEqual(len(info.children), 2)

    def test_formatted_size(self) -> None:
        """Test formatted size."""
        info = FileInfo.from_path(str(self.test_file))
        self.assertEqual(info.formatted_size, "13.0 B")

    def test_extension(self) -> None:
        """Test file extension."""
        info = FileInfo.from_path(str(self.test_file))
        self.assertEqual(info.extension, ".txt")

    def test_calculate_sha256(self) -> None:
        """Test checksum calculation."""
        info = FileInfo.from_path(str(self.test_file))
        checksum = info.calculate_sha256()
        self.assertEqual(len(checksum), 64)  # SHA-256 hex length
        self.assertEqual(checksum, info.checksum)

    def test_get_all_files(self) -> None:
        """Test getting all files recursively."""
        info = FileInfo.from_path(str(self.test_dir))
        files = info.get_all_files()
        self.assertEqual(len(files), 2)

    def test_get_total_size(self) -> None:
        """Test getting total size."""
        info = FileInfo.from_path(str(self.test_dir))
        total = info.get_total_size()
        self.assertGreater(total, 0)

    def test_nonexistent_path(self) -> None:
        """Test nonexistent path."""
        with self.assertRaises(FileNotFoundError):
            FileInfo.from_path("/nonexistent/path")

    def test_to_dict(self) -> None:
        """Test serialization."""
        info = FileInfo.from_path(str(self.test_file))
        data = info.to_dict()
        self.assertEqual(data["name"], "test.txt")
        self.assertFalse(data["is_directory"])

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "name": "test.txt",
            "path": "/tmp/test.txt",
            "size": 13,
            "is_directory": False,
            "children": [],
            "metadata": {},
        }
        info = FileInfo.from_dict(data)
        self.assertEqual(info.name, "test.txt")
        self.assertFalse(info.is_directory)


if __name__ == "__main__":
    unittest.main()
