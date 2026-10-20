"""safe_move never overwrites."""

import pytest

from pdf_organizer.fsutil import safe_move


def test_safe_move_renames(tmp_path):
    src = tmp_path / "a.pdf"
    dest = tmp_path / "b.pdf"
    src.write_bytes(b"data")
    safe_move(src, dest)
    assert not src.exists()
    assert dest.read_bytes() == b"data"


def test_safe_move_refuses_existing_dest(tmp_path):
    src = tmp_path / "a.pdf"
    dest = tmp_path / "b.pdf"
    src.write_bytes(b"new")
    dest.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        safe_move(src, dest)
    assert dest.read_bytes() == b"old"
    assert src.exists()
