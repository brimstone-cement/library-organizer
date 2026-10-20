"""DOI extraction and author parsing."""

from pdf_organizer.pdf_meta import (
    extract_doi_from_text,
    is_usable_author,
    normalize_doi,
    parse_first_author_last,
)


def test_parse_last_comma_first():
    assert parse_first_author_last("Smith, John") == "Smith"


def test_parse_first_last():
    assert parse_first_author_last("John Smith") == "Smith"


def test_parse_multi_author():
    assert parse_first_author_last("Smith, John; Jones, Amy") == "Smith"
    assert parse_first_author_last("John Smith and Amy Jones") == "Smith"


def test_normalize_doi():
    assert normalize_doi("doi:10.1234/foo.bar.") == "10.1234/foo.bar"


def test_doi_not_from_references_block():
    text = (
        "An important paper about cement.\n"
        "\n"
        "References\n"
        "1. Someone Else, 10.9999/cited-work\n"
    )
    assert extract_doi_from_text(text) is None


def test_doi_from_header_url():
    text = "Available at https://doi.org/10.1038/s41586-020-2649-2\nMore text\n"
    assert extract_doi_from_text(text) == "10.1038/s41586-020-2649-2"


def test_doi_before_references():
    text = (
        "Title here 10.5555/paper-doi and abstract.\n"
        "References\n"
        "10.9999/should-not-win\n"
    )
    assert extract_doi_from_text(text) == "10.5555/paper-doi"


def test_junk_utf16_administrator_mojibake():
    junk = "\x104<8=8AB@0B>@"
    assert is_usable_author(junk) is False


def test_junk_hex_token_and_administrator():
    assert is_usable_author("488AB0B") is False
    assert is_usable_author("Administrator") is False
    assert is_usable_author("Администратор") is False


def test_real_author_usable():
    assert is_usable_author("Smith, John") is True
    assert is_usable_author("Mel Pell") is True
    assert is_usable_author("Bongo-Njeng") is True


def test_extract_patent_id_hyphenated_and_wo():
    from pdf_organizer.pdf_meta import extract_patent_id

    assert extract_patent_id("US-3092450-A Preparation") == "US-3092450-A"
    assert extract_patent_id("US5019198 - Calcium") == "US5019198"
    assert extract_patent_id("WO1995033686A1 - Method") == "WO1995033686A1"
    assert extract_patent_id("USBOM - Bauer report") is None
    assert extract_patent_id("US_Import_Market_Analysis.pdf") is None
