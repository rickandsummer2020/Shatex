"""Device model for ShareX.

Represents a discovered or connected device.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class DeviceStatus(Enum):
    """Device connection status."""
    OFFLINE = "offline"
    ONLINE = "online"
    BUSY = "busy"
    TRUSTED = "trusted"
    BLOCKED = "blocked"


@dataclass
class Device:
    """Represents a ShareX device.

    Attributes:
        id: Unique device identifier.
        name: Device hostname or identifier.
        nickname: User-friendly device name.
        ip_address: Device IP address.
        port: Device listening port.
        status: Current device status.
        last_seen: Timestamp of last discovery.
        is_trusted: Whether device is trusted.
        public_key: Device public key for encryption.
        metadata: Additional device information.
    """

    id: str
    name: str
    nickname: Optional[str] = None
    ip_address: Optional[str] = None
    port: int = 57575
    status: DeviceStatus = DeviceStatus.OFFLINE
    last_seen: float = field(default_factory=time.time)
    is_trusted: bool = False
    public_key: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate device data after initialization."""
        if not self.id:
            raise ValueError("Device ID cannot be empty")
        if not self.name:
            raise ValueError("Device name cannot be empty")

    @property
    def display_name(self) -> str:
        """Get user-friendly display name."""
        return self.nickname or self.name

    @property
    def is_online(self) -> bool:
        """Check if device is currently online."""
        return self.status in (DeviceStatus.ONLINE, DeviceStatus.BUSY, DeviceStatus.TRUSTED)

    @property
    def address(self) -> str:
        """Get device network address."""
        if self.ip_address:
            return f"{self.ip_address}:{self.port}"
        return "Unknown"

    def update_last_seen(self) -> None:
        """Update last seen timestamp to current time."""
        self.last_seen = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "nickname": self.nickname,
            "ip_address": self.ip_address,
            "port": self.port,
            "status": self.status.value,
            "last_seen": self.last_seen,
            "is_trusted": self.is_trusted,
            "public_key": self.public_key.hex() if self.public_key else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Device":
        """Create device from dictionary.

        Args:
            data: Dictionary containing device data.

        Returns:
            New Device instance.
        """
        return cls(
            id=data["id"],
            name=data["name"],
            nickname=data.get("nickname"),
            ip_address=data.get("ip_address"),
            port=data.get("port", 57575),
            status=DeviceStatus(data.get("status", "offline")),
            last_seen=data.get("last_seen", time.time()),
            is_trusted=data.get("is_trusted", False),
            public_key=bytes.fromhex(data["public_key"]) if data.get("public_key") else None,
            metadata=data.get("metadata", {}),
        )

    def __str__(self) -> str:
        """String representation of device."""
        return f"{self.display_name} ({self.address})"

    def __eq__(self, other: object) -> bool:
        """Check equality based on device ID."""
        if not isinstance(other, Device):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash based on device ID."""
        return hash(self.id)
