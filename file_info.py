"""File information model for ShareX.

Represents metadata about a file or folder.
"""

import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class FileInfo:
    """Represents file or folder information.

    Attributes:
        name: File or folder name.
        path: Full path to the file or folder.
        size: Size in bytes (0 for folders).
        is_directory: Whether this is a directory.
        modified_time: Last modification timestamp.
        checksum: SHA-256 checksum (for files only).
        mime_type: MIME type of the file.
        children: List of child items (for directories).
        metadata: Additional file information.
    """

    name: str
    path: str
    size: int = 0
    is_directory: bool = False
    modified_time: float = 0.0
    checksum: Optional[str] = None
    mime_type: Optional[str] = None
    children: List["FileInfo"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate file info after initialization."""
        if not self.name:
            raise ValueError("File name cannot be empty")
        if not self.path:
            raise ValueError("File path cannot be empty")

    @property
    def formatted_size(self) -> str:
        """Get human-readable file size."""
        if self.is_directory:
            return f"{len(self.children)} items"
        return self._format_bytes(self.size)

    @property
    def formatted_time(self) -> str:
        """Get human-readable modification time."""
        dt = datetime.fromtimestamp(self.modified_time)
        return dt.strftime("%Y-%m-%d %H:%M")

    @property
    def extension(self) -> str:
        """Get file extension."""
        return Path(self.name).suffix.lower()

    @classmethod
    def from_path(cls, path: str, calculate_checksum: bool = False) -> "FileInfo":
        """Create FileInfo from filesystem path.

        Args:
            path: Path to the file or folder.
            calculate_checksum: Whether to calculate SHA-256 checksum.

        Returns:
            New FileInfo instance.
        """
        path_obj = Path(path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        stat = path_obj.stat()
        is_dir = path_obj.is_dir()

        file_info = cls(
            name=path_obj.name,
            path=str(path_obj.resolve()),
            size=0 if is_dir else stat.st_size,
            is_directory=is_dir,
            modified_time=stat.st_mtime,
        )

        if is_dir:
            try:
                for child in path_obj.iterdir():
                    try:
                        file_info.children.append(cls.from_path(str(child), False))
                    except (PermissionError, OSError):
                        continue
            except PermissionError:
                pass
        elif calculate_checksum:
            file_info.checksum = file_info.calculate_sha256()

        return file_info

    def calculate_sha256(self) -> str:
        """Calculate SHA-256 checksum of the file.

        Returns:
            Hexadecimal checksum string.
        """
        if self.is_directory:
            return ""

        sha256 = hashlib.sha256()
        try:
            with open(self.path, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (IOError, OSError) as e:
            raise IOError(f"Failed to calculate checksum: {e}")

    def get_all_files(self) -> List["FileInfo"]:
        """Get all files recursively (for directories).

        Returns:
            List of all file items.
        """
        if not self.is_directory:
            return [self]

        files = []
        for child in self.children:
            files.extend(child.get_all_files())
        return files

    def get_total_size(self) -> int:
        """Get total size including all children.

        Returns:
            Total size in bytes.
        """
        if not self.is_directory:
            return self.size

        return sum(child.get_total_size() for child in self.children)

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def to_dict(self) -> Dict[str, Any]:
        """Convert file info to dictionary."""
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "is_directory": self.is_directory,
            "modified_time": self.modified_time,
            "checksum": self.checksum,
            "mime_type": self.mime_type,
            "children": [child.to_dict() for child in self.children],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileInfo":
        """Create file info from dictionary."""
        file_info = cls(
            name=data["name"],
            path=data["path"],
            size=data.get("size", 0),
            is_directory=data.get("is_directory", False),
            modified_time=data.get("modified_time", 0.0),
            checksum=data.get("checksum"),
            mime_type=data.get("mime_type"),
            metadata=data.get("metadata", {}),
        )
        file_info.children = [cls.from_dict(child) for child in data.get("children", [])]
        return file_info

    def __str__(self) -> str:
        """String representation."""
        if self.is_directory:
            return f"📁 {self.name}/ ({len(self.children)} items)"
        return f"📄 {self.name} ({self.formatted_size})"
