# ShareX Feature Integration Guide

This guide documents how to integrate the three new features into the existing ShareX codebase.

## Files Overview

### NEW Files (8 files)
1. `sharex/services/transfer_queue.py` - Transfer Queue Service
2. `sharex/services/browser_push.py` - Browser Push Service
3. `sharex/services/resume_manager.py` - Resume Manager
4. `sharex/ui/screens/send_to_browser.py` - Send to Browser UI
5. `sharex/ui/screens/transfer_queue_screen.py` - Transfer Queue UI
6. `sharex/core/engine_integration.py` - Extended Engine
7. `sharex/database/queue_migrations.py` - DB Migrations
8. `sharex/ui/app_integration.py` - App Integration Reference

### MODIFIED Files (4 files - minimal changes)
1. `sharex/database/manager.py` - Add 6 methods
2. `sharex/services/webshare_server.py` - Add 2 methods to WebSocketManager
3. `sharex/ui/app.py` - Add bindings and screen imports
4. `sharex/core/engine.py` - No changes needed (ExtendedEngine wraps it)

---

## Step-by-Step Integration

### Step 1: Database (manager.py)

Add to imports:
```python
import json
```

Add these 6 methods to `DatabaseManager` class (copy from db_extensions.py).

### Step 2: WebSocket Manager (webshare_server.py)

Add these 2 methods to `WebSocketManager` class (copy from ws_manager_additions.py):
- `send_to_session()` - Send to specific browser
- `send_to_all_except()` - Broadcast except one

### Step 3: Engine (NO CHANGES to engine.py)

The `ExtendedEngine` in `engine_integration.py` inherits from `ShareXEngine`.
Replace the engine instantiation in `app.py`:

```python
# OLD:
from ..core.engine import ShareXEngine
self.engine = ShareXEngine(...)

# NEW:
from ..core.engine_integration import ExtendedEngine
self.engine = ExtendedEngine(...)
```

### Step 4: App (app.py)

Add imports:
```python
from ..ui.screens.send_to_browser import SendToBrowserScreen
from ..ui.screens.transfer_queue_screen import TransferQueueScreen
```

Add to BINDINGS:
```python
("b", "send_to_browser", "Send to Browser"),
("t", "transfer_queue", "Transfer Queue"),
```

Add action methods:
```python
def action_send_to_browser(self) -> None:
    self.push_screen(SendToBrowserScreen(webshare_manager=self.webshare_manager))

def action_transfer_queue(self) -> None:
    self.push_screen(TransferQueueScreen(transfer_queue=self.engine.transfer_queue))
```

### Step 5: WebShare Setup

In the WebShare screen setup, connect to engine:
```python
self.engine.set_webshare_manager(self.webshare_manager)
```

---

## Feature Usage

### Send to Browser
1. Start Web Share (W)
2. Open browser and connect to URL
3. Press B for Send to Browser
4. Select browser from list
5. Add files
6. Click Send → Browser auto-downloads

### Transfer Queue
1. Press T for Transfer Queue
2. Queue files from Send Files screen
3. Use P/R/C/X/K for Pause/Resume/Cancel/Retry/Skip
4. Watch concurrent transfers (max 3 default)

### Resume
- Automatic on network failure
- Manual via Retry (X) in queue
- Persistent across app restarts
- Handles WiFi disconnect, browser reconnect

---

## Architecture Diagram

```
ShareXApp (Extended)
├── ExtendedEngine
│   ├── ShareXEngine (existing - unchanged)
│   ├── TransferQueue (NEW)
│   │   └── TransferService (existing)
│   ├── BrowserPushService (NEW)
│   └── ResumeManager (NEW)
├── WebShareManager (existing)
│   └── WebShareServer (existing + 2 methods)
├── SendToBrowserScreen (NEW)
├── TransferQueueScreen (NEW)
└── Existing screens (unchanged)
```
