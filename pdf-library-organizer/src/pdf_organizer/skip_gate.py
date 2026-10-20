"""Suppress repeated skipped_in_use log rows for unchanged import files."""

from __future__ import annotations

import csv
from pathlib import Path

SKIP_FIELDS = ["source_name", "mtime", "size", "status"]


class SkipLogGate:
    """Only allow logging a skip when name/mtime/size changed since last skip."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._state: dict[str, tuple[str, str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    name = row.get("source_name") or ""
                    if not name:
                        continue
                    self._state[name] = (
                        row.get("mtime") or "",
                        row.get("size") or "",
                        row.get("status") or "",
                    )
        except OSError:
            self._state = {}

    def should_log(self, source_name: str, mtime: float, size: int, status: str) -> bool:
        key = (f"{mtime:.6f}", str(size), status)
        prior = self._state.get(source_name)
        if prior == key:
            return False
        self._state[source_name] = key
        return True

    def clear(self, source_name: str) -> None:
        self._state.pop(source_name, None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=SKIP_FIELDS)
            writer.writeheader()
            for name, (mtime, size, status) in sorted(self._state.items()):
                writer.writerow(
                    {
                        "source_name": name,
                        "mtime": mtime,
                        "size": size,
                        "status": status,
                    }
                )
