"""Receive Files Screen for ShareX."""

import asyncio
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Button, Label, ListView, ListItem
from textual.reactive import reactive

from ...config import get_config


class ReceiveFilesScreen(Screen):
    """Screen for receiving files from other devices."""

    DEFAULT_CSS = """
    ReceiveFilesScreen {
        align: center middle;
    }

    ReceiveFilesScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    ReceiveFilesScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    ReceiveFilesScreen .status-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    ReceiveFilesScreen .active {
        color: ansi_bright_green;
        border: solid green;
    }

    ReceiveFilesScreen .inactive {
        color: ansi_bright_red;
        border: solid red;
    }

    ReceiveFilesScreen .transfer-box {
        background: #1a1a3e;
        border: solid yellow;
        padding: 1;
        margin: 1 0;
        text-align: center;
        color: ansi_bright_white;
    }

    ReceiveFilesScreen ListView {
        height: 6;
        border: solid blue;
        background: #1a1a3e;
    }

    ReceiveFilesScreen Button {
        width: 100%;
        margin: 1 0;
    }
    """

    server_running: reactive[bool] = reactive(False)
    transfers: reactive[list] = reactive([])

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Receive Files", classes="title")
        yield Static("Accept incoming transfers", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        config = get_config()
        status = f"Active - Port {config.config.port}" if self.server_running else "Stopped"
        css_class = "active" if self.server_running else "inactive"
        yield Static(f"Server: {status}", id="server_status", classes=f"status-box {css_class}")

        yield Static("Incoming Transfers:", classes="subtitle")
        yield ListView(id="transfer_list")

        if self.server_running:
            yield Button("Stop Server", id="stop", variant="error")
        else:
            yield Button("Start Server", id="start", variant="success")

        yield Button("Back", id="back")

    def on_mount(self) -> None:
        """Check engine status on mount."""
        app = self.app
        if hasattr(app, "engine") and app.engine:
            self.server_running = app.engine.state.server_running
            self.refresh(recompose=True)

        # Start transfer update loop
        self.run_worker(self._update_loop(), exclusive=False)

    async def _update_loop(self) -> None:
        """Update transfer list periodically."""
        try:
            while self.is_active:
                await asyncio.sleep(1)
                if self.is_active:
                    self._refresh_transfers()
        except asyncio.CancelledError:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "start":
            self._start_server()
        elif button_id == "stop":
            self._stop_server()

    def _start_server(self) -> None:
        """Start receive server."""
        app = self.app
        if hasattr(app, "engine") and app.engine:
            if not app.engine.state.server_running:
                # Engine should have started it, but restart if needed
                asyncio.create_task(app.engine._start_server())
            self.server_running = True
        else:
            self.server_running = True  # Demo mode

        self.refresh(recompose=True)

    def _stop_server(self) -> None:
        """Stop receive server."""
        app = self.app
        if hasattr(app, "engine") and app.engine:
            if app.engine.server:
                asyncio.create_task(app.engine.server.stop())
            self.server_running = False
        else:
            self.server_running = False

        self.refresh(recompose=True)

    def _refresh_transfers(self) -> None:
        """Refresh incoming transfer list."""
        app = self.app
        if hasattr(app, "engine") and app.engine:
            transfers = app.engine.get_active_transfers()
            if transfers != self.transfers:
                self.transfers = transfers

                transfer_list = self.query_one("#transfer_list", ListView)
                transfer_list.clear()

                from ...models.transfer import TransferDirection
                receive_transfers = [t for t in transfers if t.direction == TransferDirection.RECEIVE]
                for transfer in receive_transfers:
                    transfer_list.append(ListItem(Label(
                        f"↓ {transfer.file_name} ({transfer.progress:.1f}%)"
                    )))

                if not receive_transfers:
                    transfer_list.append(ListItem(Label("No active transfers")))
