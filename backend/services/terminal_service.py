"""
Terminal Service — manages PTY (pseudo-terminal) sessions for the Brownfield IDE.

Uses pywinpty on Windows to provide a real interactive shell (PowerShell).
Falls back to subprocess pipes if pywinpty is unavailable.
"""

import asyncio
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Detect whether pywinpty is available
try:
    from winpty import PtyProcess as _PtyProcess
    _HAS_WINPTY = True
    logger.info("pywinpty detected — using PTY terminal backend")
except ImportError:
    _HAS_WINPTY = False
    logger.warning(
        "pywinpty not found — falling back to subprocess pipes. "
        "Install pywinpty for full terminal support: pip install pywinpty"
    )


# ---------------------------------------------------------------------------
# Terminal Session
# ---------------------------------------------------------------------------

class TerminalSession:
    """
    A single terminal session backed by either a Windows PTY (pywinpty)
    or a plain subprocess as fallback.
    """

    def __init__(self, session_id: str, cwd: str, cols: int = 80, rows: int = 24):
        self.session_id = session_id
        self.cwd = cwd
        self.cols = cols
        self.rows = rows
        self.created_at: str = datetime.now(timezone.utc).isoformat()

        # Output from the shell is put here; the WS reader pulls from it
        self._output_queue: queue.Queue = queue.Queue(maxsize=2000)

        self._pty = None          # pywinpty PtyProcess (if available)
        self._proc = None         # subprocess.Popen  (fallback)
        self._reader_thread: Optional[threading.Thread] = None
        self._alive: bool = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the shell process and start the reader thread."""
        if _HAS_WINPTY:
            self._start_pty()
        else:
            self._start_subprocess()

    def _start_pty(self) -> None:
        """Start a real PTY via pywinpty."""
        try:
            self._pty = _PtyProcess.spawn(
                ["powershell.exe", "-NoLogo"],
                dimensions=(self.rows, self.cols),
                cwd=self.cwd,
            )
        except Exception as exc:
            logger.error(f"PTY spawn failed: {exc}")
            # Fall back to subprocess
            self._start_subprocess()
            return

        self._reader_thread = threading.Thread(
            target=self._pty_reader_loop, daemon=True, name=f"pty-{self.session_id[:8]}"
        )
        self._reader_thread.start()

    def _pty_reader_loop(self) -> None:
        """Background thread: read PTY output → queue."""
        while self._alive:
            try:
                if not self._pty.isalive():
                    break
                data = self._pty.read(4096)
                if data:
                    self._output_queue.put(data)
            except EOFError:
                break
            except Exception as exc:
                if self._alive:
                    logger.debug(f"PTY read: {exc}")
                break
        self._output_queue.put(None)  # EOF sentinel

    def _start_subprocess(self) -> None:
        """Fallback: start cmd.exe via subprocess with pipes."""
        import subprocess
        try:
            self._proc = subprocess.Popen(
                ["powershell.exe", "-NoLogo"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception:
            self._proc = subprocess.Popen(
                ["cmd.exe"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

        self._reader_thread = threading.Thread(
            target=self._subprocess_reader_loop,
            daemon=True,
            name=f"proc-{self.session_id[:8]}",
        )
        self._reader_thread.start()

    def _subprocess_reader_loop(self) -> None:
        """Background thread: read subprocess stdout → queue."""
        try:
            for line in self._proc.stdout:
                if not self._alive:
                    break
                self._output_queue.put(line)
        except Exception as exc:
            if self._alive:
                logger.debug(f"Subprocess read: {exc}")
        finally:
            self._output_queue.put(None)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def write(self, data: str) -> None:
        """Send user input to the shell."""
        try:
            if self._pty is not None and self._pty.isalive():
                self._pty.write(data)
            elif self._proc is not None and self._proc.poll() is None:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
        except Exception as exc:
            logger.debug(f"Terminal write error: {exc}")

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal window."""
        self.rows = rows
        self.cols = cols
        if self._pty is not None:
            try:
                self._pty.setwinsize(rows, cols)
            except Exception as exc:
                logger.debug(f"PTY resize error: {exc}")

    async def get_output(self, timeout: float = 0.05) -> Optional[str]:
        """
        Async-friendly: pull pending output from the internal queue.
        Returns "" if no data is ready, None on EOF.
        """
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: self._output_queue.get(timeout=timeout),
            )
            return data  # May be None (EOF sentinel)
        except queue.Empty:
            return ""

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        if self._pty is not None:
            try:
                return self._pty.isalive()
            except Exception:
                return False
        if self._proc is not None:
            return self._proc.poll() is None
        return False

    def kill(self) -> None:
        """Terminate the session."""
        self._alive = False
        if self._pty is not None:
            try:
                self._pty.terminate(force=True)
            except Exception:
                pass
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Terminal Manager (singleton)
# ---------------------------------------------------------------------------

class TerminalManager:
    """Manages the collection of active terminal sessions."""

    def __init__(self):
        self._sessions: Dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def create_session(self, cwd: str, cols: int = 80, rows: int = 24) -> str:
        """Create and start a new terminal session. Returns session_id."""
        session_id = str(uuid.uuid4())
        session = TerminalSession(session_id, cwd, cols, rows)
        session.start()
        with self._lock:
            self._sessions[session_id] = session
        logger.info(f"Terminal session created: {session_id[:8]} cwd={cwd}")
        return session_id

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def kill_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            session.kill()
            logger.info(f"Terminal session killed: {session_id[:8]}")

    def list_sessions(self) -> list:
        with self._lock:
            return [
                {
                    "session_id": sid,
                    "cwd": s.cwd,
                    "alive": s.is_alive(),
                    "created_at": s.created_at,
                }
                for sid, s in self._sessions.items()
            ]

    def cleanup_dead(self) -> None:
        """Remove sessions whose processes have exited."""
        with self._lock:
            dead = [sid for sid, s in self._sessions.items() if not s.is_alive()]
            for sid in dead:
                del self._sessions[sid]
                logger.debug(f"Cleaned up dead session: {sid[:8]}")


# Global singleton
terminal_manager = TerminalManager()
