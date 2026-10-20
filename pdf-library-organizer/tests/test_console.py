"""Console helpers."""

from pdf_organizer.console import safe_print


def test_safe_print_greek_falls_back_on_narrow_console():
    class RaisingStream:
        encoding = "cp1252"

        def __init__(self) -> None:
            self._data = b""

        def write(self, s: str) -> int:
            raise UnicodeEncodeError("cp1252", s, 0, 1, "narrow console")

        def flush(self) -> None:
            pass

        @property
        def buffer(self):
            outer = self

            class B:
                def write(self, raw: bytes) -> int:
                    outer._data += raw
                    return len(raw)

                def flush(self) -> None:
                    pass

            return B()

    out = RaisingStream()
    safe_print("α-and-γ-Al2O3", file=out)
    text = out._data.decode("cp1252", errors="replace")
    assert "Al2O3" in text
    assert "?" in text  # Greek replaced
