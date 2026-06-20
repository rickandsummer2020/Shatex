"""Modal dialogs for ShareX.

Popup dialogs for confirmations, inputs, and notifications.
"""

from typing import Optional, Callable

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Input, Label
from textual.reactive import reactive


class ConfirmDialog(ModalScreen[bool]):
    """Confirmation dialog modal.

    Asks user to confirm or cancel an action.
    """

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
        background: $surface 60%;
    }

    ConfirmDialog > Vertical {
        width: 38;
        height: auto;
        background: #1a1a3e;
        border: solid cyan;
        padding: 1;
    }

    ConfirmDialog .title {
        text-align: center;
        color: $text;
        text-style: bold;
        padding: 1 0;
    }

    ConfirmDialog .message {
        text-align: center;
        color: $text;
        padding: 1 0;
    }

    ConfirmDialog Button {
        width: 100%;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        title: str = "Confirm",
        message: str = "Are you sure?",
        confirm_text: str = "Yes",
        cancel_text: str = "No",
    ) -> None:
        """Initialize dialog.

        Args:
            title: Dialog title.
            message: Dialog message.
            confirm_text: Confirm button text.
            cancel_text: Cancel button text.
        """
        super().__init__()
        self.title = title
        self.message = message
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text

    def compose(self) -> None:
        """Compose dialog."""
        with Vertical():
            yield Static(self.title, classes="title")
            yield Static(self.message, classes="message")
            yield Button(self.confirm_text, variant="success", id="confirm")
            yield Button(self.cancel_text, variant="error", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)


class InputDialog(ModalScreen[str]):
    """Input dialog modal.

    Prompts user for text input.
    """

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
        background: $surface 60%;
    }

    InputDialog > Vertical {
        width: 38;
        height: auto;
        background: #1a1a3e;
        border: solid cyan;
        padding: 1;
    }

    InputDialog .title {
        text-align: center;
        color: $text;
        text-style: bold;
        padding: 1 0;
    }

    InputDialog Input {
        margin: 1 0;
    }

    InputDialog Button {
        width: 100%;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        title: str = "Input",
        placeholder: str = "Enter value...",
        default: str = "",
    ) -> None:
        """Initialize dialog.

        Args:
            title: Dialog title.
            placeholder: Input placeholder.
            default: Default value.
        """
        super().__init__()
        self.title = title
        self.placeholder = placeholder
        self.default = default

    def compose(self) -> None:
        """Compose dialog."""
        with Vertical():
            yield Static(self.title, classes="title")
            yield Input(placeholder=self.placeholder, value=self.default, id="input")
            yield Button("OK", variant="success", id="ok")
            yield Button("Cancel", variant="error", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "ok":
            value = self.query_one("#input", Input).value
            self.dismiss(value)
        else:
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        self.dismiss(event.value)


class InfoDialog(ModalScreen[None]):
    """Information dialog modal.

    Displays information message with OK button.
    """

    DEFAULT_CSS = """
    InfoDialog {
        align: center middle;
        background: $surface 60%;
    }

    InfoDialog > Vertical {
        width: 38;
        height: auto;
        background: #1a1a3e;
        border: solid cyan;
        padding: 1;
    }

    InfoDialog .title {
        text-align: center;
        color: $text;
        text-style: bold;
        padding: 1 0;
    }

    InfoDialog .message {
        text-align: center;
        color: $text;
        padding: 1 0;
    }

    InfoDialog Button {
        width: 100%;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        title: str = "Info",
        message: str = "",
    ) -> None:
        """Initialize dialog.

        Args:
            title: Dialog title.
            message: Dialog message.
        """
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> None:
        """Compose dialog."""
        with Vertical():
            yield Static(self.title, classes="title")
            yield Static(self.message, classes="message")
            yield Button("OK", variant="primary", id="ok")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()


class UploadApprovalDialog(ModalScreen[bool]):
    """Upload approval dialog.

    Shows upload request details for user approval.
    """

    DEFAULT_CSS = """
    UploadApprovalDialog {
        align: center middle;
        background: $surface 60%;
    }

    UploadApprovalDialog > Vertical {
        width: 40;
        height: auto;
        background: #1a1a3e;
        border: solid yellow;
        padding: 1;
    }

    UploadApprovalDialog .title {
        text-align: center;
        color: ansi_bright_yellow;
        text-style: bold;
        padding: 1 0;
    }

    UploadApprovalDialog .info {
        color: $text;
        padding: 0 1;
    }

    UploadApprovalDialog .label {
        color: ansi_bright_cyan;
    }

    UploadApprovalDialog Button {
        width: 100%;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        device_ip: str = "",
        filename: str = "",
        file_size: str = "",
    ) -> None:
        """Initialize dialog.

        Args:
            device_ip: Uploader IP address.
            filename: File name.
            file_size: Formatted file size.
        """
        super().__init__()
        self.device_ip = device_ip
        self.filename = filename
        self.file_size = file_size

    def compose(self) -> None:
        """Compose dialog."""
        with Vertical():
            yield Static("Incoming Upload", classes="title")
            yield Static(f"Device: {self.device_ip}", classes="info")
            yield Static(f"File: {self.filename}", classes="info")
            yield Static(f"Size: {self.file_size}", classes="info")
            yield Static("Accept this upload?", classes="title")
            yield Button("Accept", variant="success", id="accept")
            yield Button("Reject", variant="error", id="reject")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "accept":
            self.dismiss(True)
        else:
            self.dismiss(False)
