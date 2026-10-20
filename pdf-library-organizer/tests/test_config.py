"""Config validation."""

import pytest
from pydantic import ValidationError

from pdf_organizer.config import CrossrefConfig


def test_mailto_rejects_example_com():
    with pytest.raises(ValidationError):
        CrossrefConfig(mailto="you@example.com")


def test_mailto_accepts_real_looking_address():
    cfg = CrossrefConfig(mailto="person@brimstone.energy")
    assert cfg.mailto == "person@brimstone.energy"
