"""CrossRef REST client (polite pool)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from pdf_organizer.config import CrossrefConfig


@dataclass
class CrossrefWork:
    doi: str | None = None
    title: str | None = None
    year: str | None = None
    first_author_last: str | None = None
    authors: str | None = None
    report_ids: str | None = None
    publisher: str | None = None
    work_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None  # crossref_error | crossref_not_found | None


def _year_from_date_parts(message: dict[str, Any]) -> str | None:
    for key in ("published-print", "published-online", "issued", "created"):
        block = message.get(key) or {}
        parts = block.get("date-parts") or []
        if parts and parts[0]:
            year = parts[0][0]
            if year:
                return str(year)
    return None


def _authors_from_message(message: dict[str, Any]) -> tuple[str | None, str | None]:
    authors = message.get("author") or []
    if not authors:
        return None, None
    labels: list[str] = []
    first_last: str | None = None
    for i, author in enumerate(authors):
        family = (author.get("family") or "").strip()
        given = (author.get("given") or "").strip()
        name = (author.get("name") or "").strip()
        if family:
            label = f"{family}, {given}".strip(", ") if given else family
            if first_last is None:
                first_last = family
        elif name:
            label = name
            if first_last is None:
                first_last = name
        else:
            continue
        labels.append(label)
        if i == 0 and first_last is None:
            first_last = label
    return first_last, "; ".join(labels) if labels else None


def _report_ids(message: dict[str, Any]) -> str | None:
    bits: list[str] = []
    alt = message.get("alternative-id")
    if isinstance(alt, list):
        bits.extend(str(x) for x in alt)
    elif alt:
        bits.append(str(alt))
    for key in ("ISBN", "ISSN"):
        vals = message.get(key)
        if isinstance(vals, list):
            bits.extend(str(x) for x in vals)
        elif vals:
            bits.append(str(vals))
    return "; ".join(bits) if bits else None


def parse_work(message: dict[str, Any]) -> CrossrefWork:
    titles = message.get("title") or []
    title = titles[0] if titles else None
    first_last, authors = _authors_from_message(message)
    return CrossrefWork(
        doi=message.get("DOI"),
        title=title,
        year=_year_from_date_parts(message),
        first_author_last=first_last,
        authors=authors,
        report_ids=_report_ids(message),
        publisher=message.get("publisher"),
        work_type=message.get("type"),
        raw=message,
    )


class CrossrefClient:
    def __init__(self, config: CrossrefConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=config.timeout_seconds,
            headers={
                "User-Agent": f"pdf-library-organizer/0.1 (mailto:{config.mailto})",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> CrossrefClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_work(self, doi: str) -> CrossrefWork:
        encoded = quote(doi.strip(), safe="")
        url = f"https://api.crossref.org/works/{encoded}"
        params = {"mailto": self.config.mailto}
        last_error: str | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last_error = f"crossref_error: {exc}"
                time.sleep(min(2**attempt, 8))
                continue

            if response.status_code == 404:
                return CrossrefWork(doi=doi, error="crossref_not_found")
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 2**attempt))
                time.sleep(min(retry_after, 30))
                last_error = "crossref_error: rate limited"
                continue
            if response.status_code >= 400:
                last_error = f"crossref_error: HTTP {response.status_code}"
                time.sleep(min(2**attempt, 8))
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                last_error = f"crossref_error: invalid JSON ({exc})"
                time.sleep(min(2**attempt, 8))
                continue

            message = payload.get("message") or {}
            return parse_work(message)

        return CrossrefWork(doi=doi, error=last_error or "crossref_error")
