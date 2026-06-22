"""WebSocket Manager Additions for Browser Push.

Add these methods to the existing WebSocketManager class in webshare_server.py.
"""

# Add these methods to WebSocketManager class:

async def send_to_session(self, session_id: str, message) -> bool:
    """Send a message to a specific browser session.

    Args:
        session_id: Browser session ID.
        message: WSMessage to send.

    Returns:
        True if sent successfully.
    """
    conn = self._connections.get(session_id)
    if not conn:
        logger.warning(f"No WebSocket connection for session: {session_id}")
        return False

    try:
        await conn.ws.send_str(message.to_json())
        return True
    except Exception as e:
        logger.error(f"Failed to send to session {session_id}: {e}")
        return False

async def send_to_all_except(self, exclude_session_id: str, message) -> None:
    """Broadcast to all except one session.

    Args:
        exclude_session_id: Session to exclude.
        message: WSMessage to send.
    """
    for sid, conn in self._connections.items():
        if sid == exclude_session_id:
            continue
        try:
            await conn.ws.send_str(message.to_json())
        except Exception as e:
            logger.error(f"Broadcast error to {sid}: {e}")
