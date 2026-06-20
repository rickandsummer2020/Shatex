"""Main Menu Screen for ShareX."""

import asyncio
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button
from textual.reactive import reactive
from textual.worker import Worker, WorkerState

from ...config import get_config
from ...core.engine import ShareXEngine


class MainMenuScreen(Screen):
    """Main menu screen - entry point of application."""

    DEFAULT_CSS = """
    MainMenuScreen {
        align: center middle;
    }

    MainMenuScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    MainMenuScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    MainMenuScreen .divider {
        text-align: center;
        color: blue;
        padding: 0;
    }

    MainMenuScreen .status-bar {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
        color: ansi_bright_green;
    }

    MainMenuScreen .menu-grid {
        grid-size: 2;
        grid-gutter: 1;
        padding: 1 0;
    }

    MainMenuScreen Button {
        width: 100%;
        height: 3;
        content-align: center middle;
        background: #1a1a3e;
        color: white;
        border: solid blue;
    }

    MainMenuScreen Button:hover {
        background: #0f3460;
        color: ansi_bright_cyan;
    }

    MainMenuScreen Button:focus {
        background: ansi_bright_cyan;
        color: #0f0f23;
    }

    MainMenuScreen .footer {
        text-align: center;
        color: dimgrey;
        padding: 1 0;
    }
    """

    engine_started: reactive[bool] = reactive(False)

    def compose(self) -> None:
        """Compose main menu."""
        config = get_config()

        yield Static("ShareX", classes="title")
        yield Static(f"v1.0.0 - {config.config.device_name}", classes="subtitle")
        yield Static("─" * 40, classes="divider")

        status = "Engine Running" if self.engine_started else "Engine Stopped"
        yield Static(status, id="engine_status", classes="status-bar")

        with Horizontal(classes="menu-grid"):
            yield Button("Send", id="send", variant="primary")
            yield Button("Receive", id="receive")

        with Horizontal(classes="menu-grid"):
            yield Button("Devices", id="devices")
            yield Button("History", id="history")

        with Horizontal(classes="menu-grid"):
            yield Button("WebShare", id="webshare")
            yield Button("Settings", id="settings")

        with Horizontal(classes="menu-grid"):
            yield Button("About", id="about")
            yield Button("Exit", id="exit", variant="error")

        yield Static("S=Send R=Receive D=Devices H=History W=WebShare", classes="footer")

    def on_mount(self) -> None:
        """Start engine on mount."""
        self.run_worker(self._start_engine(), exclusive=True)

    async def _start_engine(self) -> None:
        """Start the ShareX engine."""
        try:
            app = self.app
            if hasattr(app, "engine") and app.engine:
                await app.engine.start()
                self.engine_started = True
                status = self.query_one("#engine_status", Static)
                if status:
                    status.update("Engine Running - Discovery Active")
        except Exception as e:
            status = self.query_one("#engine_status", Static)
            if status:
                status.update(f"Engine Error: {str(e)[:25]}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        screens = {
            "send": "send_files",
            "receive": "receive_files",
            "devices": "nearby_devices",
            "history": "transfer_history",
            "webshare": "web_share",
            "settings": "settings",
            "about": "about",
        }

        if button_id == "exit":
            self.app.exit()
        elif button_id in screens:
            self.app.push_screen(screens[button_id])
