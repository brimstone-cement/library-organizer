"""PDF metadata and conservative DOI / patent extraction."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
DOI_URL_RE = re.compile(
    r"(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)
PATENT_RE = re.compile(
    r"\b(?:US|USPTO)[-\s]*[0-9,]{7,12}(?:[-\s]?[A-Z]\d?)?\b"
    r"|\bEP[-\s]*\d{7,}(?:[-\s]?[A-Z]\d?)?\b"
    r"|\bWO\s*\d{4}/\d+\b"
    r"|\bWO\d{7,}[A-Z]?\d?\b",
    re.IGNORECASE,
)
REF_HEADING_RE = re.compile(
    r"^(?:\s*)(references|bibliography|works cited)\b",
    re.IGNORECASE | re.MULTILINE,
)

# PDF /Author junk (OS account names, placeholders, encoding debris).
_AUTHOR_BLOCKLIST = frozenset(
    {
        "admin",
        "administrator",
        "anonymous",
        "author",
        "microsoft",
        "microsoft word",
        "unknown",
        "untitled",
        "user",
        "администратор",
    }
)
_CTRL_OR_JUNK_PUNCT_RE = re.compile(r"[\x00-\x1f]|[<>@=]")
_HEX_ID_TOKEN_RE = re.compile(r"^[0-9A-Fa-f]+$")


@dataclass
class PdfFields:
    title: str | None = None
    author_raw: str | None = None
    first_author_last: str | None = None
    year: str | None = None
    doi: str | None = None
    patent_id: str | None = None
    page1_text: str = ""
    error: str | None = None
    flags: list[str] = field(default_factory=list)


def normalize_doi(raw: str) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().rstrip(".,;:)")
    match = DOI_RE.search(text)
    if not match:
        return None
    doi = match.group(0).rstrip(".,;:)")
    return doi


def _normalize_author_key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _utf16_low_byte_decode(text: str) -> str | None:
    """Rebuild Cyrillic when UTF-16BE high bytes (0x04) were dropped from /Author."""
    if not text or any(ord(c) > 0xFF for c in text):
        return None
    decoded = "".join(chr(0x0400 | ord(c)) for c in text)
    if not any("\u0400" <= ch <= "\u04FF" for ch in decoded):
        return None
    return decoded


def is_usable_author(author: str | None) -> bool:
    """False for empty, control/mojibake, blocklisted, or numeric/hex-like tokens."""
    if not author or not str(author).strip():
        return False
    text = str(author).strip()
    if _CTRL_OR_JUNK_PUNCT_RE.search(text):
        return False
    for candidate in (text, _utf16_low_byte_decode(text) or ""):
        if not candidate:
            continue
        key = _normalize_author_key(candidate)
        if key in _AUTHOR_BLOCKLIST:
            return False
        first = key.split(",", 1)[0].strip()
        if first in _AUTHOR_BLOCKLIST:
            return False
    alnum = re.sub(r"[^A-Za-z0-9]+", "", text)
    if not alnum:
        return False
    letters = sum(1 for c in alnum if c.isalpha())
    digits = sum(1 for c in alnum if c.isdigit())
    if letters == 0:
        return False
    if digits and _HEX_ID_TOKEN_RE.fullmatch(alnum):
        return False
    return True


def parse_first_author_last(author: str | None) -> str | None:
    """Parse 'Last, First' or 'First Last'; take first name if multi-author."""
    if not author:
        return None
    text = author.strip()
    if not text:
        return None
    # Split multi-author
    for sep in (";", " and ", " & "):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    if "," in text:
        last = text.split(",", 1)[0].strip()
        return last or None
    parts = text.split()
    if not parts:
        return None
    return parts[-1]


def _text_before_references(text: str) -> str:
    match = REF_HEADING_RE.search(text)
    if match:
        return text[: match.start()]
    return text


def extract_doi_from_text(page1_text: str) -> str | None:
    """Prefer doi.org URLs near the top, then DOI regex before References."""
    if not page1_text:
        return None
    searchable = _text_before_references(page1_text)
    header = searchable[:2500]
    url_match = DOI_URL_RE.search(header)
    if url_match:
        return normalize_doi(url_match.group(1))

    match = DOI_RE.search(header) or DOI_RE.search(searchable)
    if match:
        return normalize_doi(match.group(0))
    return None


def extract_patent_id(text: str) -> str | None:
    if not text:
        return None
    match = PATENT_RE.search(text[:5000])
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(0)).strip()


def extract_pdf_fields(path: Path) -> PdfFields:
    result = PdfFields()
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as exc:  # noqa: BLE001 — surface as unreadable
        result.error = f"unreadable_pdf: {exc}"
        return result

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            result.error = f"unreadable_pdf: encrypted ({exc})"
            return result

    meta = reader.metadata
    if meta:
        def _meta_get(attr: str, key: str) -> str | None:
            value = getattr(meta, attr, None)
            if value:
                return str(value).strip() or None
            if hasattr(meta, "get"):
                raw = meta.get(key)
                if raw:
                    return str(raw).strip() or None
            return None

        title = _meta_get("title", "/Title")
        author = _meta_get("author", "/Author")
        subject = _meta_get("subject", "/Subject")
        if title:
            result.title = title
        if author:
            result.author_raw = author
            if is_usable_author(author):
                result.first_author_last = parse_first_author_last(author)
            else:
                result.flags.append("junk_pdf_author")
        # Do not use /CreationDate or /ModDate for bibliographic year — those are
        # often scan/upload times, not publication year. Year comes from CrossRef
        # (DOI) or user hints; otherwise naming uses NoYear.
        for blob in (subject, title):
            if blob and not result.doi:
                result.doi = normalize_doi(str(blob)) or extract_doi_from_text(str(blob))

    page1_text = ""
    try:
        if reader.pages:
            page1_text = reader.pages[0].extract_text() or ""
    except Exception:  # noqa: BLE001
        page1_text = ""
    result.page1_text = page1_text

    if not result.doi:
        result.doi = extract_doi_from_text(page1_text)

    result.patent_id = (
        extract_patent_id(page1_text)
        or extract_patent_id(" ".join(filter(None, [result.title, result.author_raw])))
        or extract_patent_id(path.name)
    )
    return result
