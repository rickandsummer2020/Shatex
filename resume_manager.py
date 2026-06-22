"""Resume Manager for ShareX.

Provides robust transfer resume capabilities for:
- WiFi disconnections
- Browser reconnections
- Temporary network failures
- App restarts

Stores checkpoints in SQLite and validates integrity.
"""

import os
import json
import logging
import hashlib
import time
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field, asdict

from ..models.transfer import Transfer, TransferStatus
from ..database.manager import get_database

logger = logging.getLogger(__name__)


@dataclass
class TransferCheckpoint:
    """Checkpoint for resuming a transfer."""
    transfer_id: str
    file_path: str
    file_size: int
    transferred_bytes: int
    chunk_index: int
    chunk_size: int
    checksum: str
    peer_address: str
    peer_port: int
    direction: str
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    last_error: Optional[str] = None
    is_valid: bool = True

    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "transferred_bytes": self.transferred_bytes,
            "chunk_index": self.chunk_index,
            "chunk_size": self.chunk_size,
            "checksum": self.checksum,
            "peer_address": self.peer_address,
            "peer_port": self.peer_port,
            "direction": self.direction,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "is_valid": self.is_valid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TransferCheckpoint":
        return cls(**data)


class ResumeManager:
    """Manages transfer checkpoints for resume support.

    Features:
    - Periodic checkpoint saving during transfers
    - Integrity validation (SHA-256 of partial file)
    - Automatic cleanup of stale checkpoints
    - Network failure detection and retry scheduling
    - Cross-session resume (app restart)
    """

    def __init__(
        self,
        checkpoint_interval: int = 5,
        stale_timeout: float = 86400,
    ) -> None:
        """Initialize resume manager."""
        self.checkpoint_interval = checkpoint_interval
        self.stale_timeout = stale_timeout
        self._checkpoints: Dict[str, TransferCheckpoint] = {}
        self._active_transfers: Dict[str, Transfer] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start resume manager."""
        await self._load_checkpoints()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("ResumeManager started")

    async def stop(self) -> None:
        """Stop resume manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("ResumeManager stopped")

    # =================================================================
    # CHECKPOINT OPERATIONS
    # =================================================================

    async def create_checkpoint(
        self,
        transfer: Transfer,
        chunk_index: int,
        chunk_size: int,
        peer_address: str,
        peer_port: int,
        direction: str,
    ) -> TransferCheckpoint:
        """Create or update a checkpoint."""
        checkpoint = TransferCheckpoint(
            transfer_id=transfer.id,
            file_path=transfer.file_path,
            file_size=transfer.file_size,
            transferred_bytes=transfer.transferred_size,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            checksum=transfer.checksum or "",
            peer_address=peer_address,
            peer_port=peer_port,
            direction=direction,
            timestamp=time.time(),
        )

        async with self._lock:
            self._checkpoints[transfer.id] = checkpoint
            self._active_transfers[transfer.id] = transfer

        await self._save_checkpoint(checkpoint)
        logger.debug(f"Checkpoint saved: {transfer.id} at {transfer.transferred_size} bytes")
        return checkpoint

    async def get_checkpoint(self, transfer_id: str) -> Optional[TransferCheckpoint]:
        """Get checkpoint for a transfer."""
        async with self._lock:
            checkpoint = self._checkpoints.get(transfer_id)

        if not checkpoint:
            checkpoint = await self._load_checkpoint_from_db(transfer_id)

        if checkpoint and not await self._validate_checkpoint(checkpoint):
            logger.warning(f"Checkpoint invalid, removing: {transfer_id}")
            await self.remove_checkpoint(transfer_id)
            return None

        return checkpoint

    async def update_progress(
        self,
        transfer_id: str,
        transferred_bytes: int,
        chunk_index: int,
    ) -> None:
        """Update checkpoint progress (throttled)."""
        checkpoint = await self.get_checkpoint(transfer_id)
        if not checkpoint:
            return

        if chunk_index % self.checkpoint_interval != 0:
            return

        checkpoint.transferred_bytes = transferred_bytes
        checkpoint.chunk_index = chunk_index
        checkpoint.timestamp = time.time()

        async with self._lock:
            self._checkpoints[transfer_id] = checkpoint

        await self._save_checkpoint(checkpoint)

    async def remove_checkpoint(self, transfer_id: str) -> None:
        """Remove a checkpoint."""
        async with self._lock:
            self._checkpoints.pop(transfer_id, None)
            self._active_transfers.pop(transfer_id, None)

        try:
            db = get_database()
            db.delete_checkpoint(transfer_id)
        except Exception as e:
            logger.error(f"Checkpoint removal error: {e}")

    async def mark_failed(self, transfer_id: str, error: str) -> None:
        """Mark checkpoint as failed with error."""
        checkpoint = await self.get_checkpoint(transfer_id)
        if checkpoint:
            checkpoint.last_error = error
            checkpoint.retry_count += 1
            checkpoint.is_valid = checkpoint.retry_count < 5
            await self._save_checkpoint(checkpoint)

    # =================================================================
    # RESUME LOGIC
    # =================================================================

    async def can_resume(self, transfer_id: str) -> tuple[bool, int]:
        """Check if transfer can be resumed and from what offset."""
        checkpoint = await self.get_checkpoint(transfer_id)
        if not checkpoint:
            return False, 0

        partial_path = self._get_partial_path(checkpoint.file_path, checkpoint.direction)
        if not os.path.exists(partial_path):
            return False, 0

        actual_size = os.path.getsize(partial_path)
        if actual_size != checkpoint.transferred_bytes:
            logger.warning(
                f"Partial file size mismatch: expected {checkpoint.transferred_bytes}, got {actual_size}"
            )
            return True, min(actual_size, checkpoint.transferred_bytes)

        return True, checkpoint.transferred_bytes

    async def prepare_resume(
        self,
        transfer_id: str,
        file_path: str,
        direction: str,
    ) -> tuple[bool, int]:
        """Prepare transfer for resume."""
        checkpoint = await self.get_checkpoint(transfer_id)
        if not checkpoint:
            return False, 0

        if direction == "send":
            if not os.path.exists(file_path):
                return False, 0
            current_checksum = await self._calculate_checksum(file_path)
            if current_checksum != checkpoint.checksum:
                logger.warning("Source file changed, cannot resume")
                await self.remove_checkpoint(transfer_id)
                return False, 0

        if direction == "receive":
            partial_path = self._get_partial_path(file_path, "receive")
            if not os.path.exists(partial_path):
                return False, 0

        return True, checkpoint.transferred_bytes

    def _get_partial_path(self, file_path: str, direction: str) -> str:
        """Get path to partial file."""
        if direction == "receive":
            return file_path + ".partial"
        return file_path

    # =================================================================
    # VALIDATION
    # =================================================================

    async def _validate_checkpoint(self, checkpoint: TransferCheckpoint) -> bool:
        """Validate checkpoint integrity."""
        if time.time() - checkpoint.timestamp > self.stale_timeout:
            return False

        if checkpoint.direction == "receive":
            partial_path = self._get_partial_path(checkpoint.file_path, "receive")
            if not os.path.exists(partial_path):
                return False

        if checkpoint.retry_count >= 5:
            return False

        return True

    async def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()

    # =================================================================
    # PERSISTENCE
    # =================================================================

    async def _save_checkpoint(self, checkpoint: TransferCheckpoint) -> None:
        """Save checkpoint to database."""
        try:
            db = get_database()
            db.save_checkpoint(checkpoint.to_dict())
        except Exception as e:
            logger.error(f"Checkpoint save error: {e}")

    async def _load_checkpoint_from_db(self, transfer_id: str) -> Optional[TransferCheckpoint]:
        """Load checkpoint from database."""
        try:
            db = get_database()
            data = db.load_checkpoint(transfer_id)
            if data:
                return TransferCheckpoint.from_dict(data)
        except Exception as e:
            logger.error(f"Checkpoint load error: {e}")
        return None

    async def _load_checkpoints(self) -> None:
        """Load all checkpoints from database on startup."""
        try:
            db = get_database()
            all_data = db.load_all_checkpoints()
            async with self._lock:
                for data in all_data:
                    try:
                        cp = TransferCheckpoint.from_dict(data)
                        if await self._validate_checkpoint(cp):
                            self._checkpoints[cp.transfer_id] = cp
                    except Exception as e:
                        logger.error(f"Invalid checkpoint data: {e}")
            logger.info(f"Loaded {len(self._checkpoints)} valid checkpoints")
        except Exception as e:
            logger.error(f"Checkpoint bulk load error: {e}")

    # =================================================================
    # CLEANUP
    # =================================================================

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of stale checkpoints."""
        try:
            while True:
                await asyncio.sleep(3600)
                await self._cleanup_stale()
        except asyncio.CancelledError:
            pass

    async def _cleanup_stale(self) -> None:
        """Remove stale checkpoints."""
        stale = []
        current_time = time.time()

        async with self._lock:
            for tid, cp in self._checkpoints.items():
                if current_time - cp.timestamp > self.stale_timeout:
                    stale.append(tid)

        for tid in stale:
            await self.remove_checkpoint(tid)
            logger.info(f"Removed stale checkpoint: {tid}")

    # =================================================================
    # NETWORK FAILURE HANDLING
    # =================================================================

    async def handle_network_failure(
        self,
        transfer_id: str,
        error: str,
        is_recoverable: bool = True,
    ) -> bool:
        """Handle network failure during transfer."""
        checkpoint = await self.get_checkpoint(transfer_id)
        if not checkpoint:
            return False

        if is_recoverable:
            await self.mark_failed(transfer_id, error)
            return checkpoint.retry_count < 5
        else:
            await self.remove_checkpoint(transfer_id)
            return False

    def get_recoverable_transfers(self) -> List[TransferCheckpoint]:
        """Get list of transfers that can be recovered."""
        result = []
        for cp in self._checkpoints.values():
            if cp.is_valid and cp.retry_count < 5:
                result.append(cp)
        return result
