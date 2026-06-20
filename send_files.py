"""Send Files Screen for ShareX."""

import asyncio
from pathlib import Path
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Input, Label, ListView, ListItem
from textual.reactive import reactive

from ...config import get_config
from ...models.file_info import FileInfo
from ...models.device import Device
from ...utils.terminal import format_bytes


class SendFilesScreen(Screen):
    """Screen for sending files to other devices."""

    DEFAULT_CSS = """
    SendFilesScreen {
        align: center middle;
    }

    SendFilesScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    SendFilesScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    SendFilesScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
    }

    SendFilesScreen Input {
        margin: 1 0;
    }

    SendFilesScreen Button {
        width: 100%;
        margin: 1 0;
    }

    SendFilesScreen .file-info {
        color: ansi_bright_white;
        padding: 1 0;
    }

    SendFilesScreen .progress-box {
        background: #1a1a3e;
        border: solid green;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    SendFilesScreen ListView {
        height: 6;
        border: solid blue;
        background: #1a1a3e;
    }
    """

    selected_file: reactive[str] = reactive("")
    file_info: reactive[str] = reactive("No file selected")
    devices: reactive[list] = reactive([])
    sending: reactive[bool] = reactive(False)

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Send Files", classes="title")
        yield Static("Select file and device", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        yield Input(placeholder="Enter file path...", id="filepath")
        yield Button("Browse Downloads", id="browse")
        yield Static(self.file_info, id="file_info", classes="file-info")

        yield Static("Select Device:", classes="subtitle")
        yield ListView(id="device_list")

        if self.sending:
            yield Static("Sending...", id="progress", classes="progress-box")
        else:
            yield Button("Send File", id="send", variant="success")

        yield Button("Back", id="back")

    def on_mount(self) -> None:
        """Refresh device list on mount."""
        self._refresh_devices()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change."""
        path = event.value
        if path and Path(path).exists():
            try:
                info = FileInfo.from_path(path)
                self.file_info = f"{info.name} ({info.formatted_size})"
                self.selected_file = path
            except Exception:
                self.file_info = "Invalid file path"
                self.selected_file = ""
        else:
            self.file_info = "No file selected"
            self.selected_file = ""

        try:
            info_widget = self.query_one("#file_info", Static)
            info_widget.update(self.file_info)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "browse":
            self._browse_files()
        elif button_id == "send":
            self._send_file()

    def _browse_files(self) -> None:
        """Browse common directories."""
        config = get_config()
        download_path = Path(config.config.download_folder).expanduser()

        if download_path.exists():
            files = [f for f in download_path.iterdir() if f.is_file()][:10]
            file_list = "\n".join([f"  {f.name}" for f in files])
            info = self.query_one("#file_info", Static)
            info.update(f"Downloads folder:\n{file_list}")
        else:
            info = self.query_one("#file_info", Static)
            info.update("Downloads folder not found")

    def _refresh_devices(self) -> None:
        """Refresh available devices."""
        app = self.app
        if hasattr(app, "engine") and app.engine:
            self.devices = app.engine.get_devices()

        device_list = self.query_one("#device_list", ListView)
        device_list.clear()

        if self.devices:
            for device in self.devices:
                device_list.append(ListItem(Label(
                    f"● {device.display_name} ({device.ip_address})"
                )))
        else:
            device_list.append(ListItem(Label("No devices found - use Web Share")))

    def _send_file(self) -> None:
        """Send selected file."""
        if not self.selected_file:
            info = self.query_one("#file_info", Static)
            info.update("Error: No file selected!")
            return

        if not self.devices:
            info = self.query_one("#file_info", Static)
            info.update("Error: No devices found!")
            return

        # For demo, send to first device
        device = self.devices[0]
        info = self.query_one("#file_info", Static)
        info.update(f"Sending to {device.display_name}...")

        app = self.app
        if hasattr(app, "engine") and app.engine:
            self.sending = True
            self.refresh(recompose=True)

            async def do_send():
                try:
                    await app.engine.send_file(self.selected_file, device)
                except Exception as e:
                    info = self.query_one("#file_info", Static)
                    info.update(f"Error: {str(e)[:30]}")
                finally:
                    self.sending = False
                    self.refresh(recompose=True)

            asyncio.create_task(do_send())
        else:
            info.update("Engine not available (demo mode)")
