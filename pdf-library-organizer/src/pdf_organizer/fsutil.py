"""Safe filesystem moves that never overwrite via copy-fallback."""

from __future__ import annotations

import os
from pathlib import Path


def safe_move(src: Path, dest: Path) -> None:
    """
    Move src -> dest using os.rename only.

    On Windows, shutil.move falls back to copy+delete when rename fails, which
    can overwrite an existing destination. This helper refuses that path.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f"destination already exists: {dest}")
    os.rename(str(src), str(dest))
