"""Merge precedence for empty hints (Script 1 path)."""

from pdf_organizer.crossref import CrossrefWork
from pdf_organizer.hints import MetadataHints
from pdf_organizer.pdf_meta import PdfFields
from pdf_organizer.pipeline import merge_metadata


def test_empty_hints_prefer_crossref_over_pdf():
    pdf = PdfFields(title="PDF Title", first_author_last="PdfAuthor", year="1999", doi="10.1/x")
    work = CrossrefWork(
        doi="10.1/x",
        title="Crossref Title About Cement Chemistry",
        year="2021",
        first_author_last="Cross",
        authors="Cross, A",
    )
    meta = merge_metadata(MetadataHints(), pdf, work)
    assert meta.year == "2021"
    assert meta.first_author == "Cross"
    assert meta.title == "Crossref Title About Cement Chemistry"
    assert meta.metadata_source in {"crossref", "mixed"}


def test_hint_title_beats_crossref():
    pdf = PdfFields()
    work = CrossrefWork(title="From Crossref", year="2020", first_author_last="A")
    meta = merge_metadata(MetadataHints(title="User Title Here"), pdf, work)
    assert meta.title == "User Title Here"


def test_placeholders_when_nothing():
    meta = merge_metadata(MetadataHints(), PdfFields(), None)
    assert meta.year == "NoYear"
    assert meta.first_author == "NoAuthor"
    assert meta.title == "NoTitle"
    assert "insufficient_metadata" in meta.flags


def test_pdf_creation_year_ignored_without_crossref_or_hint():
    pdf = PdfFields(
        title="Only PDF",
        first_author_last="Smith",
        year="2010",  # would formerly come from /CreationDate
    )
    meta = merge_metadata(MetadataHints(), pdf, None)
    assert meta.year == "NoYear"
    assert "year_from_pdf_dates" not in meta.flags


def test_hint_year_used_when_no_crossref():
    pdf = PdfFields(title="Only PDF", first_author_last="Smith")
    meta = merge_metadata(MetadataHints(year="1990"), pdf, None)
    assert meta.year == "1990"


def test_crossref_year_preferred_over_stale_pdf_year():
    pdf = PdfFields(
        title="PDF Title",
        first_author_last="PdfAuthor",
        year="1999",
    )
    work = CrossrefWork(
        doi="10.1/x",
        title="Crossref Title",
        year="2021",
        first_author_last="Cross",
        authors="Cross, A",
    )
    meta = merge_metadata(MetadataHints(), pdf, work)
    assert meta.year == "2021"
    assert "year_from_pdf_dates" not in meta.flags


def test_pdf_patent_number_sets_patent_type():
    pdf = PdfFields(
        title="Process for making anhydrous magnesium chloride",
        first_author_last="Smith",
        year="1996",
        patent_id="US 5,514,359",
    )
    meta = merge_metadata(MetadataHints(), pdf, None)
    assert meta.file_type == "patent"
    assert meta.patent_id.startswith("US")


def test_crossref_patent_type_sets_patent():
    pdf = PdfFields(title="Something", first_author_last="Doe", year="2019")
    work = CrossrefWork(title="A Patent", year="2019", first_author_last="Doe", work_type="patent")
    meta = merge_metadata(MetadataHints(), pdf, work)
    assert meta.file_type == "patent"


def test_hint_patent_id_sets_patent_type():
    pdf = PdfFields(title="Something", first_author_last="Doe", year="2019")
    meta = merge_metadata(MetadataHints(patent_id="EP1234567"), pdf, None)
    assert meta.file_type == "patent"


def test_junk_pdf_author_becomes_noauthor():
    pdf = PdfFields(
        title="Gas Fluidization",
        author_raw="\x104<8=8AB@0B>@",
        first_author_last=None,
        flags=["junk_pdf_author"],
    )
    meta = merge_metadata(MetadataHints(), pdf, None)
    assert meta.first_author == "NoAuthor"
    assert meta.authors == ""
