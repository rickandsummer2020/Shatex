"""Web Share models for ShareX.

Defines data structures for web share sessions and status.

ENHANCED: Browser session tracking fields.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class WebShareStatus(Enum):
    """Web share session status."""
    INACTIVE = "inactive"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WebShareSession:
    """Represents an active web share session.

    Manages shared files, uploaded files, and browser connection state.

    ENHANCED: Added browser session tracking fields.

    Attributes:
        id: Unique session identifier.
        ip_address: Server IP address.
        port: Server port.
        url: Full URL for accessing the web share.
        status: Current session status.
        allow_upload: Whether uploads are allowed.
        require_password: Whether password is required.
        password: Optional session password.
        expires_at: Optional expiration timestamp.
        files: List of shared files.
        uploaded_files: List of uploaded files.
        qr_code: ASCII QR code string.
        created_at: Session creation timestamp.
        browser_count: Number of active browser sessions.
        browser_sessions: List of active browser session dicts.
        total_browser_downloads: Total downloads across all browsers.
        total_browser_uploads: Total uploads across all browsers.
        total_browser_bytes: Total bytes transferred across all browsers.
    """

    id: str
    ip_address: str
    port: int
    url: str
    status: WebShareStatus = WebShareStatus.INACTIVE
    allow_upload: bool = True
    require_password: bool = False
    password: Optional[str] = None
    expires_at: Optional[float] = None
    files: List[Dict[str, Any]] = field(default_factory=list)
    uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
    qr_code: str = ""
    created_at: float = field(default_factory=time.time)
    max_upload_size: int = 100 * 1024 * 1024  # 100MB default

    # NEW: Browser session tracking fields
    browser_count: int = 0
    browser_sessions: List[Dict[str, Any]] = field(default_factory=list)
    total_browser_downloads: int = 0
    total_browser_uploads: int = 0
    total_browser_bytes: int = 0

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        if self.status != WebShareStatus.ACTIVE:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at:
            return time.time() > self.expires_at
        return False

    @property
    def duration(self) -> float:
        """Session duration in seconds."""
        return time.time() - self.created_at

    @property
    def formatted_duration(self) -> str:
        """Human-readable session duration."""
        duration = int(self.duration)
        if duration < 60:
            return f"{duration}s"
        elif duration < 3600:
            return f"{duration // 60}m {duration % 60}s"
        else:
            return f"{duration // 3600}h {(duration % 3600) // 60}m"

    @property
    def expires_in(self) -> Optional[int]:
        """Seconds until expiration."""
        if self.expires_at:
            remaining = int(self.expires_at - time.time())
            return max(0, remaining)
        return None

    @property
    def formatted_expires_in(self) -> Optional[str]:
        """Human-readable expiration time."""
        expires = self.expires_in
        if expires is None:
            return None
        if expires < 60:
            return f"{expires}s"
        elif expires < 3600:
            return f"{expires // 60}m"
        else:
            return f"{expires // 3600}h {(expires % 3600) // 60}m"

    def add_file(
        self,
        file_name: str,
        file_path: str,
        file_size: int,
    ) -> None:
        """Add a file to the session.

        Args:
            file_name: Display name of the file.
            file_path: Absolute path to the file.
            file_size: File size in bytes.
        """
        self.files.append({
            "name": file_name,
            "path": file_path,
            "size": file_size,
            "added_at": time.time(),
        })

    def remove_file(self, file_name: str) -> bool:
        """Remove a file from the session.

        Args:
            file_name: Name of the file to remove.

        Returns:
            True if file was removed.
        """
        for i, file_info in enumerate(self.files):
            if file_info["name"] == file_name:
                self.files.pop(i)
                return True
        return False

    def add_uploaded_file(
        self,
        file_name: str,
        file_path: str,
        file_size: int,
        uploader_ip: str,
    ) -> None:
        """Add an uploaded file to the session.

        Args:
            file_name: Name of the uploaded file.
            file_path: Path where file was saved.
            file_size: Size of the uploaded file.
            uploader_ip: IP address of the uploader.
        """
        self.uploaded_files.append({
            "name": file_name,
            "path": file_path,
            "size": file_size,
            "uploader_ip": uploader_ip,
            "uploaded_at": time.time(),
        })

    # NEW: Update browser session information
    def update_browser_info(
        self,
        count: int,
        sessions: List[Dict[str, Any]],
        total_downloads: int = 0,
        total_uploads: int = 0,
        total_bytes: int = 0,
    ) -> None:
        """Update browser session tracking information.

        Args:
            count: Number of active browser sessions.
            sessions: List of browser session dictionaries.
            total_downloads: Total downloads across all browsers.
            total_uploads: Total uploads across all browsers.
            total_bytes: Total bytes transferred across all browsers.
        """
        self.browser_count = count
        self.browser_sessions = sessions
        self.total_browser_downloads = total_downloads
        self.total_browser_uploads = total_uploads
        self.total_browser_bytes = total_bytes

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status.value,
            "is_active": self.is_active,
            "allow_upload": self.allow_upload,
            "require_password": self.require_password,
            "files_count": len(self.files),
            "uploaded_count": len(self.uploaded_files),
            "duration": self.formatted_duration,
            "expires_in": self.formatted_expires_in,
            # NEW: Browser info
            "browser_count": self.browser_count,
            "browser_sessions": self.browser_sessions,
            "total_browser_downloads": self.total_browser_downloads,
            "total_browser_uploads": self.total_browser_uploads,
            "total_browser_bytes": self.total_browser_bytes,
        }
