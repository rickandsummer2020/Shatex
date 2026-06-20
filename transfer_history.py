"""Transfer History Screen for ShareX."""

import asyncio
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.reactive import reactive

from ...database.manager import get_database
from ...models.transfer import TransferStatus


class TransferHistoryScreen(Screen):
    """Screen for viewing transfer history."""

    DEFAULT_CSS = """
    TransferHistoryScreen {
        align: center middle;
    }

    TransferHistoryScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    TransferHistoryScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    TransferHistoryScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    TransferHistoryScreen ListView {
        height: 10;
        border: solid blue;
        background: #1a1a3e;
    }

    TransferHistoryScreen ListItem {
        height: 2;
        color: white;
    }

    TransferHistoryScreen ListItem:hover {
        background: #0f3460;
        color: ansi_bright_cyan;
    }

    TransferHistoryScreen Button {
        width: 100%;
        margin: 1 0;
    }
    """

    transfers: reactive[list] = reactive([])

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Transfer History", classes="title")
        yield Static("Recent file transfers", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        yield ListView(id="history_list")
        yield Button("Clear History", id="clear", variant="error")
        yield Button("Refresh", id="refresh", variant="primary")
        yield Button("Back", id="back")

        yield Static("0 transfers", id="count", classes="info-box")

    def on_mount(self) -> None:
        """Handle mount."""
        self._refresh_history()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "refresh":
            self._refresh_history()
        elif button_id == "clear":
            self._clear_history()

    def _refresh_history(self) -> None:
        """Refresh history list from database."""
        try:
            db = get_database()
            self.transfers = db.get_transfers(limit=50)
        except Exception as e:
            # Fallback to demo data
            self.transfers = []

        history_list = self.query_one("#history_list", ListView)
        history_list.clear()

        if self.transfers:
            for transfer in self.transfers:
                icon = "↑" if transfer.direction.value == "send" else "↓"
                status_color = "green" if transfer.status == TransferStatus.COMPLETED else "red"
                history_list.append(ListItem(Label(
                    f"{icon} {transfer.file_name} ({transfer.formatted_size}) - {transfer.status.value}"
                )))
        else:
            # Demo data if no real data
            demo_history = [
                ("document.pdf", "2.5 MB", "completed", "send"),
                ("image.jpg", "1.2 MB", "completed", "receive"),
                ("video.mp4", "45 MB", "failed", "send"),
            ]
            for name, size, status, direction in demo_history:
                icon = "↑" if direction == "send" else "↓"
                history_list.append(ListItem(Label(
                    f"{icon} {name} ({size}) - {status}"
                )))

        count = self.query_one("#count", Static)
        count.update(f"{len(self.transfers)} transfers")

    def _clear_history(self) -> None:
        """Clear transfer history."""
        try:
            db = get_database()
            db.clear_history()
        except Exception:
            pass

        self.transfers = []
        history_list = self.query_one("#history_list", ListView)
        history_list.clear()

        count = self.query_one("#count", Static)
        count.update("0 transfers")
