"""Optional metadata hints (Script 2 form / sidecar). Script 1 passes empty hints."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class MetadataHints:
    doi: str | None = None
    year: str | None = None
    authors: str | None = None
    title: str | None = None
    report_ids: str | None = None
    patent_id: str | None = None
    company: str | None = None
    file_type: str | None = None  # article | report | book | patent | manual

    def non_empty(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                out[f.name] = text
        return out

    @classmethod
    def from_mapping(cls, data: dict | None) -> MetadataHints:
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        kwargs = {}
        for key, value in data.items():
            if key not in known or value is None:
                continue
            text = str(value).strip()
            kwargs[key] = text if text else None
        return cls(**kwargs)

    def to_dict(self) -> dict[str, str]:
        return self.non_empty()


def sidecar_path_for(pdf_path: Path) -> Path:
    return pdf_path.with_name(pdf_path.stem + ".meta.json")


def load_sidecar(path: Path | None) -> MetadataHints:
    if path is None or not path.is_file():
        return MetadataHints()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"sidecar must be a JSON object: {path}")
    return MetadataHints.from_mapping(data)


def write_sidecar(path: Path, hints: MetadataHints) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(hints.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def delete_sidecar(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
