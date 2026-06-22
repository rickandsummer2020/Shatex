"""Web Share Server for ShareX.

Provides a lightweight HTTP server that allows any device
with a web browser to download and upload files without
installing ShareX.

ENHANCED: Full WebSocket support with heartbeat, reconnect,
browser session tracking, and real-time bidirectional communication.
"""

import os
import json
import time
import asyncio
import logging
import hashlib
import tempfile
import shutil
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

import aiohttp
from aiohttp import web
import aiofiles
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import SquareModuleDrawer

from ..models.webshare import WebShareSession, WebShareStatus
from ..models.file_info import FileInfo
from ..config import get_config

logger = logging.getLogger(__name__)


# =============================================================================
# BROWSER SESSION MANAGEMENT
# =============================================================================

class BrowserType(Enum):
    """Detected browser types."""
    CHROME = "chrome"
    FIREFOX = "firefox"
    SAFARI = "safari"
    EDGE = "edge"
    OPERA = "opera"
    SAMSUNG = "samsung"
    UNKNOWN = "unknown"


class PlatformType(Enum):
    """Detected platform types."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    ANDROID = "android"
    IOS = "ios"
    UNKNOWN = "unknown"


@dataclass
class BrowserSession:
    """Represents an active browser connection session.

    Tracks individual browser instances connected to the web share.
    """
    id: str
    ip_address: str
    user_agent: str
    browser_type: BrowserType = BrowserType.UNKNOWN
    platform_type: PlatformType = PlatformType.UNKNOWN
    browser_version: str = ""
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    is_active: bool = True
    is_websocket: bool = False  # NEW: Whether connected via WebSocket
    page_views: int = 0
    files_downloaded: int = 0
    files_uploaded: int = 0
    bytes_transferred: int = 0

    @property
    def duration(self) -> float:
        """Session duration in seconds."""
        return time.time() - self.connected_at

    @property
    def formatted_duration(self) -> str:
        """Human-readable session duration."""
        duration = int(self.duration)
        if duration < 60:
            return f"{duration}s"
        elif duration < 3600:
            return f"{duration // 60}m {duration % 60}s"
        else:
            return f"{duration // 3600}h {(duration % 3600) // 60}m"

    @property
    def display_name(self) -> str:
        """User-friendly browser display name."""
        browser_name = self.browser_type.value.title()
        platform_name = self.platform_type.value.title()
        return f"{browser_name} on {platform_name}"

    @property
    def heartbeat_ago(self) -> str:
        """Time since last heartbeat in human-readable format."""
        seconds = int(time.time() - self.last_heartbeat)
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        else:
            return f"{seconds // 3600}h ago"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent[:100] + "..." if len(self.user_agent) > 100 else self.user_agent,
            "browser_type": self.browser_type.value,
            "platform_type": self.platform_type.value,
            "browser_version": self.browser_version,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "last_heartbeat": self.last_heartbeat,
            "heartbeat_ago": self.heartbeat_ago,
            "is_active": self.is_active,
            "is_websocket": self.is_websocket,
            "page_views": self.page_views,
            "files_downloaded": self.files_downloaded,
            "files_uploaded": self.files_uploaded,
            "bytes_transferred": self.bytes_transferred,
            "duration": self.formatted_duration,
            "display_name": self.display_name,
        }


class BrowserDetector:
    """Detects browser type and platform from User-Agent string."""

    BROWSER_PATTERNS = {
        BrowserType.SAMSUNG: r"SamsungBrowser\/(\d+\.\d+)",
        BrowserType.OPERA: r"OPR\/(\d+\.\d+)",
        BrowserType.EDGE: r"Edg\/(\d+\.\d+)",
        BrowserType.CHROME: r"Chrome\/(\d+\.\d+)",
        BrowserType.FIREFOX: r"Firefox\/(\d+\.\d+)",
        BrowserType.SAFARI: r"Version\/(\d+\.\d+).*Safari",
    }

    PLATFORM_PATTERNS = {
        PlatformType.ANDROID: r"Android",
        PlatformType.IOS: r"(iPhone|iPad|iPod)",
        PlatformType.WINDOWS: r"Windows",
        PlatformType.MACOS: r"(Mac OS X|macOS)",
        PlatformType.LINUX: r"Linux",
    }

    @classmethod
    def detect(cls, user_agent: str) -> tuple[BrowserType, PlatformType, str]:
        """Detect browser type, platform, and version from User-Agent."""
        if not user_agent:
            return BrowserType.UNKNOWN, PlatformType.UNKNOWN, ""

        browser_type = BrowserType.UNKNOWN
        browser_version = ""
        for browser, pattern in cls.BROWSER_PATTERNS.items():
            match = re.search(pattern, user_agent)
            if match:
                browser_type = browser
                browser_version = match.group(1) if match.groups() else ""
                break

        platform_type = PlatformType.UNKNOWN
        for platform, pattern in cls.PLATFORM_PATTERNS.items():
            if re.search(pattern, user_agent):
                platform_type = platform
                break

        return browser_type, platform_type, browser_version


# =============================================================================
# WEBSOCKET MESSAGE PROTOCOL
# =============================================================================

@dataclass
class WSMessage:
    """WebSocket message protocol for real-time communication."""
    type: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "type": self.type,
            "timestamp": self.timestamp,
            "data": self.data,
        })

    @classmethod
    def from_json(cls, json_str: str) -> "WSMessage":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            type=data.get("type", "unknown"),
            timestamp=data.get("timestamp", time.time()),
            data=data.get("data", {}),
        )

    @classmethod
    def heartbeat(cls) -> "WSMessage":
        """Create server heartbeat message."""
        return cls(type="heartbeat", data={"server_time": time.time()})

    @classmethod
    def heartbeat_ack(cls) -> "WSMessage":
        """Create client heartbeat acknowledgment."""
        return cls(type="heartbeat_ack")

    @classmethod
    def browser_update(cls, sessions: List[BrowserSession]) -> "WSMessage":
        """Create browser update message."""
        return cls(
            type="browser_update",
            data={
                "count": len(sessions),
                "browsers": [s.to_dict() for s in sessions],
            }
        )

    @classmethod
    def file_update(cls, files: List[Dict], uploaded_files: List[Dict]) -> "WSMessage":
        """Create file list update message."""
        return cls(
            type="file_update",
            data={
                "files_count": len(files),
                "uploaded_count": len(uploaded_files),
                "files": files,
                "uploaded_files": uploaded_files,
            }
        )

    @classmethod
    def status_update(cls, status: str, url: str) -> "WSMessage":
        """Create server status update message."""
        return cls(
            type="status_update",
            data={
                "status": status,
                "url": url,
                "timestamp": time.time(),
            }
        )

    @classmethod
    def upload_progress(cls, upload_id: str, progress: float, status: str) -> "WSMessage":
        """Create upload progress message."""
        return cls(
            type="upload_progress",
            data={
                "upload_id": upload_id,
                "progress": progress,
                "status": status,
            }
        )

    @classmethod
    def error(cls, message: str) -> "WSMessage":
        """Create error message."""
        return cls(type="error", data={"message": message})


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================

@dataclass
class WSConnection:
    """Represents an active WebSocket connection."""
    ws: web.WebSocketResponse
    browser_session_id: str
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    is_alive: bool = True

    @property
    def latency(self) -> float:
        """Connection latency in seconds."""
        return time.time() - self.last_heartbeat


class WebSocketManager:
    """Manages all WebSocket connections.

    Handles connection lifecycle, heartbeat monitoring,
    broadcast distribution, and timeout detection.
    """

    HEARTBEAT_INTERVAL: float = 30.0  # Server sends heartbeat every 30s
    HEARTBEAT_TIMEOUT: float = 60.0   # Client must respond within 60s
    RECONNECT_GRACE: float = 5.0      # Grace period for reconnect with same session

    def __init__(self) -> None:
        """Initialize WebSocket manager."""
        self._connections: Dict[str, WSConnection] = {}  # session_id -> WSConnection
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start heartbeat monitoring loop."""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocket manager started")

    async def stop(self) -> None:
        """Stop all connections and monitoring."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Close all connections gracefully
        async with self._lock:
            for conn in list(self._connections.values()):
                conn.is_alive = False
                try:
                    await conn.ws.close(code=1001, message=b"Server shutting down")
                except Exception:
                    pass
            self._connections.clear()

        logger.info("WebSocket manager stopped")

    async def add_connection(
        self,
        ws: web.WebSocketResponse,
        browser_session_id: str,
    ) -> None:
        """Add a new WebSocket connection.

        Args:
            ws: WebSocket response object.
            browser_session_id: Associated browser session ID.
        """
        async with self._lock:
            # Close existing connection for same session (reconnect scenario)
            if browser_session_id in self._connections:
                old_conn = self._connections[browser_session_id]
                old_conn.is_alive = False
                try:
                    await old_conn.ws.close(code=1000, message=b"Replaced by new connection")
                except Exception:
                    pass
                del self._connections[browser_session_id]
                logger.info(f"Replaced existing WebSocket for session {browser_session_id[:8]}")

            conn = WSConnection(
                ws=ws,
                browser_session_id=browser_session_id,
            )
            self._connections[browser_session_id] = conn
            logger.info(f"WebSocket connected: {browser_session_id[:8]}")

    async def remove_connection(self, browser_session_id: str) -> None:
        """Remove a WebSocket connection.

        Args:
            browser_session_id: Browser session ID to remove.
        """
        async with self._lock:
            if browser_session_id in self._connections:
                conn = self._connections[browser_session_id]
                conn.is_alive = False
                del self._connections[browser_session_id]
                logger.info(f"WebSocket disconnected: {browser_session_id[:8]}")

    async def update_heartbeat(self, browser_session_id: str) -> None:
        """Update heartbeat timestamp for a connection.

        Args:
            browser_session_id: Browser session ID.
        """
        async with self._lock:
            if browser_session_id in self._connections:
                self._connections[browser_session_id].last_heartbeat = time.time()

    def get_connection_count(self) -> int:
        """Get number of active WebSocket connections.

        Returns:
            Active connection count.
        """
        return len([c for c in self._connections.values() if c.is_alive])

    async def broadcast(self, message: WSMessage) -> int:
        """Broadcast message to all connected clients.

        Args:
            message: Message to broadcast.

        Returns:
            Number of clients that received the message.
        """
        sent_count = 0
        dead_connections = []

        async with self._lock:
            connections = list(self._connections.items())

        for session_id, conn in connections:
            if not conn.is_alive or conn.ws.closed:
                dead_connections.append(session_id)
                continue

            try:
                await conn.ws.send_str(message.to_json())
                sent_count += 1
            except Exception as e:
                logger.debug(f"Failed to send to {session_id[:8]}: {e}")
                dead_connections.append(session_id)

        # Clean up dead connections
        for session_id in dead_connections:
            await self.remove_connection(session_id)

        return sent_count

    async def send_to(self, browser_session_id: str, message: WSMessage) -> bool:
        """Send message to specific client.

        Args:
            browser_session_id: Target browser session ID.
            message: Message to send.

        Returns:
            True if sent successfully.
        """
        async with self._lock:
            conn = self._connections.get(browser_session_id)
            if not conn or not conn.is_alive or conn.ws.closed:
                return False

        try:
            await conn.ws.send_str(message.to_json())
            return True
        except Exception as e:
            logger.debug(f"Failed to send to {browser_session_id[:8]}: {e}")
            await self.remove_connection(browser_session_id)
            return False

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat and timeout detection loop."""
        try:
            while self._running:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                current_time = time.time()
                dead_connections = []

                async with self._lock:
                    connections = list(self._connections.items())

                for session_id, conn in connections:
                    if not conn.is_alive:
                        dead_connections.append(session_id)
                        continue

                    # Check for timeout
                    if current_time - conn.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                        logger.warning(f"WebSocket timeout: {session_id[:8]}")
                        dead_connections.append(session_id)
                        continue

                    # Send heartbeat ping
                    try:
                        heartbeat_msg = WSMessage.heartbeat()
                        await conn.ws.send_str(heartbeat_msg.to_json())
                    except Exception as e:
                        logger.debug(f"Heartbeat failed for {session_id[:8]}: {e}")
                        dead_connections.append(session_id)

                # Clean up dead connections
                for session_id in dead_connections:
                    await self.remove_connection(session_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")


# =============================================================================
# HTML TEMPLATE WITH WEBSOCKET CLIENT
# =============================================================================

WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ShareX Web Share</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23;
            color: #eaeaea;
            min-height: 100vh;
            padding: 16px;
        }
        .header {
            text-align: center;
            padding: 20px 0;
            border-bottom: 2px solid #1a1a3e;
            margin-bottom: 20px;
        }
        .header h1 {
            font-size: 1.5rem;
            color: #00d9ff;
            margin-bottom: 8px;
        }
        .device-info {
            font-size: 0.85rem;
            color: #a0a0a0;
        }
        .ws-status {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        .ws-connected { background: #00ff88; }
        .ws-connecting { background: #ff9f1c; animation: pulse 1s infinite; }
        .ws-disconnected { background: #e94560; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .section {
            background: #1a1a3e;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #0f3460;
        }
        .section-title {
            font-size: 1rem;
            color: #00d9ff;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .file-list { list-style: none; }
        .file-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px;
            background: #0f0f23;
            border-radius: 8px;
            margin-bottom: 8px;
            border: 1px solid #0f3460;
        }
        .file-info { flex: 1; min-width: 0; }
        .file-name {
            font-size: 0.9rem;
            color: #eaeaea;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 4px;
        }
        .file-size { font-size: 0.75rem; color: #a0a0a0; }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            gap: 6px;
        }
        .btn-primary { background: #00d9ff; color: #0f0f23; }
        .btn-primary:hover { background: #33e0ff; }
        .btn-success { background: #00ff88; color: #0f0f23; }
        .btn-success:hover { background: #33ffaa; }
        .btn-danger { background: #e94560; color: #fff; }
        .btn-danger:hover { background: #ff6b81; }
        .btn-sm { padding: 6px 12px; font-size: 0.8rem; }
        .upload-area {
            border: 2px dashed #0f3460;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            transition: all 0.3s;
            cursor: pointer;
        }
        .upload-area:hover, .upload-area.dragover {
            border-color: #00d9ff;
            background: rgba(0, 217, 255, 0.05);
        }
        .upload-icon { font-size: 2.5rem; margin-bottom: 12px; }
        .upload-text { font-size: 1rem; color: #eaeaea; margin-bottom: 8px; }
        .upload-hint { font-size: 0.8rem; color: #a0a0a0; }
        #file-input { display: none; }
        .progress-container { display: none; margin-top: 16px; }
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #0f0f23;
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 8px;
        }
        .progress-fill {
            height: 100%;
            background: #00d9ff;
            border-radius: 4px;
            transition: width 0.3s;
            width: 0%;
        }
        .progress-text { font-size: 0.8rem; color: #a0a0a0; text-align: center; }
        .file-preview {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: #0f0f23;
            border-radius: 6px;
            margin-bottom: 8px;
            font-size: 0.85rem;
        }
        .file-preview-name { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .file-preview-size { color: #a0a0a0; font-size: 0.75rem; }
        .empty-state { text-align: center; padding: 40px 20px; color: #a0a0a0; }
        .empty-state-icon { font-size: 3rem; margin-bottom: 16px; opacity: 0.5; }
        .status-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .status-active { background: rgba(0, 255, 136, 0.2); color: #00ff88; }
        .footer { text-align: center; padding: 20px; font-size: 0.75rem; color: #666; }
        .toast {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #1a1a3e;
            color: #eaeaea;
            padding: 12px 24px;
            border-radius: 8px;
            border: 1px solid #0f3460;
            font-size: 0.9rem;
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
        }
        .toast.show { opacity: 1; }
        @media (max-width: 400px) {
            body { padding: 12px; }
            .header h1 { font-size: 1.2rem; }
            .file-item { flex-direction: column; align-items: flex-start; gap: 8px; }
            .btn { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>ShareX Web Share</h1>
        <div class="device-info">
            <span class="status-badge status-active">Online</span>
            <span id="device-name">{{device_name}}</span>
            <span id="ws-indicator" style="margin-left: 10px;">
                <span class="ws-status ws-connecting" id="ws-dot"></span>
                <span id="ws-text" style="font-size: 0.75rem; color: #a0a0a0;">Connecting...</span>
            </span>
        </div>
    </div>

    <div class="section">
        <div class="section-title">
            <span>Files</span>
            <span id="file-count">({{file_count}})</span>
        </div>
        <ul class="file-list" id="file-list">
            {{file_list}}
        </ul>
        <div class="empty-state" id="empty-files" style="display: {{empty_display}};">
            <div class="empty-state-icon">No files shared</div>
            <p>No files available for download</p>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Upload Files</div>
        <div class="upload-area" id="upload-area">
            <div class="upload-icon">Click or drop files here</div>
            <div class="upload-text">Select files to upload</div>
            <div class="upload-hint">Supports multiple files and folders</div>
        </div>
        <input type="file" id="file-input" multiple>
        <div id="file-previews"></div>
        <div class="progress-container" id="progress-container">
            <div class="progress-bar">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
            <div class="progress-text" id="progress-text">0%</div>
        </div>
        <button class="btn btn-success" id="upload-btn" style="display: none; width: 100%; margin-top: 12px;">
            Upload Files
        </button>
    </div>

    <div class="footer">
        <p>ShareX Web Share - Local Network Only</p>
        <p id="connection-info">{{connection_info}}</p>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        const deviceName = "{{device_name}}";
        const sessionId = "{{session_id}}";
        let selectedFiles = [];
        let uploadCancelled = false;

        // WebSocket Manager
        class WSManager {
            constructor() {
                this.ws = null;
                this.reconnectAttempts = 0;
                this.maxReconnectDelay = 30000;
                this.reconnectTimer = null;
                this.heartbeatTimer = null;
                this.url = `ws://${window.location.host}/ws`;
                this.connected = false;
            }

            connect() {
                if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
                    return;
                }

                this.updateStatus('connecting', 'Connecting...');

                try {
                    this.ws = new WebSocket(this.url);

                    this.ws.onopen = () => {
                        console.log('WebSocket connected');
                        this.connected = true;
                        this.reconnectAttempts = 0;
                        this.updateStatus('connected', 'Live');
                        this.startHeartbeat();
                    };

                    this.ws.onmessage = (event) => {
                        try {
                            const msg = JSON.parse(event.data);
                            this.handleMessage(msg);
                        } catch (e) {
                            console.error('Invalid message:', event.data);
                        }
                    };

                    this.ws.onclose = (event) => {
                        console.log('WebSocket closed:', event.code, event.reason);
                        this.connected = false;
                        this.stopHeartbeat();
                        this.updateStatus('disconnected', 'Disconnected');
                        if (!event.wasClean) {
                            this.scheduleReconnect();
                        }
                    };

                    this.ws.onerror = (error) => {
                        console.error('WebSocket error:', error);
                        this.updateStatus('disconnected', 'Error');
                    };

                } catch (e) {
                    console.error('Failed to create WebSocket:', e);
                    this.scheduleReconnect();
                }
            }

            disconnect() {
                if (this.reconnectTimer) {
                    clearTimeout(this.reconnectTimer);
                    this.reconnectTimer = null;
                }
                this.stopHeartbeat();
                if (this.ws) {
                    this.ws.onclose = null; // Prevent reconnect
                    this.ws.close(1000, 'Client disconnect');
                    this.ws = null;
                }
                this.connected = false;
            }

            scheduleReconnect() {
                const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
                this.reconnectAttempts++;
                console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
                this.updateStatus('connecting', 'Reconnecting...');

                this.reconnectTimer = setTimeout(() => {
                    this.connect();
                }, delay);
            }

            startHeartbeat() {
                // Respond to server heartbeats
                this.heartbeatTimer = setInterval(() => {
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.send({type: 'heartbeat_ack'});
                    }
                }, 25000); // Send ack every 25s to stay alive
            }

            stopHeartbeat() {
                if (this.heartbeatTimer) {
                    clearInterval(this.heartbeatTimer);
                    this.heartbeatTimer = null;
                }
            }

            send(data) {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify(data));
                    return true;
                }
                return false;
            }

            handleMessage(msg) {
                switch (msg.type) {
                    case 'heartbeat':
                        // Server heartbeat - respond immediately
                        this.send({type: 'heartbeat_ack'});
                        break;
                    case 'status_update':
                        console.log('Status:', msg.data.status);
                        break;
                    case 'file_update':
                        console.log('Files updated:', msg.data.files_count);
                        break;
                    case 'browser_update':
                        console.log('Browsers:', msg.data.count);
                        break;
                    case 'upload_progress':
                        console.log('Upload progress:', msg.data.progress);
                        break;
                    case 'error':
                        console.error('Server error:', msg.data.message);
                        showToast('Error: ' + msg.data.message);
                        break;
                    default:
                        console.log('Unknown message type:', msg.type);
                }
            }

            updateStatus(state, text) {
                const dot = document.getElementById('ws-dot');
                const txt = document.getElementById('ws-text');
                if (dot && txt) {
                    dot.className = 'ws-status ws-' + state;
                    txt.textContent = text;
                }
            }
        }

        const wsManager = new WSManager();
        wsManager.connect();

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            wsManager.disconnect();
        });

        function showToast(message) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }

        const uploadArea = document.getElementById('upload-area');
        const fileInput = document.getElementById('file-input');
        const filePreviews = document.getElementById('file-previews');
        const uploadBtn = document.getElementById('upload-btn');
        const progressContainer = document.getElementById('progress-container');
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');

        uploadArea.addEventListener('click', () => fileInput.click());

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const items = e.dataTransfer.items;
            if (items) {
                const files = [];
                for (let i = 0; i < items.length; i++) {
                    const item = items[i].webkitGetAsEntry();
                    if (item) traverseFileTree(item, files);
                }
                setTimeout(() => { selectedFiles = files; updateFilePreviews(); }, 100);
            } else {
                selectedFiles = Array.from(e.dataTransfer.files);
                updateFilePreviews();
            }
        });

        function traverseFileTree(item, files) {
            if (item.isFile) {
                item.file(file => files.push(file));
            } else if (item.isDirectory) {
                const dirReader = item.createReader();
                dirReader.readEntries(entries => {
                    for (let i = 0; i < entries.length; i++) {
                        traverseFileTree(entries[i], files);
                    }
                });
            }
        }

        fileInput.addEventListener('change', (e) => {
            selectedFiles = Array.from(e.target.files);
            updateFilePreviews();
        });

        function formatSize(bytes) {
            for (const unit of ['B', 'KB', 'MB', 'GB']) {
                if (bytes < 1024) return bytes.toFixed(1) + ' ' + unit;
                bytes /= 1024;
            }
            return bytes.toFixed(1) + ' TB';
        }

        function updateFilePreviews() {
            filePreviews.innerHTML = '';
            if (selectedFiles.length === 0) {
                uploadBtn.style.display = 'none';
                return;
            }
            selectedFiles.forEach(file => {
                const div = document.createElement('div');
                div.className = 'file-preview';
                div.innerHTML = `<span class="file-preview-name">${file.name}</span><span class="file-preview-size">${formatSize(file.size)}</span>`;
                filePreviews.appendChild(div);
            });
            uploadBtn.style.display = 'block';
        }

        uploadBtn.addEventListener('click', async () => {
            if (selectedFiles.length === 0) return;
            uploadCancelled = false;
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
            progressContainer.style.display = 'block';

            const totalSize = selectedFiles.reduce((sum, f) => sum + f.size, 0);
            let uploadedSize = 0;

            for (let i = 0; i < selectedFiles.length; i++) {
                if (uploadCancelled) break;
                const file = selectedFiles[i];
                const formData = new FormData();
                formData.append('file', file);
                formData.append('filename', file.name);
                formData.append('session_id', sessionId);

                try {
                    const xhr = new XMLHttpRequest();
                    xhr.upload.addEventListener('progress', (e) => {
                        if (e.lengthComputable) {
                            const fileProgress = e.loaded / e.total;
                            const currentUploaded = uploadedSize + (file.size * fileProgress);
                            const percent = (currentUploaded / totalSize) * 100;
                            progressFill.style.width = percent + '%';
                            progressText.textContent = Math.round(percent) + '%';
                        }
                    });

                    await new Promise((resolve, reject) => {
                        xhr.addEventListener('load', () => {
                            if (xhr.status === 200) {
                                uploadedSize += file.size;
                                resolve();
                            } else if (xhr.status === 202) {
                                showToast('Upload pending approval...');
                                setTimeout(resolve, 2000);
                            } else {
                                reject(new Error(xhr.responseText || 'Upload failed'));
                            }
                        });
                        xhr.addEventListener('error', () => reject(new Error('Network error')));
                        xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));
                        xhr.open('POST', '/upload');
                        xhr.send(formData);
                    });
                } catch (error) {
                    showToast('Error: ' + error.message);
                    break;
                }
            }

            progressFill.style.width = '100%';
            progressText.textContent = 'Complete!';
            showToast('Upload complete!');
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload Files';
            selectedFiles = [];
            updateFilePreviews();
            setTimeout(() => { progressContainer.style.display = 'none'; progressFill.style.width = '0%'; }, 2000);
        });

        function cancelUpload() {
            uploadCancelled = true;
            showToast('Upload cancelled');
        }
    </script>
</body>
</html>"""


@dataclass
class UploadRequest:
    """Represents a pending upload request awaiting approval."""
    id: str
    filename: str
    file_size: int
    client_ip: str
    temp_path: str
    session_id: str
    timestamp: float = field(default_factory=time.time)
    approved: Optional[bool] = None
    approved_by: Optional[str] = None
    approval_time: Optional[float] = None


class WebShareServer:
    """HTTP server for browser-based file sharing.

    Allows any device with a web browser to download and
    upload files without installing ShareX.

    ENHANCED: Full WebSocket support with real-time updates,
    heartbeat monitoring, automatic reconnect, and timeout detection.

    Attributes:
        session: Current web share session.
        on_upload_request: Callback for upload approval.
        on_status_change: Callback for status changes.
        on_browser_update: Callback for browser session changes.
        _app: aiohttp application instance.
        _runner: aiohttp server runner.
        _site: aiohttp server site.
        _ws_manager: WebSocket connection manager.
        _browser_sessions: Active browser connections.
    """

    def __init__(
        self,
        session: WebShareSession,
        on_upload_request: Optional[Callable[[UploadRequest], asyncio.Future]] = None,
        on_status_change: Optional[Callable[[WebShareStatus], None]] = None,
        on_browser_update: Optional[Callable[[List[BrowserSession]], None]] = None,
    ) -> None:
        """Initialize web share server.

        Args:
            session: Web share session configuration.
            on_upload_request: Callback triggered when upload needs approval.
            on_status_change: Callback triggered on status changes.
            on_browser_update: Callback triggered when browser sessions change.
        """
        self.session = session
        self.on_upload_request = on_upload_request
        self.on_status_change = on_status_change
        self.on_browser_update = on_browser_update
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._pending_uploads: Dict[str, UploadRequest] = {}
        self._upload_futures: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

        # WebSocket manager
        self._ws_manager = WebSocketManager()

        # Browser session management
        self._browser_sessions: Dict[str, BrowserSession] = {}
        self._browser_cleanup_task: Optional[asyncio.Task] = None
        self._browser_lock = asyncio.Lock()
        self._browser_session_timeout: float = 300.0  # 5 minutes

        logger.info(f"WebShareServer initialized for session {session.id}")

    # =====================================================================
    # BROWSER SESSION MANAGEMENT
    # =====================================================================

    def _get_or_create_browser_session(self, request: web.Request) -> BrowserSession:
        """Get existing or create new browser session for a request."""
        client_ip = request.remote or "unknown"
        user_agent = request.headers.get("User-Agent", "")

        session_key = hashlib.sha256(
            f"{client_ip}:{user_agent}".encode()
        ).hexdigest()[:16]

        existing = self._browser_sessions.get(session_key)
        if existing and existing.is_active:
            existing.last_activity = time.time()
            existing.page_views += 1
            return existing

        browser_type, platform_type, version = BrowserDetector.detect(user_agent)

        new_session = BrowserSession(
            id=session_key,
            ip_address=client_ip,
            user_agent=user_agent,
            browser_type=browser_type,
            platform_type=platform_type,
            browser_version=version,
            page_views=1,
        )

        self._browser_sessions[session_key] = new_session
        logger.info(f"New browser session: {new_session.display_name} from {client_ip}")

        self._notify_browser_update()
        return new_session

    def get_active_browser_sessions(self) -> List[BrowserSession]:
        """Get list of currently active browser sessions."""
        current_time = time.time()
        active = []
        for session in self._browser_sessions.values():
            if session.is_active and (current_time - session.last_activity) < self._browser_session_timeout:
                active.append(session)
        return active

    def get_browser_session_count(self) -> int:
        """Get count of active browser sessions."""
        return len(self.get_active_browser_sessions())

    def _update_browser_activity(self, session_id: str, bytes_count: int = 0,
                                  download: bool = False, upload: bool = False) -> None:
        """Update browser session activity metrics."""
        session = self._browser_sessions.get(session_id)
        if session:
            session.last_activity = time.time()
            session.bytes_transferred += bytes_count
            if download:
                session.files_downloaded += 1
            if upload:
                session.files_uploaded += 1
            self._notify_browser_update()

    def _notify_browser_update(self) -> None:
        """Notify UI about browser changes via callback and WebSocket."""
        sessions = self.get_active_browser_sessions()

        # Callback notification
        if self.on_browser_update:
            try:
                self.on_browser_update(sessions)
            except Exception as e:
                logger.error(f"Browser update callback error: {e}")

        # WebSocket broadcast
        asyncio.create_task(
            self._ws_manager.broadcast(WSMessage.browser_update(sessions))
        )

    async def _browser_cleanup_loop(self) -> None:
        """Periodic cleanup of stale browser sessions."""
        try:
            while self.session.status == WebShareStatus.ACTIVE:
                await asyncio.sleep(30)

                current_time = time.time()
                stale_sessions = []

                for session_id, session in self._browser_sessions.items():
                    if current_time - session.last_activity > self._browser_session_timeout:
                        session.is_active = False
                        stale_sessions.append(session_id)
                        logger.info(f"Browser session expired: {session.display_name}")

                if stale_sessions:
                    for session_id in stale_sessions:
                        self._browser_sessions.pop(session_id, None)
                    self._notify_browser_update()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Browser cleanup error: {e}")

    # =====================================================================
    # WEBSOCKET HANDLERS
    # =====================================================================

    def _setup_websocket_routes(self) -> None:
        """Setup WebSocket routes."""
        if not self._app:
            return

        self._app.router.add_get("/ws", self._handle_websocket)
        logger.info("WebSocket endpoint registered at /ws")

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection with full lifecycle management.

        Supports: connect, disconnect, heartbeat, reconnect, timeout detection.
        """
        ws = web.WebSocketResponse(
            heartbeat=30.0,
            autoping=True,
        )
        await ws.prepare(request)

        # Get or create browser session
        browser_session = self._get_or_create_browser_session(request)
        browser_session.is_websocket = True
        browser_session.last_heartbeat = time.time()

        # Register with WebSocket manager
        await self._ws_manager.add_connection(ws, browser_session.id)

        logger.info(f"WebSocket connected: {browser_session.display_name} ({browser_session.ip_address})")

        # Send initial status
        try:
            await ws.send_str(WSMessage.status_update(
                self.session.status.value,
                self.session.url
            ).to_json())

            # Send current file list
            await ws.send_str(WSMessage.file_update(
                self.session.files,
                self.session.uploaded_files
            ).to_json())

            # Send current browser list
            await ws.send_str(WSMessage.browser_update(
                self.get_active_browser_sessions()
            ).to_json())
        except Exception as e:
            logger.error(f"WebSocket initial send failed: {e}")
            await self._ws_manager.remove_connection(browser_session.id)
            return ws

        # Message loop
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        msg_type = data.get("type", "")

                        if msg_type == "heartbeat_ack":
                            # Client acknowledged heartbeat
                            await self._ws_manager.update_heartbeat(browser_session.id)
                            browser_session.last_heartbeat = time.time()
                        elif msg_type == "ping":
                            # Client ping
                            await ws.send_str(WSMessage(type="pong").to_json())
                        else:
                            logger.debug(f"WebSocket message from {browser_session.id[:8]}: {msg_type}")

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from {browser_session.id[:8]}: {msg.data[:100]}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break

                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    logger.info(f"WebSocket closed by client: {browser_session.id[:8]}")
                    break

        except Exception as e:
            logger.error(f"WebSocket handler error for {browser_session.id[:8]}: {e}")

        finally:
            # Cleanup
            await self._ws_manager.remove_connection(browser_session.id)
            browser_session.is_websocket = False
            self._notify_browser_update()
            logger.info(f"WebSocket disconnected: {browser_session.display_name}")

        return ws

    async def _broadcast_browser_update(self) -> None:
        """Broadcast browser update to all WebSocket clients."""
        sessions = self.get_active_browser_sessions()
        await self._ws_manager.broadcast(WSMessage.browser_update(sessions))

    async def _broadcast_file_update(self) -> None:
        """Broadcast file update to all WebSocket clients."""
        await self._ws_manager.broadcast(WSMessage.file_update(
            self.session.files,
            self.session.uploaded_files
        ))

    async def _broadcast_status_update(self) -> None:
        """Broadcast status update to all WebSocket clients."""
        await self._ws_manager.broadcast(WSMessage.status_update(
            self.session.status.value,
            self.session.url
        ))

    # =====================================================================
    # LIFECYCLE
    # =====================================================================

    async def start(self) -> None:
        """Start the HTTP server with WebSocket support."""
        try:
            self.session.status = WebShareStatus.STARTING
            self._notify_status_change()

            self._app = web.Application()
            self._setup_routes()
            self._setup_websocket_routes()

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()

            self._site = web.TCPSite(
                self._runner,
                self.session.ip_address,
                self.session.port,
            )
            await self._site.start()

            # Start managers
            await self._ws_manager.start()
            self._browser_cleanup_task = asyncio.create_task(
                self._browser_cleanup_loop()
            )

            self.session.status = WebShareStatus.ACTIVE
            self._notify_status_change()
            logger.info(f"Web share server started at {self.session.url}")

        except Exception as e:
            self.session.status = WebShareStatus.ERROR
            self._notify_status_change()
            logger.error(f"Failed to start web share server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the HTTP server and WebSocket connections."""
        try:
            self.session.status = WebShareStatus.STOPPING
            self._notify_status_change()

            # Stop WebSocket manager first (notifies clients)
            await self._ws_manager.stop()

            # Cancel browser cleanup
            if self._browser_cleanup_task:
                self._browser_cleanup_task.cancel()
                try:
                    await self._browser_cleanup_task
                except asyncio.CancelledError:
                    pass
                self._browser_cleanup_task = None

            if self._site:
                await self._site.stop()
            if self._runner:
                await self._runner.cleanup()

            self.session.status = WebShareStatus.STOPPED
            self._notify_status_change()
            logger.info("Web share server stopped")

        except Exception as e:
            logger.error(f"Error stopping web share server: {e}")
            self.session.status = WebShareStatus.ERROR
            self._notify_status_change()

    def _setup_routes(self) -> None:
        """Configure HTTP routes (HTTP remains fully functional)."""
        if not self._app:
            return

        # Core HTTP routes (unchanged)
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/download/{filename}", self._handle_download)
        self._app.router.add_post("/upload", self._handle_upload)
        self._app.router.add_get("/api/files", self._handle_api_files)
        self._app.router.add_get("/api/status", self._handle_api_status)
        self._app.router.add_get("/api/browsers", self._handle_api_browsers)
        self._app.router.add_get("/api/browsers/count", self._handle_api_browser_count)

        # Static files
        config = get_config()
        download_path = Path(config.config.download_folder)
        if download_path.exists():
            self._app.router.add_static("/downloads", path=str(download_path), name="downloads")

    def _notify_status_change(self) -> None:
        """Notify status change via callback and WebSocket."""
        if self.on_status_change:
            try:
                self.on_status_change(self.session.status)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

        # Broadcast to WebSocket clients
        if self.session.status in (WebShareStatus.ACTIVE, WebShareStatus.STOPPING, WebShareStatus.STOPPED):
            asyncio.create_task(self._broadcast_status_update())

    # =====================================================================
    # HTTP HANDLERS (UNCHANGED - Downloads work via HTTP)
    # =====================================================================

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Handle main page request."""
        try:
            browser_session = self._get_or_create_browser_session(request)

            config = get_config()
            device_name = config.config.device_name

            file_list_html = ""
            for file_info in self.session.files:
                size_str = self._format_size(file_info.get("size", 0))
                file_list_html += f"""
                <li class="file-item">
                    <div class="file-info">
                        <div class="file-name">{file_info["name"]}</div>
                        <div class="file-size">{size_str}</div>
                    </div>
                    <a href="/download/{file_info["name"]}" class="btn btn-primary btn-sm">
                        Download
                    </a>
                </li>
                """

            empty_display = "none" if self.session.files else "block"
            file_count = len(self.session.files)

            browser_count = self.get_browser_session_count()
            browser_text = f"{browser_count} browser{'s' if browser_count != 1 else ''} connected"
            connection_info = f"Connected from: {request.remote} | {browser_text}"

            html = WEB_UI_HTML.replace("{{device_name}}", device_name)
            html = html.replace("{{file_count}}", str(file_count))
            html = html.replace("{{file_list}}", file_list_html)
            html = html.replace("{{empty_display}}", empty_display)
            html = html.replace("{{session_id}}", self.session.id)
            html = html.replace("{{connection_info}}", connection_info)

            return web.Response(text=html, content_type="text/html")

        except Exception as e:
            logger.error(f"Error rendering index: {e}")
            return web.Response(status=500, text="Internal Server Error")

    async def _handle_download(self, request: web.Request) -> web.Response:
        """Handle file download request (HTTP streaming - unchanged)."""
        try:
            browser_session = self._get_or_create_browser_session(request)

            filename = request.match_info.get("filename", "")
            if not filename:
                return web.Response(status=400, text="Filename required")

            file_info = None
            for f in self.session.files:
                if f["name"] == filename:
                    file_info = f
                    break

            if not file_info:
                return web.Response(status=404, text="File not found")

            file_path = Path(file_info["path"])
            if not file_path.exists():
                return web.Response(status=404, text="File not found on server")

            file_size = file_info.get("size", 0)
            self._update_browser_activity(
                browser_session.id,
                bytes_count=file_size,
                download=True
            )

            # HTTP file streaming (unchanged)
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(file_info["size"]),
                },
            )
            await response.prepare(request)

            chunk_size = get_config().config.chunk_size
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    await response.write(chunk)

            await response.write_eof()
            logger.info(f"File downloaded: {filename} by {request.remote}")
            return response

        except Exception as e:
            logger.error(f"Download error: {e}")
            return web.Response(status=500, text="Download failed")

    async def _handle_upload(self, request: web.Request) -> web.Response:
        """Handle file upload request with approval."""
        try:
            browser_session = self._get_or_create_browser_session(request)

            reader = await request.multipart()

            filename = None
            session_id = None
            file_size = 0

            # Stream upload to temp file
            temp_fd, temp_path = tempfile.mkstemp(prefix="sharex_upload_")
            try:
                with os.fdopen(temp_fd, "wb") as f:
                    async for part in reader:
                        if part.name == "file":
                            filename = part.filename
                            while True:
                                chunk = await part.read_chunk()
                                if not chunk:
                                    break
                                f.write(chunk)
                                file_size += len(chunk)
                        elif part.name == "filename":
                            filename = (await part.read()).decode("utf-8")
                        elif part.name == "session_id":
                            session_id = (await part.read()).decode("utf-8")
            except Exception as e:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                logger.error(f"Upload stream error: {e}")
                return web.json_response({"error": "Upload failed"}, status=500)

            if not filename or file_size == 0:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return web.json_response({"error": "Missing file"}, status=400)

            if session_id != self.session.id:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return web.json_response({"error": "Invalid session"}, status=403)

            client_ip = request.remote or "unknown"

            if file_size > self.session.max_upload_size:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return web.json_response(
                    {"error": f"File too large. Max: {self._format_size(self.session.max_upload_size)}"},
                    status=413,
                )

            # Create upload request for approval
            upload_id = hashlib.sha256(
                f"{filename}{client_ip}{time.time()}".encode()
            ).hexdigest()[:16]

            upload_request = UploadRequest(
                id=upload_id,
                filename=filename,
                file_size=file_size,
                client_ip=client_ip,
                temp_path=temp_path,
                session_id=session_id,
            )

            async with self._lock:
                self._pending_uploads[upload_id] = upload_request
                self._upload_futures[upload_id] = asyncio.get_event_loop().create_future()

            # Request approval
            if self.on_upload_request:
                try:
                    approved = await self.on_upload_request(upload_request)
                except Exception as e:
                    logger.error(f"Approval callback error: {e}")
                    approved = False
            else:
                approved = True

            if not approved:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                async with self._lock:
                    self._pending_uploads.pop(upload_id, None)
                    self._upload_futures.pop(upload_id, None)
                return web.json_response(
                    {"error": "Upload rejected by user"},
                    status=403,
                )

            # Move to final location
            config = get_config()
            download_dir = Path(config.config.download_folder)
            if not download_dir.exists():
                download_dir = Path(config.config.fallback_download_folder)
            download_dir.mkdir(parents=True, exist_ok=True)

            dest_path = download_dir / filename
            counter = 1
            original_dest = dest_path
            while dest_path.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
                dest_path = download_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            shutil.move(temp_path, str(dest_path))

            # Calculate checksum
            sha256_hash = hashlib.sha256()
            async with aiofiles.open(dest_path, "rb") as f:
                while True:
                    chunk = await f.read(65536)
                    if not chunk:
                        break
                    sha256_hash.update(chunk)
            checksum = sha256_hash.hexdigest()

            self.session.add_uploaded_file(
                file_name=filename,
                file_path=str(dest_path),
                file_size=file_size,
                uploader_ip=client_ip,
            )

            self._update_browser_activity(
                browser_session.id,
                bytes_count=file_size,
                upload=True
            )

            # Broadcast file update via WebSocket
            asyncio.create_task(self._broadcast_file_update())

            async with self._lock:
                self._pending_uploads.pop(upload_id, None)
                future = self._upload_futures.pop(upload_id, None)
                if future and not future.done():
                    future.set_result(True)

            return web.json_response({
                "success": True,
                "filename": filename,
                "size": file_size,
                "checksum": checksum,
            })

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return web.json_response(
                {"error": f"Upload failed: {str(e)}"},
                status=500,
            )

    # =====================================================================
    # API HANDLERS (HTTP FALLBACK - UNCHANGED)
    # =====================================================================

    async def _handle_api_files(self, request: web.Request) -> web.Response:
        """Handle API request for file list."""
        self._get_or_create_browser_session(request)
        return web.json_response({
            "files": self.session.files,
            "uploaded_files": self.session.uploaded_files,
            "device_name": get_config().config.device_name,
        })

    async def _handle_api_status(self, request: web.Request) -> web.Response:
        """Handle API request for server status."""
        self._get_or_create_browser_session(request)
        return web.json_response({
            "status": self.session.status.value,
            "device_name": get_config().config.device_name,
            "url": self.session.url,
            "files_count": len(self.session.files),
            "uploaded_count": len(self.session.uploaded_files),
            "browser_count": self.get_browser_session_count(),
            "browser_sessions": [s.to_dict() for s in self.get_active_browser_sessions()],
            "websocket_count": self._ws_manager.get_connection_count(),
        })

    async def _handle_api_browsers(self, request: web.Request) -> web.Response:
        """Handle API request for browser sessions."""
        self._get_or_create_browser_session(request)
        sessions = self.get_active_browser_sessions()
        return web.json_response({
            "count": len(sessions),
            "browsers": [s.to_dict() for s in sessions],
        })

    async def _handle_api_browser_count(self, request: web.Request) -> web.Response:
        """Handle API request for browser count."""
        self._get_or_create_browser_session(request)
        return web.json_response({
            "count": self.get_browser_session_count(),
            "websocket_count": self._ws_manager.get_connection_count(),
        })

    # =====================================================================
    # UPLOAD MANAGEMENT
    # =====================================================================

    def approve_upload(self, upload_id: str, approved: bool = True) -> bool:
        """Approve or reject a pending upload."""
        try:
            upload = self._pending_uploads.get(upload_id)
            if not upload:
                return False

            upload.approved = approved
            upload.approval_time = time.time()

            future = self._upload_futures.get(upload_id)
            if future and not future.done():
                future.set_result(approved)

            return True
        except Exception as e:
            logger.error(f"Error approving upload: {e}")
            return False

    def get_pending_uploads(self) -> List[UploadRequest]:
        """Get list of pending upload requests."""
        return list(self._pending_uploads.values())

    @staticmethod
    def _format_size(size: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def __del__(self) -> None:
        """Cleanup on destruction."""
        if self._pending_uploads:
            for upload in self._pending_uploads.values():
                try:
                    if os.path.exists(upload.temp_path):
                        os.unlink(upload.temp_path)
                except OSError:
                    pass
