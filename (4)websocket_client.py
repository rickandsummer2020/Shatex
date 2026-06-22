"""WebSocket Client Handler for Browser Auto-Download.

This JavaScript code should be added to the Web UI HTML in webshare_server.py
to handle 'file_push' messages and auto-initiate downloads.
"""

# Add this to the WEB_UI_HTML template in webshare_server.py
# Inside the <script> section of the existing HTML

WEBSOCKET_CLIENT_JS = """
// WebSocket connection for real-time updates
let ws = null;
let wsReconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 3000;

function connectWebSocket() {
    const wsUrl = `ws://${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log('WebSocket connected');
        wsReconnectAttempts = 0;
        updateConnectionStatus('connected');
    };

    ws.onmessage = function(event) {
        const msg = JSON.parse(event.data);
        handleWebSocketMessage(msg);
    };

    ws.onclose = function() {
        console.log('WebSocket disconnected');
        updateConnectionStatus('disconnected');
        attemptReconnect();
    };

    ws.onerror = function(error) {
        console.error('WebSocket error:', error);
        updateConnectionStatus('error');
    };
}

function attemptReconnect() {
    if (wsReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        wsReconnectAttempts++;
        console.log(`Reconnecting... attempt ${wsReconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`);
        setTimeout(connectWebSocket, RECONNECT_DELAY);
    } else {
        console.log('Max reconnection attempts reached');
        updateConnectionStatus('failed');
    }
}

function handleWebSocketMessage(msg) {
    switch(msg.type) {
        case 'file_push':
            handleFilePush(msg.payload);
            break;
        case 'file_update':
            updateFileList(msg.payload.files);
            break;
        case 'browser_update':
            updateBrowserList(msg.payload.browsers);
            break;
        case 'status_update':
            updateStatus(msg.payload.status);
            break;
        case 'pong':
            // Heartbeat response
            break;
    }
}

function handleFilePush(payload) {
    console.log('File push received:', payload);

    // Show notification
    showNotification(`New file: ${payload.file_name}`, 'info');

    // Auto-download if enabled
    if (payload.auto_download) {
        autoDownloadFile(payload.download_url, payload.file_name);
    }

    // Update file list
    refreshFileList();
}

function autoDownloadFile(url, filename) {
    // Create a hidden iframe or use fetch to trigger download
    const downloadLink = document.createElement('a');
    downloadLink.href = url;
    downloadLink.download = filename;
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);

    showNotification(`Downloading: ${filename}`, 'success');

    // Send download complete acknowledgment
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'download_complete',
            push_id: payload.push_id,
            success: true
        }));
    }
}

function updateConnectionStatus(status) {
    const indicator = document.getElementById('ws-indicator');
    if (indicator) {
        indicator.className = `ws-indicator ws-${status}`;
        indicator.textContent = status === 'connected' ? '● Live' : '○ Offline';
    }
}

function showNotification(message, type) {
    // Create notification element
    const notif = document.createElement('div');
    notif.className = `notification notification-${type}`;
    notif.textContent = message;
    document.body.appendChild(notif);

    setTimeout(() => {
        notif.remove();
    }, 3000);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    connectWebSocket();

    // Send heartbeat every 30 seconds
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({type: 'ping'}));
        }
    }, 30000);
});
"""
