"""Settings Screen for ShareX."""

from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Input, Label, Select
from textual.reactive import reactive

from ...config import get_config


class SettingsScreen(Screen):
    """Screen for application settings."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }

    SettingsScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    SettingsScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    SettingsScreen .setting-row {
        height: auto;
        margin: 1 0;
    }

    SettingsScreen Label {
        color: ansi_bright_white;
        padding: 1 0 0 0;
    }

    SettingsScreen Input {
        margin: 0 0 1 0;
    }

    SettingsScreen Button {
        width: 100%;
        margin: 1 0;
    }

    SettingsScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
        color: ansi_bright_green;
    }
    """

    status_message: reactive[str] = reactive("")

    def compose(self) -> None:
        """Compose screen."""
        config = get_config()

        yield Static("Settings", classes="title")
        yield Static("Application configuration", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        yield Label("Device Name:")
        yield Input(value=config.config.device_name, id="device_name")

        yield Label("Download Folder:")
        yield Input(value=config.config.download_folder, id="download_folder")

        yield Label("Transfer Threads (1-16):")
        yield Input(value=str(config.config.transfer_threads), id="threads")

        yield Label("Chunk Size (4096-1048576):")
        yield Input(value=str(config.config.chunk_size), id="chunk_size")

        yield Static(self.status_message, id="status", classes="info-box")

        yield Button("Save", id="save", variant="success")
        yield Button("Reset to Defaults", id="reset", variant="error")
        yield Button("Back", id="back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "save":
            self._save_settings()
        elif button_id == "reset":
            self._reset_settings()

    def _save_settings(self) -> None:
        """Save settings."""
        config = get_config()

        try:
            device_name = self.query_one("#device_name", Input).value
            download_folder = self.query_one("#download_folder", Input).value
            threads = int(self.query_one("#threads", Input).value)
            chunk_size = int(self.query_one("#chunk_size", Input).value)

            # Validate
            if not device_name or len(device_name) > 32:
                self.status_message = "Error: Device name 1-32 chars"
                self.query_one("#status", Static).update(self.status_message)
                return

            if threads < 1 or threads > 16:
                self.status_message = "Error: Threads must be 1-16"
                self.query_one("#status", Static).update(self.status_message)
                return

            if chunk_size < 4096 or chunk_size > 1048576:
                self.status_message = "Error: Chunk size 4KB-1MB"
                self.query_one("#status", Static).update(self.status_message)
                return

            config.set("device_name", device_name)
            config.set("download_folder", download_folder)
            config.set("transfer_threads", threads)
            config.set("chunk_size", chunk_size)

            self.status_message = "Settings saved successfully!"
            self.query_one("#status", Static).update(self.status_message)

        except ValueError:
            self.status_message = "Error: Invalid number format"
            self.query_one("#status", Static).update(self.status_message)

    def _reset_settings(self) -> None:
        """Reset settings to defaults."""
        config = get_config()
        config.reset()

        # Refresh inputs
        self.query_one("#device_name", Input).value = config.config.device_name
        self.query_one("#download_folder", Input).value = config.config.download_folder
        self.query_one("#threads", Input).value = str(config.config.transfer_threads)
        self.query_one("#chunk_size", Input).value = str(config.config.chunk_size)

        self.status_message = "Settings reset to defaults"
        self.query_one("#status", Static).update(self.status_message)
