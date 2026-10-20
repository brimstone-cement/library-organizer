"""Run-level lockfile so Script 1 and Script 2 do not race."""

from __future__ import annotations

import atexit
import os
import secrets
import time
from pathlib import Path


def _pid_is_running(pid: int) -> bool:
    """Return True if pid looks alive (best-effort on Windows/POSIX)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock(path: Path) -> tuple[int | None, str, float]:
    """Return (pid, token, written_at) from lock file."""
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None, "", 0.0
    pid: int | None = None
    token = ""
    written_at = 0.0
    if lines:
        try:
            pid = int(lines[0].strip())
        except ValueError:
            pid = None
    if len(lines) >= 2:
        token = lines[1].strip()
    if len(lines) >= 3:
        try:
            written_at = float(lines[2].strip())
        except ValueError:
            written_at = 0.0
    return pid, token, written_at


class ProcessorLock:
    """
    Exclusive lock with dead-PID recovery and age-based steal.

    Lock file format:
      pid
      token
      unix_timestamp
    """

    def __init__(self, path: Path, *, stale_seconds: float = 1800) -> None:
        self.path = path
        self.stale_seconds = stale_seconds
        self._held = False
        self._token = ""
        self._atexit_registered = False

    def acquire(self, timeout: float = 30) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + timeout
        while True:
            try:
                token = secrets.token_hex(8)
                now = time.time()
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(f"{os.getpid()}\n{token}\n{now}\n")
                self._held = True
                self._token = token
                if not self._atexit_registered:
                    atexit.register(self.release)
                    self._atexit_registered = True
                return
            except FileExistsError:
                if self._can_steal():
                    try:
                        self.path.unlink(missing_ok=True)
                        continue
                    except OSError:
                        pass
                if time.time() >= deadline:
                    raise TimeoutError(f"Could not acquire lock: {self.path}") from None
                time.sleep(0.25)

    def _can_steal(self) -> bool:
        pid, _token, written_at = _read_lock(self.path)
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return True
        if age > self.stale_seconds:
            return True
        if written_at and (time.time() - written_at) > self.stale_seconds:
            return True
        if pid is None or not _pid_is_running(pid):
            return True
        return False

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        # Only delete if we still own the token (avoid wiping a stolen/reacquired lock)
        try:
            _pid, token, _written = _read_lock(self.path)
            if token and self._token and token != self._token:
                return
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> ProcessorLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()
