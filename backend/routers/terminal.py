"""
Terminal Router — REST endpoints and WebSocket handler for terminal sessions.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.models.schemas import (
    CreateTerminalRequest,
    CreateTerminalResponse,
    SuccessResponse,
)
from backend.services.terminal_service import terminal_manager
from backend.services import workspace_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.post("/api/terminal/create", response_model=CreateTerminalResponse,
             summary="Create a terminal session")
async def create_terminal(body: CreateTerminalRequest):
    """
    Create a new terminal session.  If no cwd is provided, defaults to the
    currently open project root.
    """
    cwd = body.cwd
    if not cwd:
        cwd = workspace_service.get_current_project()
    if not cwd:
        import os
        cwd = os.path.expanduser("~")

    session_id = terminal_manager.create_session(cwd, cols=body.cols, rows=body.rows)
    return CreateTerminalResponse(session_id=session_id, cwd=cwd)


@router.delete("/api/terminal/{session_id}", response_model=SuccessResponse,
               summary="Kill a terminal session")
async def kill_terminal(session_id: str):
    """Kill and remove a terminal session."""
    session = terminal_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    terminal_manager.kill_session(session_id)
    return SuccessResponse(message=f"Session {session_id} terminated.")


@router.get("/api/terminal/sessions", summary="List active terminal sessions")
async def list_terminals():
    """Return all active terminal sessions."""
    terminal_manager.cleanup_dead()
    return terminal_manager.list_sessions()


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

@router.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str):
    """
    Bidirectional WebSocket for a terminal session.

    Client → Server messages (JSON):
      {"type": "input",  "data": "<user keystrokes>"}
      {"type": "resize", "rows": 24, "cols": 80}

    Server → Client messages (JSON):
      {"type": "output", "data": "<terminal output>"}
      {"type": "exit"}
      {"type": "error",  "message": "..."}
    """
    await websocket.accept()
    logger.info(f"WS connected: terminal/{session_id[:8]}")

    session = terminal_manager.get_session(session_id)
    if not session:
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Terminal session not found."})
        )
        await websocket.close(code=1008)
        return

    # Task that streams PTY output to the browser
    async def output_pump():
        while True:
            try:
                data = await session.get_output(timeout=0.05)
                if data is None:
                    # Process exited
                    await websocket.send_text(json.dumps({"type": "exit"}))
                    break
                if data:
                    await websocket.send_text(json.dumps({"type": "output", "data": data}))
            except Exception as exc:
                logger.debug(f"Output pump error: {exc}")
                break

    pump_task = asyncio.create_task(output_pump())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "input":
                    session.write(msg.get("data", ""))
                elif msg_type == "resize":
                    rows = int(msg.get("rows", 24))
                    cols = int(msg.get("cols", 80))
                    session.resize(rows, cols)
                else:
                    logger.warning(f"Unknown WS message type: {msg_type}")
            except (json.JSONDecodeError, ValueError) as exc:
                logger.debug(f"Bad WS message: {exc}")

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: terminal/{session_id[:8]}")
    except Exception as exc:
        logger.error(f"WS error: {exc}")
    finally:
        pump_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
