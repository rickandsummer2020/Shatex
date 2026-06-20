"""ShareX Configuration Module.

Manages all application settings, paths, and constants.
Optimized for Termux mobile environment.
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

# Application Constants
APP_NAME: str = "ShareX"
APP_VERSION: str = "1.0.0"
APP_AUTHOR: str = "ShareX Team"

# Terminal Constraints (Mobile Optimized)
MAX_TERMINAL_WIDTH: int = 44
MAX_TERMINAL_HEIGHT: int = 22
MIN_TERMINAL_WIDTH: int = 32
MIN_TERMINAL_HEIGHT: int = 16

# Network Constants
DEFAULT_PORT: int = 57575
DISCOVERY_PORT: int = 57576
BROADCAST_INTERVAL: float = 2.0
CONNECTION_TIMEOUT: float = 10.0
MAX_RETRIES: int = 3

# Transfer Constants
DEFAULT_CHUNK_SIZE: int = 65536  # 64KB
MAX_CHUNK_SIZE: int = 1048576    # 1MB
MIN_CHUNK_SIZE: int = 4096       # 4KB
DEFAULT_THREADS: int = 4
MAX_THREADS: int = 16
MIN_THREADS: int = 1

# File Size Limits
MAX_FILE_SIZE: int = 1099511627776  # 1TB
WARNING_FILE_SIZE: int = 1073741824  # 1GB

# Cryptography Constants
KEY_SIZE: int = 32
NONCE_SIZE: int = 12
SALT_SIZE: int = 16
ITERATIONS: int = 100000

# UI Constants
REFRESH_RATE: float = 0.1
PROGRESS_BAR_WIDTH: int = 30
NOTIFICATION_DURATION: float = 3.0

# Theme Constants
DARK_THEME: Dict[str, str] = {
    "background": "#1a1a2e",
    "surface": "#16213e",
    "primary": "#0f3460",
    "accent": "#e94560",
    "text": "#eaeaea",
    "text_secondary": "#a0a0a0",
    "success": "#00d9ff",
    "warning": "#ff9f1c",
    "error": "#e94560",
    "border": "#0f3460",
}

@dataclass
class AppConfig:
    """Application configuration dataclass."""

    # Device Settings
    device_name: str = field(default_factory=lambda: f"ShareX-{os.urandom(2).hex().upper()}")
    device_nickname: Optional[str] = None

    # Storage Settings
    download_folder: str = field(default_factory=lambda: str(Path.home() / "storage" / "downloads" / "ShareX"))
    fallback_download_folder: str = field(default_factory=lambda: str(Path.home() / "ShareX" / "downloads"))

    # Network Settings
    port: int = DEFAULT_PORT
    discovery_port: int = DISCOVERY_PORT
    auto_detect_interface: bool = True
    preferred_interface: Optional[str] = None

    # Transfer Settings
    chunk_size: int = DEFAULT_CHUNK_SIZE
    transfer_threads: int = DEFAULT_THREADS
    auto_retry: bool = True
    max_retries: int = MAX_RETRIES
    verify_checksum: bool = True

    # Security Settings
    encryption_enabled: bool = True
    require_trusted_devices: bool = False

    # UI Settings
    theme: str = "dark"
    language: str = "en"
    show_notifications: bool = True
    sound_effects: bool = False

    # Advanced Settings
    log_level: str = "INFO"
    max_log_size_mb: int = 10
    max_history_items: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert config to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Create config from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "AppConfig":
        """Create config from JSON string."""
        return cls.from_dict(json.loads(json_str))


class ConfigManager:
    """Manages application configuration persistence."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        """Initialize configuration manager.

        Args:
            config_dir: Directory to store configuration files.
        """
        self.config_dir = config_dir or Path.home() / ".sharex"
        self.config_file = self.config_dir / "config.json"
        self.config: AppConfig = AppConfig()
        self._ensure_directories()
        self.load()

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Ensure download folder exists
            download_path = Path(self.config.download_folder)
            if not download_path.exists():
                try:
                    download_path.mkdir(parents=True, exist_ok=True)
                except OSError:
                    # Fallback to Termux home directory
                    download_path = Path(self.config.fallback_download_folder)
                    download_path.mkdir(parents=True, exist_ok=True)
                    self.config.download_folder = str(download_path)

            # Ensure logs directory exists
            logs_dir = self.config_dir / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)

        except Exception as e:
            logging.error(f"Failed to create directories: {e}")

    def load(self) -> None:
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                self.config = AppConfig.from_dict(data)
                logging.info("Configuration loaded successfully")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid config file: {e}")
        except Exception as e:
            logging.error(f"Failed to load configuration: {e}")

    def save(self) -> None:
        """Save configuration to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                f.write(self.config.to_json())
            logging.info("Configuration saved successfully")
        except Exception as e:
            logging.error(f"Failed to save configuration: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key.

        Args:
            key: Configuration key.
            default: Default value if key not found.

        Returns:
            Configuration value.
        """
        return getattr(self.config, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value by key.

        Args:
            key: Configuration key.
            value: Value to set.
        """
        if hasattr(self.config, key):
            setattr(self.config, key, value)
            self.save()
        else:
            logging.warning(f"Unknown configuration key: {key}")

    def reset(self) -> None:
        """Reset configuration to defaults."""
        self.config = AppConfig()
        self._ensure_directories()
        self.save()
        logging.info("Configuration reset to defaults")


# Global configuration instance
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get global configuration manager instance.

    Returns:
        ConfigManager instance.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def init_logging() -> None:
    """Initialize application logging."""
    config = get_config()
    log_dir = config.config_dir / "logs"
    log_file = log_dir / "sharex.log"

    logging.basicConfig(
        level=getattr(logging, config.config.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(str(log_file)),
            logging.StreamHandler(),
        ],
    )

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("zeroconf").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
