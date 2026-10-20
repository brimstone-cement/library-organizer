"""On-disk destination uniqueness (overwrite guard)."""

from pathlib import Path

from pdf_organizer.pipeline import _unique_dest_name


def test_unique_dest_name_no_clash(tmp_path: Path):
    name, disambiguated = _unique_dest_name(tmp_path, "2020_Smith_title.pdf", "abcdef123")
    assert name == "2020_Smith_title.pdf"
    assert disambiguated is False


def test_unique_dest_name_avoids_existing(tmp_path: Path):
    (tmp_path / "2020_Smith_title.pdf").write_bytes(b"x")
    name, disambiguated = _unique_dest_name(tmp_path, "2020_Smith_title.pdf", "abcdef123")
    assert name != "2020_Smith_title.pdf"
    assert name.endswith(".pdf")
    assert disambiguated is True
    assert not (tmp_path / name).exists()


def test_unique_dest_name_second_collision_differs(tmp_path: Path):
    (tmp_path / "2020_Smith_title.pdf").write_bytes(b"x")
    first, _ = _unique_dest_name(tmp_path, "2020_Smith_title.pdf", "abcdef123")
    (tmp_path / first).write_bytes(b"y")
    second, disambiguated = _unique_dest_name(tmp_path, "2020_Smith_title.pdf", "abcdef123")
    assert disambiguated is True
    assert second != first
    assert not (tmp_path / second).exists()
