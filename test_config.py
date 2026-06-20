"""Unit tests for ShareX configuration module."""

import os
import json
import tempfile
import shutil
from pathlib import Path
import unittest

from sharex.config import AppConfig, ConfigManager, get_config, init_logging


class TestAppConfig(unittest.TestCase):
    """Tests for AppConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = AppConfig()
        self.assertIsNotNone(config.device_name)
        self.assertTrue(config.device_name.startswith("ShareX-"))
        self.assertEqual(config.port, 57575)
        self.assertEqual(config.chunk_size, 65536)
        self.assertEqual(config.transfer_threads, 4)
        self.assertTrue(config.encryption_enabled)
        self.assertEqual(config.language, "en")

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        config = AppConfig()
        data = config.to_dict()
        self.assertIn("device_name", data)
        self.assertIn("port", data)
        self.assertIsInstance(data, dict)

    def test_to_json(self) -> None:
        """Test conversion to JSON."""
        config = AppConfig()
        json_str = config.to_json()
        self.assertIsInstance(json_str, str)
        data = json.loads(json_str)
        self.assertIn("device_name", data)

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "device_name": "TestDevice",
            "port": 12345,
            "chunk_size": 8192,
        }
        config = AppConfig.from_dict(data)
        self.assertEqual(config.device_name, "TestDevice")
        self.assertEqual(config.port, 12345)
        self.assertEqual(config.chunk_size, 8192)

    def test_from_json(self) -> None:
        """Test creation from JSON."""
        data = {
            "device_name": "TestDevice",
            "port": 12345,
        }
        json_str = json.dumps(data)
        config = AppConfig.from_json(json_str)
        self.assertEqual(config.device_name, "TestDevice")
        self.assertEqual(config.port, 12345)


class TestConfigManager(unittest.TestCase):
    """Tests for ConfigManager."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.test_dir) / ".sharex"

    def tearDown(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init(self) -> None:
        """Test ConfigManager initialization."""
        manager = ConfigManager(config_dir=self.config_dir)
        self.assertTrue(self.config_dir.exists())
        self.assertIsNotNone(manager.config)

    def test_save_and_load(self) -> None:
        """Test saving and loading configuration."""
        manager = ConfigManager(config_dir=self.config_dir)
        manager.config.device_name = "TestDevice"
        manager.save()

        # Create new manager to load saved config
        manager2 = ConfigManager(config_dir=self.config_dir)
        self.assertEqual(manager2.config.device_name, "TestDevice")

    def test_get_set(self) -> None:
        """Test get and set operations."""
        manager = ConfigManager(config_dir=self.config_dir)
        manager.set("device_name", "NewName")
        self.assertEqual(manager.get("device_name"), "NewName")

    def test_get_default(self) -> None:
        """Test get with default value."""
        manager = ConfigManager(config_dir=self.config_dir)
        value = manager.get("nonexistent_key", "default")
        self.assertEqual(value, "default")

    def test_reset(self) -> None:
        """Test configuration reset."""
        manager = ConfigManager(config_dir=self.config_dir)
        manager.set("device_name", "Changed")
        manager.reset()
        self.assertTrue(manager.config.device_name.startswith("ShareX-"))


class TestInitLogging(unittest.TestCase):
    """Tests for logging initialization."""

    def test_init_logging(self) -> None:
        """Test logging initialization."""
        # Should not raise any exceptions
        init_logging()


if __name__ == "__main__":
    unittest.main()
