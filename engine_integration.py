"""Engine Integration for new features.

Extends ShareXEngine with TransferQueue, BrowserPush, and ResumeManager.
All existing methods remain unchanged - new functionality is additive.
"""

import asyncio
import logging
from typing import Optional, Callable, List

from ..core.engine import ShareXEngine, EngineState
from ..services.transfer_queue import TransferQueue, QueuePriority
from ..services.browser_push import BrowserPushService
from ..services.resume_manager import ResumeManager
from ..services.webshare_manager import WebShareManager
from ..models.device import Device
from ..models.transfer import Transfer

logger = logging.getLogger(__name__)


class ExtendedEngine(ShareXEngine):
    """Extended engine with queue, browser push, and resume support.

    Inherits all existing ShareXEngine functionality and adds:
    - TransferQueue for queued transfers
    - BrowserPushService for send-to-browser
    - ResumeManager for robust resume
    """

    def __init__(
        self,
        on_device_update: Optional[Callable[[List[Device]], None]] = None,
        on_transfer_update: Optional[Callable[[Transfer], None]] = None,
        on_notification: Optional[Callable[[str, str], None]] = None,
        on_queue_change: Optional[Callable[[List], None]] = None,
        max_concurrent_transfers: int = 3,
    ) -> None:
        """Initialize extended engine.

        Args:
            on_device_update: Existing device callback.
            on_transfer_update: Existing transfer callback.
            on_notification: Existing notification callback.
            on_queue_change: NEW callback for queue changes.
            max_concurrent_transfers: Max simultaneous transfers.
        """
        super().__init__(
            on_device_update=on_device_update,
            on_transfer_update=on_transfer_update,
            on_notification=on_notification,
        )

        # NEW: Resume manager (must start before queue)
        self.resume_manager = ResumeManager()

        # NEW: Transfer queue (wraps existing transfer_service)
        self.transfer_queue = TransferQueue(
            transfer_service=self.transfer_service,
            max_concurrent=max_concurrent_transfers,
            on_progress=self._on_transfer_progress,
            on_queue_change=on_queue_change,
            on_transfer_complete=self._on_queue_transfer_complete,
        )

        # NEW: Browser push service
        self.browser_push = BrowserPushService()

        # NEW: WebShare manager reference (set externally)
        self.webshare_manager: Optional[WebShareManager] = None

        logger.info("ExtendedEngine initialized")

    async def start(self) -> None:
        """Start all services including new ones."""
        # Start existing services
        await super().start()

        # Start NEW services
        await self.resume_manager.start()
        await self.transfer_queue.start()

        # Attach browser push to webshare if available
        if self.webshare_manager and self.webshare_manager.server:
            self.browser_push.attach_server(self.webshare_manager.server)

        self._notify("Extended engine started", "success")

    async def stop(self) -> None:
        """Stop all services gracefully."""
        # Stop NEW services first
        await self.transfer_queue.stop()
        await self.resume_manager.stop()

        # Stop existing services
        await super().stop()

    # =================================================================
    # QUEUE INTEGRATION (wraps existing send methods)
    # =================================================================

    async def send_file_queued(
        self,
        file_path: str,
        device: Optional[Device] = None,
        priority: QueuePriority = QueuePriority.NORMAL,
    ) -> str:
        """Queue a file for transfer (NEW method).

        Does NOT block - returns immediately with transfer ID.
        Use get_transfer_status(transfer_id) to check progress.

        Args:
            file_path: Path to file.
            device: Target device (None for browser push).
            priority: Queue priority.

        Returns:
            Transfer ID for tracking.
        """
        queued = await self.transfer_queue.enqueue(
            file_path=file_path,
            device=device,
            priority=priority,
        )
        return queued.transfer.id

    async def send_files_queued(
        self,
        file_paths: List[str],
        device: Optional[Device] = None,
        priority: QueuePriority = QueuePriority.NORMAL,
    ) -> List[str]:
        """Queue multiple files for transfer (NEW method).

        Args:
            file_paths: List of file paths.
            device: Target device.
            priority: Queue priority.

        Returns:
            List of transfer IDs.
        """
        results = await self.transfer_queue.enqueue_batch(
            file_paths=file_paths,
            device=device,
            priority=priority,
        )
        return [r.transfer.id for r in results]

    # =================================================================
    # BROWSER PUSH INTEGRATION
    # =================================================================

    async def send_to_browser(
        self,
        file_paths: List[str],
        browser_session_id: str,
    ) -> bool:
        """Push files to a connected browser (NEW method).

        Args:
            file_paths: Files to push.
            browser_session_id: Target browser session ID.

        Returns:
            True if push initiated.
        """
        if not self.webshare_manager or not self.webshare_manager.current_session:
            self._notify("Web Share not active", "error")
            return False

        # Find browser session
        sessions = self.webshare_manager.get_browser_sessions()
        target = None
        for s in sessions:
            if s.id == browser_session_id:
                target = s
                break

        if not target:
            self._notify("Browser session not found", "error")
            return False

        # Ensure browser push is attached
        if self.webshare_manager.server and not self.browser_push.webshare_server:
            self.browser_push.attach_server(self.webshare_manager.server)

        # Push files
        results = await self.browser_push.push_files(
            file_paths=file_paths,
            browser_session=target,
            webshare_session=self.webshare_manager.current_session,
        )

        if results:
            self._notify(f"Pushed {len(results)} file(s) to browser", "success")
            return True
        else:
            self._notify("Browser push failed", "error")
            return False

    # =================================================================
    # QUEUE CONTROL METHODS
    # =================================================================

    def queue_pause(self, transfer_id: str) -> bool:
        """Pause a queued transfer (NEW)."""
        return asyncio.create_task(self.transfer_queue.pause_transfer(transfer_id))

    def queue_resume(self, transfer_id: str) -> bool:
        """Resume a paused transfer (NEW)."""
        return asyncio.create_task(self.transfer_queue.resume_transfer(transfer_id))

    def queue_cancel(self, transfer_id: str) -> bool:
        """Cancel a queued transfer (NEW)."""
        return asyncio.create_task(self.transfer_queue.cancel_transfer(transfer_id))

    def queue_retry(self, transfer_id: str) -> bool:
        """Retry a failed transfer (NEW)."""
        return asyncio.create_task(self.transfer_queue.retry_transfer(transfer_id))

    def queue_skip(self, transfer_id: str) -> bool:
        """Skip a queued transfer (NEW)."""
        return asyncio.create_task(self.transfer_queue.skip_transfer(transfer_id))

    # =================================================================
    # RESUME INTEGRATION
    # =================================================================

    async def resume_interrupted_transfer(self, transfer_id: str) -> bool:
        """Resume an interrupted transfer (NEW method).

        Handles:
        - WiFi disconnect recovery
        - Browser reconnect
        - Temporary network failures
        - App restarts

        Args:
            transfer_id: Transfer ID to resume.

        Returns:
            True if resumed.
        """
        can_resume, offset = await self.resume_manager.can_resume(transfer_id)
        if not can_resume:
            self._notify(f"Cannot resume transfer {transfer_id}", "error")
            return False

        # Get checkpoint details
        checkpoint = await self.resume_manager.get_checkpoint(transfer_id)
        if not checkpoint:
            return False

        # Re-queue with resume
        # The TransferQueue will use resume=True when executing
        self._notify(f"Resuming transfer from {offset} bytes", "info")

        # Find original transfer and re-queue it
        # This would need the original device info stored in checkpoint
        # For now, mark as retry
        await self.transfer_queue.retry_transfer(transfer_id)
        return True

    async def get_recoverable_transfers(self) -> List[dict]:
        """Get list of transfers that can be recovered (NEW)."""
        checkpoints = self.resume_manager.get_recoverable_transfers()
        return [cp.to_dict() for cp in checkpoints]

    # =================================================================
    # CALLBACKS
    # =================================================================

    def _on_queue_transfer_complete(self, transfer: Transfer) -> None:
        """Handle queue transfer completion."""
        # Clean up resume checkpoint on success
        if transfer.status.value == "completed":
            asyncio.create_task(self.resume_manager.remove_checkpoint(transfer.id))

        # Call existing notification
        if transfer.status.value == "completed":
            self._notify(f"Completed: {transfer.file_name}", "success")
        elif transfer.status.value == "failed":
            self._notify(f"Failed: {transfer.file_name} - {transfer.error_message}", "error")

    def set_webshare_manager(self, manager: WebShareManager) -> None:
        """Set the webshare manager for browser push (NEW)."""
        self.webshare_manager = manager
        if manager and manager.server:
            self.browser_push.attach_server(manager.server)
