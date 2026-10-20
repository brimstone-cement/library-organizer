"""Repository index for duplicate detection (hash / DOI / name)."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

INDEX_FIELDS = ["path", "name", "size", "mtime", "sha256", "doi"]


@dataclass
class RepoEntry:
    path: Path
    name: str
    size: int
    mtime: float
    sha256: str
    doi: str = ""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class RepoIndex:
    def __init__(self) -> None:
        self.by_hash: dict[str, RepoEntry] = {}
        self.by_doi: dict[str, RepoEntry] = {}
        self.by_name_lower: dict[str, RepoEntry] = {}
        self.entries: list[RepoEntry] = []

    def add(self, entry: RepoEntry) -> None:
        self.entries.append(entry)
        self.by_hash[entry.sha256] = entry
        self.by_name_lower[entry.name.lower()] = entry
        if entry.doi:
            self.by_doi[entry.doi.lower()] = entry

    def has_hash(self, file_hash: str) -> RepoEntry | None:
        return self.by_hash.get(file_hash)

    def has_doi(self, doi: str | None) -> RepoEntry | None:
        if not doi:
            return None
        return self.by_doi.get(doi.lower())

    def has_name(self, name: str) -> RepoEntry | None:
        return self.by_name_lower.get(name.lower())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
            writer.writeheader()
            for entry in self.entries:
                writer.writerow(
                    {
                        "path": str(entry.path),
                        "name": entry.name,
                        "size": entry.size,
                        "mtime": f"{entry.mtime:.6f}",
                        "sha256": entry.sha256,
                        "doi": entry.doi,
                    }
                )


def _load_cached(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    cached: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = row.get("path") or ""
            if key:
                cached[key] = row
    return cached


def _doi_from_process_log(log_path: Path) -> dict[str, str]:
    """Map sha256 -> doi from prior successful log rows."""
    if not log_path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        with log_path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("status") != "renamed_moved":
                    continue
                h = (row.get("file_hash") or "").strip()
                doi = (row.get("doi") or "").strip()
                if h and doi:
                    out[h] = doi
    except OSError:
        return {}
    return out


def build_repo_index(
    repository_dir: Path,
    index_path: Path,
    process_log_path: Path | None = None,
    *,
    extract_doi_fn=None,
    progress_every: int = 25,
    quiet: bool = False,
) -> RepoIndex:
    """Refresh index from repository/; reuse hash when size+mtime unchanged."""
    cached = _load_cached(index_path)
    hash_to_doi = _doi_from_process_log(process_log_path) if process_log_path else {}
    index = RepoIndex()
    if not repository_dir.is_dir():
        return index

    pdfs = sorted(repository_dir.glob("*.pdf"))
    total = len(pdfs)
    if total and not quiet:
        print(f"Indexing {total} PDF(s) in repository...")

    for i, pdf in enumerate(pdfs, start=1):
        if (
            not quiet
            and progress_every
            and (i == 1 or i % progress_every == 0 or i == total)
        ):
            print(f"  indexed {i}/{total}: {pdf.name}")
        try:
            stat = pdf.stat()
        except OSError:
            continue
        key = str(pdf.resolve()) if pdf.exists() else str(pdf)
        # Prefer stable string path as stored previously
        prior = cached.get(str(pdf)) or cached.get(key)
        reuse = (
            prior
            and prior.get("size") == str(stat.st_size)
            and abs(float(prior.get("mtime") or 0) - stat.st_mtime) < 0.001
            and prior.get("sha256")
        )
        if reuse:
            file_hash = prior["sha256"]
            doi = prior.get("doi") or hash_to_doi.get(file_hash, "")
        else:
            try:
                file_hash = sha256_file(pdf)
            except OSError:
                continue
            doi = hash_to_doi.get(file_hash, "")
            if not doi and extract_doi_fn is not None:
                try:
                    fields = extract_doi_fn(pdf)
                    doi = getattr(fields, "doi", None) or ""
                except Exception:  # noqa: BLE001
                    doi = ""

        index.add(
            RepoEntry(
                path=pdf,
                name=pdf.name,
                size=stat.st_size,
                mtime=stat.st_mtime,
                sha256=file_hash,
                doi=doi or "",
            )
        )
    return index


def build_repo_index_light(
    repository_dir: Path,
    index_path: Path,
    process_log_path: Path | None = None,
) -> RepoIndex:
    """
    Fast index for Script 2: reuse cache + log DOIs; no PDF text extraction.
    Rehashes only when size/mtime changed.
    """
    return build_repo_index(
        repository_dir,
        index_path,
        process_log_path,
        extract_doi_fn=None,
        progress_every=0,
        quiet=True,
    )
