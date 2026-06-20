"""Web Share model for ShareX.

Represents an active web sharing session.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class WebShareStatus(Enum):
    """Web share session status."""
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WebShareSession:
    """Represents a web sharing session.

    Attributes:
        id: Unique session identifier.
        status: Current session status.
        ip_address: Local IP address.
        port: HTTP server port.
        url: Full download URL.
        qr_code: ASCII QR code representation.
        files: List of shared files.
        uploaded_files: List of received files.
        max_upload_size: Maximum upload size in bytes.
        allow_upload: Whether to allow file uploads.
        require_password: Whether password is required.
        password: Session password.
        expires_at: Session expiration timestamp.
        created_at: Session creation timestamp.
        metadata: Additional session information.
    """

    id: str
    ip_address: str
    port: int
    url: str
    status: WebShareStatus = WebShareStatus.STARTING
    qr_code: Optional[str] = None
    files: List[Dict[str, Any]] = field(default_factory=list)
    uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
    max_upload_size: int = 1073741824  # 1GB default
    allow_upload: bool = True
    require_password: bool = False
    password: Optional[str] = None
    expires_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate session data after initialization."""
        if not self.id:
            raise ValueError("Session ID cannot be empty")
        if not self.ip_address:
            raise ValueError("IP address cannot be empty")
        if not self.url:
            raise ValueError("URL cannot be empty")

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.status == WebShareStatus.ACTIVE

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def duration(self) -> float:
        """Get session duration in seconds."""
        return time.time() - self.created_at

    @property
    def formatted_duration(self) -> str:
        """Get human-readable session duration."""
        duration = int(self.duration)
        if duration < 60:
            return f"{duration}s"
        elif duration < 3600:
            minutes = duration // 60
            secs = duration % 60
            return f"{minutes}m {secs}s"
        else:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            return f"{hours}h {minutes}m"

    def add_file(self, file_name: str, file_path: str, file_size: int) -> None:
        """Add a file to the sharing session.

        Args:
            file_name: Name of the file.
            file_path: Path to the file.
            file_size: Size of the file in bytes.
        """
        self.files.append({
            "name": file_name,
            "path": file_path,
            "size": file_size,
            "added_at": time.time(),
        })

    def add_uploaded_file(self, file_name: str, file_path: str, file_size: int, 
                         uploader_ip: Optional[str] = None) -> None:
        """Add an uploaded file to the session.

        Args:
            file_name: Name of the uploaded file.
            file_path: Path where file was saved.
            file_size: Size of the file in bytes.
            uploader_ip: IP address of the uploader.
        """
        self.uploaded_files.append({
            "name": file_name,
            "path": file_path,
            "size": file_size,
            "uploader_ip": uploader_ip,
            "uploaded_at": time.time(),
        })

    def remove_file(self, file_name: str) -> bool:
        """Remove a file from the sharing session.

        Args:
            file_name: Name of the file to remove.

        Returns:
            True if file was removed, False otherwise.
        """
        for i, file in enumerate(self.files):
            if file["name"] == file_name:
                self.files.pop(i)
                return True
        return False

    def get_total_size(self) -> int:
        """Get total size of all shared files.

        Returns:
            Total size in bytes.
        """
        return sum(file["size"] for file in self.files)

    def get_uploaded_total_size(self) -> int:
        """Get total size of all uploaded files.

        Returns:
            Total size in bytes.
        """
        return sum(file["size"] for file in self.uploaded_files)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "id": self.id,
            "status": self.status.value,
            "ip_address": self.ip_address,
            "port": self.port,
            "url": self.url,
            "qr_code": self.qr_code,
            "files": self.files,
            "uploaded_files": self.uploaded_files,
            "max_upload_size": self.max_upload_size,
            "allow_upload": self.allow_upload,
            "require_password": self.require_password,
            "password": self.password,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebShareSession":
        """Create session from dictionary."""
        return cls(
            id=data["id"],
            ip_address=data["ip_address"],
            port=data["port"],
            url=data["url"],
            status=WebShareStatus(data.get("status", "starting")),
            qr_code=data.get("qr_code"),
            files=data.get("files", []),
            uploaded_files=data.get("uploaded_files", []),
            max_upload_size=data.get("max_upload_size", 1073741824),
            allow_upload=data.get("allow_upload", True),
            require_password=data.get("require_password", False),
            password=data.get("password"),
            expires_at=data.get("expires_at"),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )

    def __str__(self) -> str:
        """String representation."""
        return f"WebShare({self.url}) - {self.status.value}"
