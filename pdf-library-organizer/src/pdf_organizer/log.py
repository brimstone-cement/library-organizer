"""Append-only process log CSV with fallback if the file is locked."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

LOG_FIELDS = [
    "timestamp",
    "script",
    "source_path",
    "source_name",
    "dest_name",
    "dest_path",
    "year",
    "authors",
    "title",
    "report_ids",
    "doi",
    "patent_id",
    "company",
    "file_type",
    "metadata_source",
    "status",
    "error_flags",
    "error_message",
    "file_hash",
]


@dataclass
class LogRow:
    timestamp: str = ""
    script: str = "import"
    source_path: str = ""
    source_name: str = ""
    dest_name: str = ""
    dest_path: str = ""
    year: str = ""
    authors: str = ""
    title: str = ""
    report_ids: str = ""
    doi: str = ""
    patent_id: str = ""
    company: str = ""
    file_type: str = ""
    metadata_source: str = ""
    status: str = ""
    error_flags: str = ""
    error_message: str = ""
    file_hash: str = ""

    def as_dict(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) or "" for f in fields(self)}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ProcessLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: LogRow) -> Path:
        if not row.timestamp:
            row.timestamp = utc_now_iso()
        target = self.path
        try:
            return self._write(target, row)
        except OSError:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback = self.path.with_name(f"process_log_{stamp}.csv")
            return self._write(fallback, row)

    def _write(self, path: Path, row: LogRow) -> Path:
        # utf-8-sig only for new/empty files (Excel BOM). Append with utf-8 so
        # each open does not inject another BOM mid-file.
        last_exc: OSError | None = None
        for _ in range(5):
            try:
                new_file = (not path.is_file()) or path.stat().st_size == 0
                encoding = "utf-8-sig" if new_file else "utf-8"
                mode = "w" if new_file else "a"
                with path.open(mode, encoding=encoding, newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
                    if new_file:
                        writer.writeheader()
                    writer.writerow(row.as_dict())
                return path
            except OSError as exc:
                last_exc = exc
                time.sleep(0.2)
        assert last_exc is not None
        raise last_exc
