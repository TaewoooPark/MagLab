"""Gateway daemon — routing, sessions, proactive notifications, human gate (§8, T-P6-32).

Architecture
------------
- ``asyncio`` event loop drives all three adapters concurrently.
- ``GatewayRunner.start()`` launches the daemon; ``stop()`` shuts it down cleanly.
- A shared ``NotificationBus`` (asyncio queue) routes internal events to adapters
  for proactive push (simulation done, Ralph milestone, review done, figure produced).
- The command registry maps text commands to handler coroutines.

Daemon mode
-----------
``maglab gateway start`` forks to background and writes a PID file at
``~/.maglab/gateway.pid``.
``maglab gateway stop`` reads the PID file and sends SIGTERM.
``maglab gateway status`` checks whether the process is alive.

Security (§8)
-------------
All adapters enforce ``allowed_users`` / ``allowed_channels`` before any message
reaches the runner.  The runner itself only handles already-verified ``UnifiedMessage``
objects.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import platformdirs

from maglab.gateway.adapters.base import BaseAdapter, UnifiedMessage
from maglab.gateway.session_db import SessionDB

log = logging.getLogger(__name__)

_APP = "maglab"
_PID_FILENAME = "gateway.pid"

# ---------------------------------------------------------------------------
# Notification event types
# ---------------------------------------------------------------------------


class NotificationEvent:
    """A proactive notification pushed by the harness to the gateway.

    Attributes
    ----------
    kind:
        Event kind — ``"sim_done"``, ``"ralph_milestone"``, ``"review_done"``,
        ``"figure_produced"``.
    channel:
        Target channel ID (adapter-specific).
    platform:
        Which adapter to use — ``"slack"``, ``"telegram"``, ``"discord"``, or
        ``"all"`` to broadcast.
    payload:
        Arbitrary payload dict (e.g. ``{"task_id": "...", "figure_path": "..."}``.
    """

    def __init__(
        self,
        kind: str,
        channel: str,
        platform: str = "all",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.kind = kind
        self.channel = channel
        self.platform = platform
        self.payload: dict[str, Any] = payload or {}

    def format_text(self) -> str:
        """Return a human-readable text representation of the event."""
        labels = {
            "sim_done": "Simulation complete",
            "ralph_milestone": "Ralph loop milestone",
            "review_done": "Review complete",
            "figure_produced": "Figure produced",
        }
        label = labels.get(self.kind, self.kind)
        task_id = self.payload.get("task_id", "")
        extra = f" — task {task_id}" if task_id else ""
        return f"[MagLab] {label}{extra}"


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# Type alias for command handler: async fn(msg, session_db) -> reply_text
CommandHandler = Callable[[UnifiedMessage, SessionDB], Awaitable[str]]

_COMMAND_REGISTRY: dict[str, CommandHandler] = {}


def register_command(name: str, handler: CommandHandler) -> None:
    """Register a gateway command handler.

    Parameters
    ----------
    name:
        Command keyword (e.g. ``"status"``, ``"stop"``).
    handler:
        Async function ``(UnifiedMessage, SessionDB) → str``.
    """
    _COMMAND_REGISTRY[name] = handler


# Default built-in commands ––––––––––––––––––––––––––––––––––––––––––––––––


async def _cmd_status(msg: UnifiedMessage, db: SessionDB) -> str:
    session = db.get_or_create_session(msg.platform, msg.user_id_hash, msg.channel)
    return f"[MagLab Gateway] Running.\nPlatform: {msg.platform} | Session: {session.id[:8]}…"


async def _cmd_help(msg: UnifiedMessage, db: SessionDB) -> str:
    commands = ", ".join(sorted(_COMMAND_REGISTRY.keys()))
    return f"[MagLab Gateway] Available commands: {commands}"


register_command("status", _cmd_status)
register_command("help", _cmd_help)


# ---------------------------------------------------------------------------
# GatewayRunner
# ---------------------------------------------------------------------------


class GatewayRunner:
    """Async gateway daemon that routes messages across platform adapters.

    Parameters
    ----------
    adapters:
        Dict mapping platform name to adapter instance.
    db_path:
        Path to the SQLite session database.
    notification_queue:
        External ``asyncio.Queue`` for proactive notifications.  If ``None``,
        a new queue is created internally.
    """

    def __init__(
        self,
        adapters: dict[str, BaseAdapter] | None = None,
        db_path: Path | None = None,
        notification_queue: asyncio.Queue[NotificationEvent] | None = None,
    ) -> None:
        self._adapters: dict[str, BaseAdapter] = adapters or {}
        self._db = SessionDB(db_path)
        self._notification_queue: asyncio.Queue[NotificationEvent] = (
            notification_queue or asyncio.Queue()
        )
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def notification_queue(self) -> asyncio.Queue[NotificationEvent]:
        """The notification queue — external callers push events here."""
        return self._notification_queue

    def add_adapter(self, platform: str, adapter: BaseAdapter) -> None:
        """Register a platform adapter at runtime."""
        self._adapters[platform] = adapter

    async def start(self) -> None:
        """Start the notification dispatcher loop."""
        self._running = True
        log.info("[gateway] Runner starting with adapters: %s", list(self._adapters))
        notif_task = asyncio.create_task(self._notification_loop(), name="gateway_notifications")
        self._tasks.append(notif_task)

    async def stop(self) -> None:
        """Gracefully shut down all tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._db.close()
        log.info("[gateway] Runner stopped.")

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------

    async def handle_message(
        self,
        platform: str,
        raw: dict[str, Any],
    ) -> str | None:
        """Route a raw platform event through the full gateway pipeline.

        1. Verify request (signature + allowlist).
        2. Parse to ``UnifiedMessage``.
        3. Look up / create session.
        4. Dispatch to command registry or return None (no match).
        5. Send reply via adapter.

        Parameters
        ----------
        platform:
            Platform name (``"slack"``, ``"telegram"``, ``"discord"``).
        raw:
            Raw event dict from the platform.

        Returns
        -------
        str | None
            The reply text, or ``None`` if the request was not authorised or
            did not match any command.
        """
        adapter = self._adapters.get(platform)
        if adapter is None:
            log.warning("[gateway] No adapter registered for platform=%s", platform)
            return None

        # 1. Verify
        if not adapter.verify_request(raw):
            log.info("[gateway] Request rejected by adapter: platform=%s", platform)
            return None

        # 2. Parse
        msg = adapter.parse_message(raw)

        # 3. Session
        session = self._db.get_or_create_session(msg.platform, msg.user_id_hash, msg.channel)
        self._db.log_message(session.id, "user", msg.text)

        # 4. Command dispatch
        reply = await self._dispatch_command(msg)

        if reply is None:
            reply = "[MagLab] Command not recognised. Try 'help' for a list of available commands."

        # 5. Reply
        await adapter.send_reply(msg.channel, reply)
        self._db.log_message(session.id, "assistant", reply)
        return reply

    async def _dispatch_command(self, msg: UnifiedMessage) -> str | None:
        """Dispatch a message to a registered command handler.

        The first word of ``msg.text`` (after stripping a leading ``/`` or
        ``!`` prefix) is used as the command keyword.

        Returns ``None`` if no matching handler is found.
        """
        text = msg.text.strip().lstrip("/!")
        parts = text.split(maxsplit=1)
        if not parts:
            return None

        cmd_key = parts[0].lower()
        handler = _COMMAND_REGISTRY.get(cmd_key)
        if handler is None:
            return None

        try:
            return await handler(msg, self._db)
        except Exception:  # noqa: BLE001
            log.exception("[gateway] Command handler %s raised", cmd_key)
            return "[MagLab] Internal error while processing your command."

    # ------------------------------------------------------------------
    # Proactive notification loop
    # ------------------------------------------------------------------

    async def _notification_loop(self) -> None:
        """Drain the notification queue and push messages to adapters."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._notification_queue.get(), timeout=1.0)
                await self._send_notification(event)
                self._notification_queue.task_done()
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                log.exception("[gateway] Notification loop error")

    async def _send_notification(self, event: NotificationEvent) -> None:
        """Push a notification event to the appropriate adapter(s)."""
        text = event.format_text()
        figure_path_str: str | None = event.payload.get("figure_path")
        attachments: list[Any] = [figure_path_str] if figure_path_str else []

        if event.platform == "all":
            targets = list(self._adapters.items())
        else:
            adapter = self._adapters.get(event.platform)
            targets = [(event.platform, adapter)] if adapter else []

        for platform, adapter in targets:
            if adapter is None:
                continue
            try:
                await adapter.send_reply(event.channel, text, attachments or None)
                log.info(
                    "[gateway] Notification sent: kind=%s platform=%s channel=%s",
                    event.kind,
                    platform,
                    event.channel,
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "[gateway] Failed to send notification: kind=%s platform=%s",
                    event.kind,
                    platform,
                )


# ---------------------------------------------------------------------------
# Daemon process management (PID file helpers)
# ---------------------------------------------------------------------------


def _pid_path() -> Path:
    """Return the path to the PID file (``~/.maglab/gateway.pid``)."""
    data_dir = Path(platformdirs.user_data_dir(_APP))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _PID_FILENAME


def write_pid() -> None:
    """Write the current process PID to the PID file."""
    _pid_path().write_text(str(os.getpid()))


def read_pid() -> int | None:
    """Read and return the PID from the PID file, or ``None`` if not found."""
    pid_file = _pid_path()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def remove_pid() -> None:
    """Remove the PID file (called on clean shutdown)."""
    with contextlib.suppress(OSError):
        _pid_path().unlink(missing_ok=True)


def is_running() -> bool:
    """Return ``True`` if the gateway daemon appears to be running."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # Signal 0: check existence, no effect
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop_daemon() -> bool:
    """Send SIGTERM to the daemon process.

    Returns ``True`` if the signal was sent, ``False`` if no daemon was found.
    """
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        remove_pid()
        return True
    except (ProcessLookupError, PermissionError):
        remove_pid()
        return False


# ---------------------------------------------------------------------------
# systemd / launchd unit generation
# ---------------------------------------------------------------------------


def generate_systemd_unit(maglab_executable: str = "maglab") -> str:
    """Generate a systemd user service unit for the gateway daemon.

    Parameters
    ----------
    maglab_executable:
        Path or name of the ``maglab`` executable.

    Returns
    -------
    str
        Content of the ``.service`` unit file.
    """
    return f"""\
[Unit]
Description=MagLab Messaging Gateway Daemon
After=network.target

[Service]
Type=simple
ExecStart={maglab_executable} gateway start --foreground
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""


def generate_launchd_plist(maglab_executable: str = "maglab") -> str:
    """Generate a macOS launchd plist for the gateway daemon.

    Parameters
    ----------
    maglab_executable:
        Path or name of the ``maglab`` executable.

    Returns
    -------
    str
        Content of the launchd ``.plist`` file.
    """
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.maglab.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>{maglab_executable}</string>
        <string>gateway</string>
        <string>start</string>
        <string>--foreground</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.maglab/gateway.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.maglab/gateway.err</string>
</dict>
</plist>
"""


def install_service(maglab_executable: str = "maglab") -> Path:
    """Install the platform-appropriate service file for the gateway daemon.

    - macOS: writes ``~/Library/LaunchAgents/com.maglab.gateway.plist``.
    - Linux: writes ``~/.config/systemd/user/maglab-gateway.service``.

    In both cases the credential directory is checked for 0600 permissions
    before writing.

    Parameters
    ----------
    maglab_executable:
        Path or name of the ``maglab`` executable (defaults to ``"maglab"``).

    Returns
    -------
    Path
        Path to the written service file.

    Raises
    ------
    PermissionError
        If the gateway credential file exists with insecure permissions.
    RuntimeError
        If the platform is not macOS or Linux.
    """
    # Security invariant: credential file must be 0600 before registering a
    # system daemon.  This guard applies even when install_service is called
    # programmatically (not via the CLI wrapper).
    from maglab.gateway.adapters.base import check_credential_permissions

    cred_file = Path.home() / ".maglab" / "gateway.yaml"
    if cred_file.exists():
        check_credential_permissions(cred_file)

    if sys.platform == "darwin":
        target = Path.home() / "Library" / "LaunchAgents" / "com.maglab.gateway.plist"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generate_launchd_plist(maglab_executable))
        log.info("[gateway] launchd plist written to %s", target)
        return target
    elif sys.platform.startswith("linux"):
        target = Path.home() / ".config" / "systemd" / "user" / "maglab-gateway.service"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generate_systemd_unit(maglab_executable))
        log.info("[gateway] systemd unit written to %s", target)
        return target
    else:
        raise RuntimeError(f"Unsupported platform for service installation: {sys.platform}")
