"""Tests for naming helpers."""

from pdf_organizer.naming import (
    PLACEHOLDER_AUTHOR,
    PLACEHOLDER_TITLE,
    NameParts,
    build_filename,
    clean,
    short_title,
    sanitize_author_token,
    sanitize_patent_id,
    with_hash_suffix,
)


def test_clean_strips_windows_and_sharepoint_chars():
    assert clean('a/b:c*d?e"f<g>h|i#j%k') == "abcdefghijk"


def test_short_title_first_six_words():
    title = "The Quick Brown Fox Jumps Over The Lazy Dog"
    assert short_title(title) == "the-quick-brown-fox-jumps-over"


def test_short_title_strips_punctuation():
    assert short_title("Hello, world! (again)") == "hello-world-again"


def test_short_title_empty():
    assert short_title("...") == PLACEHOLDER_TITLE


def test_article_filename():
    name = build_filename(
        NameParts(year="2020", author="Smith", title="Climate Change Impacts on Cement", file_type="article")
    )
    assert name == "2020_Smith_climate-change-impacts-on-cement.pdf"


def test_patent_filename():
    name = build_filename(
        NameParts(
            year="2019",
            author="Doe",
            title="Novel Binder Composition",
            file_type="patent",
            patent_id="US 10,123,456",
        )
    )
    assert name.startswith("US10123456_2019_Doe_")
    assert name.endswith(".pdf")


def test_manual_filename():
    name = build_filename(
        NameParts(
            year="2020",
            author="X",
            title="Installation Guide for Unit",
            file_type="manual",
            company="Acme Corp",
        )
    )
    assert name == "Manual_Acme-Corp_installation-guide-for-unit.pdf"


def test_sanitize_patent_id_wo():
    assert sanitize_patent_id("WO 2024/123456") == "WO2024-123456"


def test_hash_suffix():
    assert with_hash_suffix("2020_Smith_title.pdf", "abcdef1234") == "2020_Smith_title_abcdef.pdf"


def test_sanitize_author_prefers_noauthor_over_hex():
    assert sanitize_author_token("\x104<8=8AB@0B>@") == PLACEHOLDER_AUTHOR
    assert sanitize_author_token("488AB0B") == PLACEHOLDER_AUTHOR


def test_build_filename_junk_author_becomes_noauthor():
    name = build_filename(
        NameParts(
            year="NoYear",
            author="\x104<8=8AB@0B>@",
            title="NoTitle",
            file_type="article",
        )
    )
    assert name == "NoYear_NoAuthor_notitle.pdf"
