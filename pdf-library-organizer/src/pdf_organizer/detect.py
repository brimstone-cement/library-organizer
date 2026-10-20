"""Detect-from-PDF prefill for Script 2 (no file moves)."""

from __future__ import annotations

from dataclasses import dataclass, field

from pdf_organizer.crossref import CrossrefClient
from pdf_organizer.hints import MetadataHints
from pdf_organizer.naming import PLACEHOLDER_AUTHOR, PLACEHOLDER_TITLE, PLACEHOLDER_YEAR
from pdf_organizer.pdf_meta import extract_pdf_fields
from pdf_organizer.pipeline import merge_metadata, resolve_file_type


@dataclass
class DetectResult:
    hints: MetadataHints
    flags: list[str] = field(default_factory=list)
    error: str | None = None
    message: str = ""


def detect_prefill(pdf_path, client: CrossrefClient) -> DetectResult:
    """
    Extract PDF metadata and optionally query CrossRef.
    Returns suggested form field values — does not move the file.
    """
    pdf = extract_pdf_fields(pdf_path)
    if pdf.error:
        return DetectResult(hints=MetadataHints(), error=pdf.error, message=pdf.error)

    work = None
    flags = list(pdf.flags)
    if pdf.doi:
        work = client.fetch_work(pdf.doi)
        if work.error:
            flags.append(work.error)

    meta = merge_metadata(MetadataHints(), pdf, work)
    file_type = resolve_file_type(MetadataHints(), work, pdf)

    def _or_none(value: str, placeholder: str) -> str | None:
        text = (value or "").strip()
        if not text or text == placeholder:
            return None
        return text

    hints = MetadataHints(
        doi=_or_none(meta.doi, ""),
        year=_or_none(meta.year, PLACEHOLDER_YEAR),
        authors=_or_none(meta.authors, PLACEHOLDER_AUTHOR),
        title=_or_none(meta.title, PLACEHOLDER_TITLE),
        report_ids=_or_none(meta.report_ids, ""),
        patent_id=_or_none(meta.patent_id, ""),
        company=_or_none(meta.company, ""),
        file_type=file_type if file_type not in ("", "article") else None,
    )
    msg_parts = []
    if pdf.doi:
        msg_parts.append(f"DOI {pdf.doi}")
    if work and not work.error:
        msg_parts.append("CrossRef OK")
    elif work and work.error:
        msg_parts.append(work.error)
    if not msg_parts:
        msg_parts.append("PDF fields only (no DOI)")

    return DetectResult(
        hints=hints,
        flags=flags + [f for f in meta.flags if f not in flags],
        message="; ".join(msg_parts),
    )
