"""Transfer Progress Screen for ShareX."""

import asyncio
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Button, ProgressBar
from textual.reactive import reactive

from ...models.transfer import Transfer, TransferStatus


class TransferProgressScreen(Screen):
    """Screen showing active transfer progress.

    Displays animated progress bar, speed, ETA,
    and transfer details in real-time.
    """

    DEFAULT_CSS = """
    TransferProgressScreen {
        align: center middle;
    }

    TransferProgressScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    TransferProgressScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    TransferProgressScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    TransferProgressScreen .progress-box {
        background: #1a1a3e;
        border: solid ansi_bright_cyan;
        padding: 1;
        margin: 1 0;
    }

    TransferProgressScreen .stats {
        color: ansi_bright_white;
        text-align: center;
        padding: 1 0;
    }

    TransferProgressScreen Button {
        width: 100%;
        margin: 1 0;
    }
    """

    transfer: reactive[Transfer | None] = reactive(None)

    def __init__(self, transfer: Transfer) -> None:
        """Initialize with transfer object.

        Args:
            transfer: Transfer to display.
        """
        super().__init__()
        self.transfer = transfer
        self._update_task: asyncio.Task | None = None

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Transfer Progress", classes="title")
        yield Static("─" * 40, classes="subtitle")

        if self.transfer:
            yield Static(
                f"File: {self.transfer.file_name[:30]}",
                id="filename",
                classes="info-box",
            )
            yield Static(
                f"Size: {self.transfer.formatted_size}",
                id="filesize",
                classes="info-box",
            )
            yield Static(
                f"To: {self.transfer.device_name}",
                id="device",
                classes="info-box",
            )

            yield Static(
                f"Progress: {self.transfer.progress:.1f}%",
                id="progress_text",
                classes="progress-box",
            )

            yield Static(
                f"Speed: {self.transfer.formatted_speed} | ETA: {self.transfer.formatted_eta}",
                id="stats",
                classes="stats",
            )

        yield Button("Cancel", id="cancel", variant="error")
        yield Button("Back", id="back")

    def on_mount(self) -> None:
        """Start update loop."""
        self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        """Update display loop."""
        try:
            while self.is_active and self.transfer:
                if self.transfer.is_complete:
                    break

                self._update_display()
                await asyncio.sleep(0.5)

            # Final update
            self._update_display()

        except asyncio.CancelledError:
            pass

    def _update_display(self) -> None:
        """Update all display widgets."""
        if not self.transfer:
            return

        try:
            progress = self.query_one("#progress_text", Static)
            progress.update(f"Progress: {self.transfer.progress:.1f}%")

            stats = self.query_one("#stats", Static)
            stats.update(
                f"Speed: {self.transfer.formatted_speed} | "
                f"ETA: {self.transfer.formatted_eta}"
            )
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel":
            if self.transfer:
                self.transfer.cancel()
        elif event.button.id == "back":
            self.app.pop_screen()

    def on_unmount(self) -> None:
        """Cleanup."""
        if self._update_task:
            self._update_task.cancel()
