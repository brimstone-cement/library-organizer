"""Sidecar and Script 2 hint helpers."""

import json
from pathlib import Path

from pdf_organizer.hints import (
    MetadataHints,
    delete_sidecar,
    load_sidecar,
    sidecar_path_for,
    write_sidecar,
)


def test_sidecar_roundtrip(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    side = sidecar_path_for(pdf)
    assert side.name == "paper.meta.json"
    write_sidecar(side, MetadataHints(doi="10.1/x", title="Hello"))
    loaded = load_sidecar(side)
    assert loaded.doi == "10.1/x"
    assert loaded.title == "Hello"
    assert loaded.year is None
    delete_sidecar(side)
    assert not side.exists()


def test_load_missing_sidecar_empty(tmp_path: Path):
    assert load_sidecar(tmp_path / "nope.meta.json").to_dict() == {}


def test_write_sidecar_omits_empty_fields(tmp_path: Path):
    path = tmp_path / "x.meta.json"
    write_sidecar(path, MetadataHints(doi="10.2/y", title=""))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"doi": "10.2/y"}
