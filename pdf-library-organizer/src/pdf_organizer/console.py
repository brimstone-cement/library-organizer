"""Console helpers for Windows-safe Unicode output."""

from __future__ import annotations

import sys


def configure_stdio() -> None:
    """Prefer UTF-8 on stdout/stderr when the runtime supports it."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — leave stream as-is
                pass


def safe_print(*args, **kwargs) -> None:
    """print() that never crashes on UnicodeEncodeError (e.g. Greek on cp1252)."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        file = kwargs.get("file", sys.stdout)
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(a) for a in args) + end
        encoding = getattr(file, "encoding", None) or "ascii"
        raw = text.encode(encoding, errors="replace")
        if hasattr(file, "buffer"):
            file.buffer.write(raw)
            file.buffer.flush()
        else:
            print(raw.decode(encoding, errors="replace"), end="", file=file)
