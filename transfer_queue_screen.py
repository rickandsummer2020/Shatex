"""Transfer Queue screen for ShareX.

Provides UI for managing the transfer queue with full
control over pause, resume, retry, cancel, and skip.
"""

import asyncio
import logging
from typing import Optional, List
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Static, Button, Label, ListView, ListItem, Header, Footer, ProgressBar,
)

from ..services.transfer_queue import TransferQueue, QueuedTransfer, QueuePriority
from ..models.transfer import Transfer, TransferStatus
from ..ui.modals import ConfirmDialog, ErrorDialog, InfoDialog

logger = logging.getLogger(__name__)


class QueueListItem(ListItem):
    """Custom list item for queue entries."""
    STATUS_COLORS = {
        "queued": "yellow",
        "transferring": "green",
        "paused": "blue",
        "retrying": "yellow",
        "failed": "red",
        "completed": "green",
        "cancelled": "red",
        "skipped": "dim",
    }

    def __init__(self, queued: QueuedTransfer) -> None:
        self.queued = queued
        t = queued.transfer
        status_color = self.STATUS_COLORS.get(t.status.value, "white")
        progress = ""
        if t.file_size > 0:
            pct = (t.transferred_size / t.file_size) * 100
            progress = f" {pct:.1f}%"
        label = f"{t.file_name} → {t.device_name} [{status_color}]{t.status.value.upper()}[/{status_color}]{progress}"
        super().__init__(Label(label))


class TransferQueueScreen(Screen):
    """Screen for managing the transfer queue."""

    CSS = """
    Screen { align: center middle; }
    .container { width: 100%; height: 100%; padding: 0 1; }
    .header { height: auto; text-align: center; color: $primary; text-style: bold; padding: 1 0; border-bottom: solid $primary; }
    .stats-bar { height: auto; layout: grid; grid-size: 4; grid-gutter: 1; padding: 1 0; }
    .stat { text-align: center; }
    .stat-value { color: $primary; text-style: bold; }
    .stat-label { color: $text-muted; text-style: italic; }
    .queue-section { height: 1fr; border: solid $primary-darken-2; padding: 1; margin: 1 0; }
    .section-title { color: $primary; text-style: bold; padding: 0 0 1 0; }
    .controls { height: auto; padding: 1 0; }
    .detail-panel { height: auto; border: solid $surface-darken-1; padding: 1; margin: 1 0; }
    .empty-state { text-align: center; color: $text-muted; padding: 2; }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("q", "quit", "Quit"),
        ("p", "pause_selected", "Pause"),
        ("r", "resume_selected", "Resume"),
        ("c", "cancel_selected", "Cancel"),
        ("x", "retry_selected", "Retry"),
        ("k", "skip_selected", "Skip"),
        ("a", "add_transfer", "Add"),
    ]

    queue_items: reactive[List[QueuedTransfer]] = reactive([])
    selected_item: reactive[Optional[QueuedTransfer]] = reactive(None)

    def __init__(self, transfer_queue: Optional[TransferQueue] = None) -> None:
        super().__init__()
        self.transfer_queue = transfer_queue

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="container"):
            yield Static("Transfer Queue", classes="header")
            with Container(classes="stats-bar"):
                with Container(classes="stat"):
                    yield Static("0", classes="stat-value", id="stat-queued")
                    yield Static("Queued", classes="stat-label")
                with Container(classes="stat"):
                    yield Static("0", classes="stat-value", id="stat-active")
                    yield Static("Active", classes="stat-label")
                with Container(classes="stat"):
                    yield Static("0", classes="stat-value", id="stat-paused")
                    yield Static("Paused", classes="stat-label")
                with Container(classes="stat"):
                    yield Static("0", classes="stat-value", id="stat-completed")
                    yield Static("Completed", classes="stat-label")
            with Container(classes="queue-section"):
                yield Static("Queue", classes="section-title")
                yield Static("Queue is empty", classes="empty-state", id="empty-queue")
                yield ListView(id="queue-list")
            with Container(classes="detail-panel", id="detail-panel"):
                yield Static("Select a transfer to view details", id="detail-text")
            with Container(classes="controls"):
                with Horizontal():
                    yield Button("Pause", id="btn-pause", variant="primary", disabled=True)
                    yield Button("Resume", id="btn-resume", variant="success", disabled=True)
                    yield Button("Cancel", id="btn-cancel", variant="error", disabled=True)
                    yield Button("Retry", id="btn-retry", variant="warning", disabled=True)
                    yield Button("Skip", id="btn-skip", variant="warning", disabled=True)
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(1.0, self._refresh_queue)
        await self._refresh_queue()

    async def _refresh_queue(self) -> None:
        if not self.transfer_queue:
            return
        all_items = (
            self.transfer_queue.get_queue()
            + self.transfer_queue.get_active()
            + self.transfer_queue.get_paused()
            + self.transfer_queue.get_completed()[-20:]
        )
        self.queue_items = all_items
        self._update_list(all_items)
        self._update_stats()

    def _update_list(self, items: List[QueuedTransfer]) -> None:
        queue_list = self.query_one("#queue-list", ListView)
        empty = self.query_one("#empty-queue", Static)
        queue_list.clear()
        if not items:
            empty.styles.display = "block"
            return
        empty.styles.display = "none"
        for item in items:
            queue_list.append(QueueListItem(item))

    def _update_stats(self) -> None:
        if not self.transfer_queue:
            return
        self.query_one("#stat-queued", Static).update(str(len(self.transfer_queue.get_queue())))
        self.query_one("#stat-active", Static).update(str(len(self.transfer_queue.get_active())))
        self.query_one("#stat-paused", Static).update(str(len(self.transfer_queue.get_paused())))
        self.query_one("#stat-completed", Static).update(str(len(self.transfer_queue.get_completed())))

    def _update_detail_panel(self, item: Optional[QueuedTransfer]) -> None:
        detail = self.query_one("#detail-text", Static)
        if not item:
            detail.update("Select a transfer to view details")
            return
        t = item.transfer
        lines = [
            f"File: {t.file_name}",
            f"Size: {self._format_size(t.file_size)}",
            f"Transferred: {self._format_size(t.transferred_size)}",
            f"Status: {t.status.value.upper()}",
            f"Device: {t.device_name}",
            f"Speed: {self._format_speed(t.speed)}",
            f"ETA: {self._format_eta(t.eta)}",
            f"Retries: {item.retry_count}/{item.max_retries}",
            f"Queue Position: {item.queue_position}",
        ]
        detail.update("\n".join(lines))
        self._update_buttons(t.status)

    def _update_buttons(self, status: TransferStatus) -> None:
        can_pause = status in (TransferStatus.QUEUED, TransferStatus.TRANSFERRING, TransferStatus.CONNECTING)
        can_resume = status == TransferStatus.PAUSED
        can_cancel = status in (TransferStatus.QUEUED, TransferStatus.TRANSFERRING, TransferStatus.CONNECTING, TransferStatus.PAUSED, TransferStatus.RETRYING)
        can_retry = status == TransferStatus.FAILED
        can_skip = status == TransferStatus.QUEUED
        self.query_one("#btn-pause", Button).disabled = not can_pause
        self.query_one("#btn-resume", Button).disabled = not can_resume
        self.query_one("#btn-cancel", Button).disabled = not can_cancel
        self.query_one("#btn-retry", Button).disabled = not can_retry
        self.query_one("#btn-skip", Button).disabled = not can_skip

    def _format_size(self, size: int) -> str:
        if size == 0:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB"]:
            if abs(size) < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _format_speed(self, speed: float) -> str:
        if speed == 0:
            return "-"
        return f"{self._format_size(int(speed))}/s"

    def _format_eta(self, eta: float) -> str:
        if eta == 0 or eta == float("inf"):
            return "-"
        if eta < 60:
            return f"{int(eta)}s"
        elif eta < 3600:
            return f"{int(eta // 60)}m {int(eta % 60)}s"
        else:
            return f"{int(eta // 3600)}h {int((eta % 3600) // 60)}m"

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, QueueListItem):
            self.selected_item = event.item.queued
            self._update_detail_panel(event.item.queued)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self.selected_item or not self.transfer_queue:
            return
        tid = self.selected_item.transfer.id
        btn_id = event.button.id
        if btn_id == "btn-pause":
            await self.transfer_queue.pause_transfer(tid)
        elif btn_id == "btn-resume":
            await self.transfer_queue.resume_transfer(tid)
        elif btn_id == "btn-cancel":
            confirmed = await self.app.push_screen(ConfirmDialog("Cancel this transfer?"))
            if confirmed:
                await self.transfer_queue.cancel_transfer(tid)
        elif btn_id == "btn-retry":
            await self.transfer_queue.retry_transfer(tid)
        elif btn_id == "btn-skip":
            await self.transfer_queue.skip_transfer(tid)
        await self._refresh_queue()

    async def action_pause_selected(self) -> None:
        if self.selected_item and self.transfer_queue:
            await self.transfer_queue.pause_transfer(self.selected_item.transfer.id)
            await self._refresh_queue()

    async def action_resume_selected(self) -> None:
        if self.selected_item and self.transfer_queue:
            await self.transfer_queue.resume_transfer(self.selected_item.transfer.id)
            await self._refresh_queue()

    async def action_cancel_selected(self) -> None:
        if self.selected_item and self.transfer_queue:
            await self.transfer_queue.cancel_transfer(self.selected_item.transfer.id)
            await self._refresh_queue()

    async def action_retry_selected(self) -> None:
        if self.selected_item and self.transfer_queue:
            await self.transfer_queue.retry_transfer(self.selected_item.transfer.id)
            await self._refresh_queue()

    async def action_skip_selected(self) -> None:
        if self.selected_item and self.transfer_queue:
            await self.transfer_queue.skip_transfer(self.selected_item.transfer.id)
            await self._refresh_queue()

    async def action_add_transfer(self) -> None:
        pass
