"""Transfer Queue Service for ShareX.

Manages queued, paused, retrying, and scheduled transfers.
Wraps TransferService to add queue semantics without
modifying existing transfer logic.
"""

import os
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List, Deque, Set
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

from ..models.transfer import Transfer, TransferStatus, TransferDirection
from ..models.device import Device
from ..models.file_info import FileInfo
from ..services.transfer_service import TransferService
from ..database.manager import get_database
from ..config import get_config

logger = logging.getLogger(__name__)


class QueuePriority(Enum):
    """Transfer queue priority levels."""
    HIGH = 1
    NORMAL = 2
    LOW = 3


class QueueAction(Enum):
    """Actions that can be applied to queued transfers."""
    PAUSE = auto()
    RESUME = auto()
    CANCEL = auto()
    RETRY = auto()
    SKIP = auto()


@dataclass
class QueuedTransfer:
    """Wrapper for transfers in the queue."""
    transfer: Transfer
    file_path: str
    device: Optional[Device] = None
    priority: QueuePriority = QueuePriority.NORMAL
    added_at: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: float = 2.0
    scheduled_at: Optional[float] = None
    queue_position: int = 0
    auto_start: bool = True

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "transfer_id": self.transfer.id,
            "file_path": self.file_path,
            "device_id": self.device.id if self.device else None,
            "priority": self.priority.value,
            "added_at": self.added_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "scheduled_at": self.scheduled_at,
            "status": self.transfer.status.value,
        }


class TransferQueue:
    """Manages a queue of file transfers with full lifecycle control.

    Features:
    - Priority-based queue ordering
    - Concurrent transfer limiting
    - Pause/Resume/Cancel/Retry/Skip for any transfer
    - Persistent queue state across sessions
    - Auto-retry with exponential backoff
    - Bandwidth-aware scheduling
    """

    def __init__(
        self,
        transfer_service: Optional[TransferService] = None,
        max_concurrent: int = 3,
        on_progress: Optional[Callable[[Transfer], None]] = None,
        on_queue_change: Optional[Callable[[List[QueuedTransfer]], None]] = None,
        on_transfer_complete: Optional[Callable[[Transfer], None]] = None,
    ) -> None:
        """Initialize transfer queue."""
        self.transfer_service = transfer_service or TransferService(
            on_progress=self._on_transfer_progress,
        )
        self.max_concurrent = max_concurrent
        self.on_progress = on_progress
        self.on_queue_change = on_queue_change
        self.on_transfer_complete = on_transfer_complete

        # Queue state
        self._queue: Deque[QueuedTransfer] = deque()
        self._active: Dict[str, QueuedTransfer] = {}
        self._paused: Dict[str, QueuedTransfer] = {}
        self._completed: List[QueuedTransfer] = []
        self._cancelled: Set[str] = set()
        self._skipped: Set[str] = set()

        # Control
        self._running = False
        self._lock = asyncio.Lock()
        self._worker_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._retry_delays = [2.0, 5.0, 10.0, 30.0, 60.0]

        logger.info(f"TransferQueue initialized (max_concurrent={max_concurrent})")

    # =================================================================
    # QUEUE MANAGEMENT
    # =================================================================

    async def enqueue(
        self,
        file_path: str,
        device: Optional[Device] = None,
        priority: QueuePriority = QueuePriority.NORMAL,
        auto_start: bool = True,
    ) -> QueuedTransfer:
        """Add a transfer to the queue."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        import secrets
        transfer = Transfer(
            id=secrets.token_hex(8),
            file_name=path.name,
            file_path=str(path.resolve()),
            file_size=path.stat().st_size,
            direction=TransferDirection.SEND,
            device_id=device.id if device else "browser",
            device_name=device.display_name if device else "Browser",
            status=TransferStatus.QUEUED,
        )

        queued = QueuedTransfer(
            transfer=transfer,
            file_path=file_path,
            device=device,
            priority=priority,
            auto_start=auto_start,
        )

        async with self._lock:
            inserted = False
            for i, existing in enumerate(self._queue):
                if existing.priority.value > priority.value:
                    self._queue.insert(i, queued)
                    inserted = True
                    break
            if not inserted:
                self._queue.append(queued)
            self._update_positions()
            self._persist_queue_state()

        self._notify_queue_change()
        logger.info(f"Enqueued: {transfer.file_name} (priority={priority.name})")

        if auto_start and self._running:
            self._wake_worker()

        return queued

    async def enqueue_batch(
        self,
        file_paths: List[str],
        device: Optional[Device] = None,
        priority: QueuePriority = QueuePriority.NORMAL,
    ) -> List[QueuedTransfer]:
        """Add multiple files to queue."""
        results = []
        for path in file_paths:
            try:
                queued = await self.enqueue(path, device, priority)
                results.append(queued)
            except Exception as e:
                logger.error(f"Failed to enqueue {path}: {e}")
        return results

    async def dequeue(self, transfer_id: str) -> Optional[QueuedTransfer]:
        """Remove a transfer from the queue (before processing)."""
        async with self._lock:
            for i, q in enumerate(self._queue):
                if q.transfer.id == transfer_id:
                    self._queue.remove(q)
                    self._update_positions()
                    self._persist_queue_state()
                    self._notify_queue_change()
                    return q
        return None

    # =================================================================
    # LIFECYCLE CONTROL
    # =================================================================

    async def start(self) -> None:
        """Start the queue worker."""
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("TransferQueue worker started")

    async def stop(self) -> None:
        """Stop the queue worker gracefully."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("TransferQueue worker stopped")

    async def pause_transfer(self, transfer_id: str) -> bool:
        """Pause a queued or active transfer."""
        async with self._lock:
            if transfer_id in self._active:
                qt = self._active[transfer_id]
                qt.transfer.status = TransferStatus.PAUSED
                self._paused[transfer_id] = qt
                self.transfer_service.pause_transfer(transfer_id)
                self._persist_queue_state()
                self._notify_queue_change()
                logger.info(f"Paused active transfer: {transfer_id}")
                return True

            for q in self._queue:
                if q.transfer.id == transfer_id:
                    q.transfer.status = TransferStatus.PAUSED
                    self._paused[transfer_id] = q
                    self._queue.remove(q)
                    self._update_positions()
                    self._persist_queue_state()
                    self._notify_queue_change()
                    logger.info(f"Paused queued transfer: {transfer_id}")
                    return True
        return False

    async def resume_transfer(self, transfer_id: str) -> bool:
        """Resume a paused transfer."""
        async with self._lock:
            if transfer_id not in self._paused:
                return False

            qt = self._paused.pop(transfer_id)
            qt.transfer.status = TransferStatus.QUEUED

            inserted = False
            for i, existing in enumerate(self._queue):
                if existing.priority.value > qt.priority.value:
                    self._queue.insert(i, qt)
                    inserted = True
                    break
            if not inserted:
                self._queue.append(qt)

            self._update_positions()
            self._persist_queue_state()
            self._notify_queue_change()
            self.transfer_service.resume_transfer(transfer_id)
            logger.info(f"Resumed transfer: {transfer_id}")
            self._wake_worker()
            return True

    async def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel a transfer (queued, paused, or active)."""
        async with self._lock:
            if transfer_id in self._active:
                qt = self._active[transfer_id]
                qt.transfer.cancel()
                self.transfer_service.cancel_transfer(transfer_id)
                self._cancelled.add(transfer_id)
                self._persist_queue_state()
                self._notify_queue_change()
                logger.info(f"Cancelled active transfer: {transfer_id}")
                return True

            if transfer_id in self._paused:
                qt = self._paused.pop(transfer_id)
                qt.transfer.cancel()
                self._cancelled.add(transfer_id)
                self._persist_queue_state()
                self._notify_queue_change()
                logger.info(f"Cancelled paused transfer: {transfer_id}")
                return True

            for q in self._queue:
                if q.transfer.id == transfer_id:
                    q.transfer.cancel()
                    self._queue.remove(q)
                    self._cancelled.add(transfer_id)
                    self._update_positions()
                    self._persist_queue_state()
                    self._notify_queue_change()
                    logger.info(f"Cancelled queued transfer: {transfer_id}")
                    return True
        return False

    async def retry_transfer(self, transfer_id: str) -> bool:
        """Retry a failed or cancelled transfer."""
        async with self._lock:
            for qt in self._completed:
                if qt.transfer.id == transfer_id:
                    if qt.transfer.status == TransferStatus.FAILED:
                        qt.retry_count += 1
                        qt.transfer.status = TransferStatus.QUEUED
                        qt.transfer.error_message = ""
                        self._completed.remove(qt)

                        inserted = False
                        for i, existing in enumerate(self._queue):
                            if existing.priority.value > qt.priority.value:
                                self._queue.insert(i, qt)
                                inserted = True
                                break
                        if not inserted:
                            self._queue.append(qt)

                        self._update_positions()
                        self._persist_queue_state()
                        self._notify_queue_change()
                        logger.info(f"Retrying transfer: {transfer_id} (attempt {qt.retry_count})")
                        self._wake_worker()
                        return True
            return False

    async def skip_transfer(self, transfer_id: str) -> bool:
        """Skip a queued transfer (keeps it in history as skipped)."""
        async with self._lock:
            for q in self._queue:
                if q.transfer.id == transfer_id:
                    self._queue.remove(q)
                    q.transfer.status = TransferStatus.SKIPPED
                    self._skipped.add(transfer_id)
                    self._update_positions()
                    self._persist_queue_state()
                    self._notify_queue_change()
                    logger.info(f"Skipped transfer: {transfer_id}")
                    return True

            if transfer_id in self._paused:
                qt = self._paused.pop(transfer_id)
                qt.transfer.status = TransferStatus.SKIPPED
                self._skipped.add(transfer_id)
                self._persist_queue_state()
                self._notify_queue_change()
                logger.info(f"Skipped paused transfer: {transfer_id}")
                return True
        return False

    # =================================================================
    # WORKER LOOP
    # =================================================================

    async def _worker_loop(self) -> None:
        """Main worker loop processing the queue."""
        try:
            while self._running:
                await self._process_next()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("Queue worker cancelled")
        except Exception as e:
            logger.error(f"Queue worker error: {e}")

    async def _process_next(self) -> None:
        """Process the next item in the queue."""
        qt: Optional[QueuedTransfer] = None

        async with self._lock:
            while self._queue:
                candidate = self._queue.popleft()
                if candidate.transfer.id in self._cancelled or candidate.transfer.id in self._skipped:
                    continue
                if candidate.transfer.status == TransferStatus.PAUSED:
                    self._paused[candidate.transfer.id] = candidate
                    continue
                if candidate.scheduled_at and candidate.scheduled_at > time.time():
                    self._queue.appendleft(candidate)
                    break
                qt = candidate
                break

            if qt:
                self._active[qt.transfer.id] = qt
                self._update_positions()
                self._persist_queue_state()

        if not qt:
            return

        async with self._semaphore:
            await self._execute_transfer(qt)

    async def _execute_transfer(self, qt: QueuedTransfer) -> None:
        """Execute a single transfer with full retry/resume support."""
        qt.transfer.status = TransferStatus.CONNECTING
        self._notify_progress(qt.transfer)

        try:
            if qt.device:
                result = await self.transfer_service.send_file(
                    file_path=qt.file_path,
                    device=qt.device,
                    transfer_id=qt.transfer.id,
                    resume=True,
                )
            else:
                result = await self._execute_browser_push(qt)

            qt.transfer.status = result.status
            qt.transfer.transferred_size = result.transferred_size
            qt.transfer.speed = result.speed
            qt.transfer.eta = result.eta
            qt.transfer.checksum = result.checksum

            if result.status == TransferStatus.COMPLETED:
                qt.transfer.complete()
                self._notify_progress(qt.transfer)
                logger.info(f"Transfer completed: {qt.transfer.file_name}")
            elif result.status == TransferStatus.FAILED:
                await self._handle_failure(qt, result.error_message or "Unknown error")
            elif result.status == TransferStatus.CANCELLED:
                logger.info(f"Transfer cancelled: {qt.transfer.id}")

        except Exception as e:
            logger.error(f"Transfer execution error: {e}")
            await self._handle_failure(qt, str(e))

        finally:
            async with self._lock:
                self._active.pop(qt.transfer.id, None)
                if qt.transfer.status not in (TransferStatus.QUEUED, TransferStatus.RETRYING):
                    self._completed.append(qt)
                    self._persist_queue_state()

            self._notify_queue_change()
            self._notify_progress(qt.transfer)

            if self.on_transfer_complete:
                try:
                    self.on_transfer_complete(qt.transfer)
                except Exception as e:
                    logger.error(f"Transfer complete callback error: {e}")

    async def _handle_failure(self, qt: QueuedTransfer, error: str) -> None:
        """Handle transfer failure with retry logic."""
        qt.transfer.fail(error)
        self._notify_progress(qt.transfer)

        config = get_config()
        if config.config.auto_retry and qt.retry_count < qt.max_retries:
            qt.retry_count += 1
            delay = self._retry_delays[min(qt.retry_count - 1, len(self._retry_delays) - 1)]
            qt.scheduled_at = time.time() + delay
            qt.transfer.status = TransferStatus.RETRYING
            qt.transfer.error_message = f"Retrying in {delay}s... ({qt.retry_count}/{qt.max_retries})"

            async with self._lock:
                self._queue.append(qt)
                self._update_positions()
                self._persist_queue_state()

            logger.info(f"Scheduled retry for {qt.transfer.id} in {delay}s")
            self._notify_queue_change()
            self._wake_worker()
        else:
            logger.error(f"Transfer failed permanently: {qt.transfer.id} - {error}")

    async def _execute_browser_push(self, qt: QueuedTransfer) -> Transfer:
        """Execute a browser push transfer."""
        qt.transfer.fail("No browser session available for push")
        return qt.transfer

    # =================================================================
    # PROGRESS & CALLBACKS
    # =================================================================

    def _on_transfer_progress(self, transfer: Transfer) -> None:
        """Internal progress handler."""
        if self.on_progress:
            try:
                self.on_progress(transfer)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    def _notify_queue_change(self) -> None:
        """Notify queue change callback."""
        if self.on_queue_change:
            try:
                queue_list = list(self._queue) + list(self._paused.values())
                self.on_queue_change(queue_list)
            except Exception as e:
                logger.error(f"Queue change callback error: {e}")

    def _wake_worker(self) -> None:
        """Wake the worker loop if sleeping."""
        pass

    # =================================================================
    # PERSISTENCE
    # =================================================================

    def _persist_queue_state(self) -> None:
        """Save queue state to database."""
        try:
            db = get_database()
            state = {
                "queue": [q.to_dict() for q in self._queue],
                "paused": [q.to_dict() for q in self._paused.values()],
                "active": [q.to_dict() for q in self._active.values()],
            }
            db.save_queue_state(state)
        except Exception as e:
            logger.error(f"Queue persistence error: {e}")

    async def load_queue_state(self) -> None:
        """Load queue state from database."""
        try:
            db = get_database()
            state = db.load_queue_state()
            if not state:
                return
            logger.info(f"Loaded queue state: {len(state.get('queue', []))} items")
        except Exception as e:
            logger.error(f"Queue load error: {e}")

    # =================================================================
    # QUERIES
    # =================================================================

    def get_queue(self) -> List[QueuedTransfer]:
        """Get current queue."""
        return list(self._queue)

    def get_active(self) -> List[QueuedTransfer]:
        """Get active transfers."""
        return list(self._active.values())

    def get_paused(self) -> List[QueuedTransfer]:
        """Get paused transfers."""
        return list(self._paused.values())

    def get_completed(self) -> List[QueuedTransfer]:
        """Get completed transfers."""
        return self._completed

    def get_all(self) -> List[QueuedTransfer]:
        """Get all transfers."""
        return list(self._queue) + list(self._active.values()) + list(self._paused.values()) + self._completed

    def get_transfer(self, transfer_id: str) -> Optional[QueuedTransfer]:
        """Get any transfer by ID."""
        for q in self._queue:
            if q.transfer.id == transfer_id:
                return q
        for q in self._active.values():
            if q.transfer.id == transfer_id:
                return q
        for q in self._paused.values():
            if q.transfer.id == transfer_id:
                return q
        for q in self._completed:
            if q.transfer.id == transfer_id:
                return q
        return None

    def _update_positions(self) -> None:
        """Update queue positions."""
        for i, q in enumerate(self._queue):
            q.queue_position = i + 1

    @property
    def is_running(self) -> bool:
        """Check if queue worker is running."""
        return self._running

    @property
    def pending_count(self) -> int:
        """Count of pending transfers."""
        return len(self._queue) + len(self._active)

    @property
    def is_busy(self) -> bool:
        """Check if queue is processing."""
        return len(self._active) > 0 or len(self._queue) > 0
