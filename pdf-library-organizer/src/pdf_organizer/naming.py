"""
Filename builders — logic ported from 0_rename_EL.py (clean / short_title / doc_namer),
extended for SharePoint, Manual scheme, Unicode, and hash disambiguation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Config
BAD_CHARS_RE = re.compile(r'[\\/:*?"<>|#%]')
PUNCT_CHARS = ".,;:!?()[]{}'\""
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(10)),
    *(f"LPT{i}" for i in range(10)),
}

PLACEHOLDER_YEAR = "NoYear"
PLACEHOLDER_AUTHOR = "NoAuthor"
PLACEHOLDER_TITLE = "NoTitle"
PLACEHOLDER_PATENT = "NoPatent"
PLACEHOLDER_COMPANY = "NoCompany"

NAME_SPACER = "_"
TITLE_SPACER = "-"
N_TITLE_WORDS = 6
MAX_FILENAME_LENGTH = 150


def clean(text: str) -> str:
    """Strip characters rejected in Windows/SharePoint filenames, collapse whitespace."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = BAD_CHARS_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def short_title(
    title: str,
    *,
    n_words: int = N_TITLE_WORDS,
    title_spacer: str = TITLE_SPACER,
) -> str:
    """Condense title into the first n words, lowercased."""
    ctitle = clean(title).lower()
    title_words = ctitle.split(" ")
    small_title = title_words[:n_words]
    small_ctitle = []
    for w in small_title:
        small_ctitle.append(w.strip(PUNCT_CHARS))
    small_ctitle = [w for w in small_ctitle if w]
    if small_ctitle:
        return title_spacer.join(small_ctitle)
    return PLACEHOLDER_TITLE


def sanitize_token(text: str, *, title_spacer: str = TITLE_SPACER) -> str:
    """Author/company-style token: clean, spaces to hyphens, keep alnum/hyphen."""
    text = clean(text).replace(" ", title_spacer)
    text = re.sub(r"[^A-Za-z0-9\-]+", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or PLACEHOLDER_AUTHOR


def sanitize_author_token(text: str, *, title_spacer: str = TITLE_SPACER) -> str:
    """Like sanitize_token, but prefer NoAuthor over numeric/hex ID debris."""
    token = sanitize_token(text, title_spacer=title_spacer)
    if token == PLACEHOLDER_AUTHOR:
        return token
    core = token.replace("-", "")
    letters = sum(1 for c in core if c.isalpha())
    digits = sum(1 for c in core if c.isdigit())
    if letters == 0:
        return PLACEHOLDER_AUTHOR
    if digits and re.fullmatch(r"[0-9A-Fa-f]+", core):
        return PLACEHOLDER_AUTHOR
    return token


def sanitize_patent_id(patent_id: str) -> str:
    """US 10,123,456 -> US10123456; WO 2024/123456 -> WO2024-123456."""
    text = unicodedata.normalize("NFKD", str(patent_id))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(",", "").replace(" ", "")
    text = text.replace("/", "-")
    text = BAD_CHARS_RE.sub("", text)
    text = re.sub(r"[^A-Za-z0-9\-]+", "", text)
    return text or PLACEHOLDER_PATENT


def _trim_stem(stem: str, max_length: int) -> str:
    """Keep stem under max_length (filename without .pdf)."""
    if len(stem) <= max_length:
        return stem
    return stem[:max_length].rstrip("._-")


def _avoid_reserved(stem: str) -> str:
    first = stem.split(NAME_SPACER, 1)[0].upper()
    if first in RESERVED_NAMES or stem.upper() in RESERVED_NAMES:
        return f"X{NAME_SPACER}{stem}"
    return stem


@dataclass
class NameParts:
    year: str
    author: str
    title: str
    file_type: str  # article | report | book | patent | manual
    patent_id: str | None = None
    company: str | None = None


def build_stem(
    parts: NameParts,
    *,
    n_title_words: int = N_TITLE_WORDS,
    name_spacer: str = NAME_SPACER,
    title_spacer: str = TITLE_SPACER,
    max_filename_length: int = MAX_FILENAME_LENGTH,
) -> str:
    """
    Build filename stem (no .pdf):
    - article/report/book: Year_Author_title
    - patent: PatentID_Year_Author_title
    - manual: Manual_Company_title
    """
    year = parts.year.strip() if parts.year else PLACEHOLDER_YEAR
    author = (
        sanitize_author_token(parts.author, title_spacer=title_spacer)
        if parts.author
        else PLACEHOLDER_AUTHOR
    )
    title = (
        short_title(parts.title, n_words=n_title_words, title_spacer=title_spacer)
        if parts.title
        else PLACEHOLDER_TITLE
    )

    ftype = (parts.file_type or "article").lower().strip()
    if ftype == "patent":
        patent = sanitize_patent_id(parts.patent_id or PLACEHOLDER_PATENT)
        chunks = [patent, year, author, title]
    elif ftype == "manual":
        company = (
            sanitize_token(parts.company, title_spacer=title_spacer)
            if parts.company
            else PLACEHOLDER_COMPANY
        )
        chunks = ["Manual", company, title]
    else:
        chunks = [year, author, title]

    stem = name_spacer.join(chunks)
    stem = stem.strip(" .")
    # max length is for full filename including .pdf
    max_stem = max_filename_length - 4
    stem = _trim_stem(stem, max_stem)
    stem = _avoid_reserved(stem)
    return stem


def build_filename(parts: NameParts, **kwargs) -> str:
    return f"{build_stem(parts, **kwargs)}.pdf"


def with_hash_suffix(filename: str, file_hash: str, *, name_spacer: str = NAME_SPACER) -> str:
    """Append _abcdef before .pdf for name disambiguation / insufficient metadata."""
    digest = (file_hash or "000000")[:6].lower()
    if filename.lower().endswith(".pdf"):
        stem = filename[:-4]
        return f"{stem}{name_spacer}{digest}.pdf"
    return f"{filename}{name_spacer}{digest}"
