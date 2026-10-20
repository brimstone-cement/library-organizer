"""Skip log gate suppresses unchanged skips."""

from pdf_organizer.skip_gate import SkipLogGate


def test_skip_gate_logs_once_for_same_mtime(tmp_path):
    gate = SkipLogGate(tmp_path / "skip_state.csv")
    assert gate.should_log("a.pdf", 1.0, 10, "skipped_in_use") is True
    assert gate.should_log("a.pdf", 1.0, 10, "skipped_in_use") is False
    assert gate.should_log("a.pdf", 2.0, 10, "skipped_in_use") is True
    gate.save()
    gate2 = SkipLogGate(tmp_path / "skip_state.csv")
    assert gate2.should_log("a.pdf", 2.0, 10, "skipped_in_use") is False
