"""Web Share Server for ShareX.

Provides a lightweight HTTP server that allows any device
with a web browser to download and upload files without
installing ShareX.
"""

import os
import json
import time
import asyncio
import logging
import hashlib
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

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


# Mobile-friendly HTML template - completely self-contained, no external dependencies
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
        .file-list {
            list-style: none;
        }
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
        .file-info {
            flex: 1;
            min-width: 0;
        }
        .file-name {
            font-size: 0.9rem;
            color: #eaeaea;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 4px;
        }
        .file-size {
            font-size: 0.75rem;
            color: #a0a0a0;
        }
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
        .btn-primary {
            background: #00d9ff;
            color: #0f0f23;
        }
        .btn-primary:hover { background: #33e0ff; }
        .btn-success {
            background: #00ff88;
            color: #0f0f23;
        }
        .btn-success:hover { background: #33ffaa; }
        .btn-danger {
            background: #e94560;
            color: #fff;
        }
        .btn-danger:hover { background: #ff6b81; }
        .btn-sm {
            padding: 6px 12px;
            font-size: 0.8rem;
        }
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
        .upload-icon {
            font-size: 2.5rem;
            margin-bottom: 12px;
        }
        .upload-text {
            font-size: 1rem;
            color: #eaeaea;
            margin-bottom: 8px;
        }
        .upload-hint {
            font-size: 0.8rem;
            color: #a0a0a0;
        }
        #file-input { display: none; }
        .progress-container {
            display: none;
            margin-top: 16px;
        }
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
        .progress-text {
            font-size: 0.8rem;
            color: #a0a0a0;
            text-align: center;
        }
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
        .file-preview-name {
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .file-preview-size {
            color: #a0a0a0;
            font-size: 0.75rem;
        }
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #a0a0a0;
        }
        .empty-state-icon {
            font-size: 3rem;
            margin-bottom: 16px;
            opacity: 0.5;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .status-active {
            background: rgba(0, 255, 136, 0.2);
            color: #00ff88;
        }
        .footer {
            text-align: center;
            padding: 20px;
            font-size: 0.75rem;
            color: #666;
        }
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
                    if (item) {
                        traverseFileTree(item, files);
                    }
                }
                setTimeout(() => {
                    selectedFiles = files;
                    updateFilePreviews();
                }, 100);
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
                div.innerHTML = `
                    <span class="file-preview-name">${file.name}</span>
                    <span class="file-preview-size">${formatSize(file.size)}</span>
                `;
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
            setTimeout(() => {
                progressContainer.style.display = 'none';
                progressFill.style.width = '0%';
            }, 2000);
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

    Attributes:
        session: Current web share session.
        on_upload_request: Callback for upload approval.
        on_status_change: Callback for status changes.
        _app: aiohttp application instance.
        _runner: aiohttp server runner.
        _site: aiohttp server site.
    """

    def __init__(
        self,
        session: WebShareSession,
        on_upload_request: Optional[Callable[[UploadRequest], asyncio.Future]] = None,
        on_status_change: Optional[Callable[[WebShareStatus], None]] = None,
    ) -> None:
        """Initialize web share server.

        Args:
            session: Web share session configuration.
            on_upload_request: Callback triggered when upload needs approval.
            on_status_change: Callback triggered on status changes.
        """
        self.session = session
        self.on_upload_request = on_upload_request
        self.on_status_change = on_status_change
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._pending_uploads: Dict[str, UploadRequest] = {}
        self._upload_futures: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        logger.info(f"WebShareServer initialized for session {session.id}")

    async def start(self) -> None:
        """Start the HTTP server."""
        try:
            self.session.status = WebShareStatus.STARTING
            self._notify_status_change()

            self._app = web.Application()
            self._setup_routes()

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()

            self._site = web.TCPSite(
                self._runner,
                self.session.ip_address,
                self.session.port,
            )
            await self._site.start()

            self.session.status = WebShareStatus.ACTIVE
            self._notify_status_change()
            logger.info(f"Web share server started at {self.session.url}")

        except Exception as e:
            self.session.status = WebShareStatus.ERROR
            self._notify_status_change()
            logger.error(f"Failed to start web share server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the HTTP server."""
        try:
            self.session.status = WebShareStatus.STOPPING
            self._notify_status_change()

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
        """Configure HTTP routes."""
        if not self._app:
            return

        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/download/{filename}", self._handle_download)
        self._app.router.add_post("/upload", self._handle_upload)
        self._app.router.add_get("/api/files", self._handle_api_files)
        self._app.router.add_get("/api/status", self._handle_api_status)
        self._app.router.add_static("/downloads", path=get_config().config.download_folder, name="downloads")

    def _notify_status_change(self) -> None:
        """Notify status change callback."""
        if self.on_status_change:
            try:
                self.on_status_change(self.session.status)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Handle main page request.

        Args:
            request: HTTP request.

        Returns:
            HTML response.
        """
        try:
            config = get_config()
            device_name = config.config.device_name

            # Build file list HTML
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
            connection_info = f"Connected from: {request.remote}"

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
        """Handle file download request.

        Args:
            request: HTTP request with filename.

        Returns:
            File response or error.
        """
        try:
            filename = request.match_info.get("filename", "")
            if not filename:
                return web.Response(status=400, text="Filename required")

            # Find file in session
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

            # Stream file for large file support
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
        """Handle file upload request with approval.

        Args:
            request: HTTP request with file data.

        Returns:
            JSON response indicating upload status.
        """
        try:
            reader = await request.multipart()

            filename = None
            session_id = None
            file_data = b""

            async for part in reader:
                if part.name == "file":
                    filename = part.filename
                    chunks = []
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        chunks.append(chunk)
                    file_data = b"".join(chunks)
                elif part.name == "filename":
                    filename = (await part.read()).decode("utf-8")
                elif part.name == "session_id":
                    session_id = (await part.read()).decode("utf-8")

            if not filename or not file_data:
                return web.json_response(
                    {"error": "Missing file or filename"},
                    status=400,
                )

            if session_id != self.session.id:
                return web.json_response(
                    {"error": "Invalid session"},
                    status=403,
                )

            client_ip = request.remote or "unknown"
            file_size = len(file_data)

            # Check max upload size
            if file_size > self.session.max_upload_size:
                return web.json_response(
                    {"error": f"File too large. Max: {self._format_size(self.session.max_upload_size)}"},
                    status=413,
                )

            # Save to temp file first by streaming chunks to avoid high RAM usage
            temp_fd, temp_path = tempfile.mkstemp(prefix="sharex_upload_")
            filename = None
            session_id = None
            file_size = 0
            
            try:
                with open(temp_fd, "wb") as f:
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
                logger.error(f"Error reading upload stream: {e}")
                return web.json_response(
                    {"error": "Upload stream failed"},
                    status=500,
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

            # Request approval from user
            if self.on_upload_request:
                try:
                    approved = await self.on_upload_request(upload_request)
                except Exception as e:
                    logger.error(f"Approval callback error: {e}")
                    approved = False
            else:
                # Auto-approve if no callback
                approved = True

            if not approved:
                # Clean up temp file
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

            # Move file to download folder
            config = get_config()
            download_dir = Path(config.config.download_folder)
            if not download_dir.exists():
                download_dir = Path(config.config.fallback_download_folder)
            download_dir.mkdir(parents=True, exist_ok=True)

            dest_path = download_dir / filename
            # Handle duplicate filenames
            counter = 1
            original_dest = dest_path
            while dest_path.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
                dest_path = download_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            shutil.move(temp_path, str(dest_path))

            # Calculate SHA-256 checksum
            sha256_hash = hashlib.sha256()
            async with aiofiles.open(dest_path, "rb") as f:
                while True:
                    chunk = await f.read(65536)
                    if not chunk:
                        break
                    sha256_hash.update(chunk)
            checksum = sha256_hash.hexdigest()

            # Add to session uploaded files
            self.session.add_uploaded_file(
                file_name=filename,
                file_path=str(dest_path),
                file_size=file_size,
                uploader_ip=client_ip,
            )

            # Clean up pending
            async with self._lock:
                self._pending_uploads.pop(upload_id, None)
                future = self._upload_futures.pop(upload_id, None)
                if future and not future.done():
                    future.set_result(True)

            logger.info(f"File uploaded: {filename} ({self._format_size(file_size)}) from {client_ip}")

            return web.json_response({
                "success": True,
                "filename": filename,
                "size": file_size,
                "checksum": checksum,
                "message": "Upload complete",
            })

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return web.json_response(
                {"error": f"Upload failed: {str(e)}"},
                status=500,
            )

    async def _handle_api_files(self, request: web.Request) -> web.Response:
        """Handle API request for file list.

        Args:
            request: HTTP request.

        Returns:
            JSON response with file list.
        """
        return web.json_response({
            "files": self.session.files,
            "uploaded_files": self.session.uploaded_files,
            "device_name": get_config().config.device_name,
        })

    async def _handle_api_status(self, request: web.Request) -> web.Response:
        """Handle API request for server status.

        Args:
            request: HTTP request.

        Returns:
            JSON response with status.
        """
        return web.json_response({
            "status": self.session.status.value,
            "device_name": get_config().config.device_name,
            "url": self.session.url,
            "files_count": len(self.session.files),
            "uploaded_count": len(self.session.uploaded_files),
        })

    def approve_upload(self, upload_id: str, approved: bool = True) -> bool:
        """Approve or reject a pending upload.

        Args:
            upload_id: Upload request ID.
            approved: Whether to approve the upload.

        Returns:
            True if action was successful.
        """
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
        """Get list of pending upload requests.

        Returns:
            List of pending uploads.
        """
        return list(self._pending_uploads.values())

    @staticmethod
    def _format_size(size: int) -> str:
        """Format bytes to human-readable string.

        Args:
            size: Size in bytes.

        Returns:
            Formatted string.
        """
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
