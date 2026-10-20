"""Shared process pipeline for Script 1 (empty hints) and Script 2 (form hints)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from pdf_organizer.config import AppConfig
from pdf_organizer.crossref import CrossrefClient, CrossrefWork
from pdf_organizer.duplicates import RepoEntry, RepoIndex, sha256_file
from pdf_organizer.fsutil import safe_move
from pdf_organizer.hints import MetadataHints
from pdf_organizer.log import LogRow, ProcessLog
from pdf_organizer.naming import (
    PLACEHOLDER_AUTHOR,
    PLACEHOLDER_COMPANY,
    PLACEHOLDER_PATENT,
    PLACEHOLDER_TITLE,
    PLACEHOLDER_YEAR,
    NameParts,
    build_filename,
    with_hash_suffix,
)
from pdf_organizer.pdf_meta import (
    PdfFields,
    extract_pdf_fields,
    is_usable_author,
    parse_first_author_last,
)
from pdf_organizer.skip_gate import SkipLogGate


@dataclass
class ResolvedMeta:
    year: str = PLACEHOLDER_YEAR
    authors: str = ""
    first_author: str = PLACEHOLDER_AUTHOR
    title: str = PLACEHOLDER_TITLE
    report_ids: str = ""
    doi: str = ""
    patent_id: str = ""
    company: str = ""
    file_type: str = "article"
    metadata_source: str = "placeholder"
    flags: list[str] = field(default_factory=list)


@dataclass
class ProcessResult:
    status: str
    source_path: Path
    dest_path: Path | None = None
    dest_name: str = ""
    meta: ResolvedMeta | None = None
    file_hash: str = ""
    error_message: str = ""
    flags: list[str] = field(default_factory=list)


def _is_cloud_placeholder(path: Path) -> bool:
    """Best-effort OneDrive placeholder detection on Windows."""
    if path.stat().st_size == 0:
        return True
    try:
        import ctypes

        FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
        FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        attrs = GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(attrs & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN))
    except Exception:  # noqa: BLE001
        return False


def should_skip_file(path: Path, settle_seconds: float) -> str | None:
    """Return skip status reason, or None if OK to process."""
    name = path.name
    if name.startswith("~$"):
        return "skipped_in_use"
    try:
        stat = path.stat()
    except OSError:
        return "skipped_in_use"
    if stat.st_size == 0:
        return "skipped_in_use"
    age = time.time() - stat.st_mtime
    if age < settle_seconds:
        return "skipped_in_use"
    if _is_cloud_placeholder(path):
        return "skipped_in_use"
    return None


def _pick(
    hint: str | None,
    crossref: str | None = None,
    pdf: str | None = None,
    placeholder: str | None = None,
) -> tuple[str, str]:
    """Return (value, source) for hint > crossref > pdf > placeholder."""
    if hint and str(hint).strip():
        return str(hint).strip(), "user"
    if crossref and str(crossref).strip():
        return str(crossref).strip(), "crossref"
    if pdf and str(pdf).strip():
        return str(pdf).strip(), "pdf"
    if placeholder is not None and str(placeholder):
        return str(placeholder), "placeholder"
    return "", "placeholder"


def resolve_file_type(
    hints: MetadataHints,
    work: CrossrefWork | None,
    pdf: PdfFields,
) -> str:
    """
    File type for naming.

    Patents: form/hint type, hint patent_id, CrossRef type == patent, or a
    patent ID found on page 1 / PDF metadata / filename (Script 1 path).
    """
    if hints.file_type and hints.file_type.strip():
        return hints.file_type.strip().lower()
    if work and not work.error and work.work_type == "patent":
        return "patent"
    if hints.patent_id and hints.patent_id.strip():
        return "patent"
    if pdf.patent_id and str(pdf.patent_id).strip():
        return "patent"
    return "article"


def merge_metadata(
    hints: MetadataHints,
    pdf: PdfFields,
    work: CrossrefWork | None,
) -> ResolvedMeta:
    sources: set[str] = set()
    flags = list(pdf.flags)

    cr_year = work.year if work and not work.error else None
    cr_author = work.first_author_last if work and not work.error else None
    cr_authors = work.authors if work and not work.error else None
    cr_title = work.title if work and not work.error else None
    cr_report = work.report_ids if work and not work.error else None
    cr_publisher = work.publisher if work and not work.error else None
    cr_doi = work.doi if work and work.doi else None

    # Publication year only: user hint or CrossRef. Never PDF Creation/ModDate.
    year, src = _pick(hints.year, cr_year, None, PLACEHOLDER_YEAR)
    sources.add(src)

    authors_hint = hints.authors
    if authors_hint and authors_hint.strip():
        authors = authors_hint.strip()
        first_author = parse_first_author_last(authors) or authors.split()[0]
        if not is_usable_author(first_author):
            first_author = PLACEHOLDER_AUTHOR
            authors = ""
        else:
            sources.add("user")
    else:
        pdf_author = pdf.first_author_last if is_usable_author(pdf.first_author_last) else None
        first_author, src = _pick(None, cr_author, pdf_author, PLACEHOLDER_AUTHOR)
        if first_author != PLACEHOLDER_AUTHOR and not is_usable_author(first_author):
            first_author, src = PLACEHOLDER_AUTHOR, "placeholder"
        sources.add(src)
        pdf_authors = pdf.author_raw if is_usable_author(pdf.author_raw) else None
        authors = cr_authors or pdf_authors or first_author
        if first_author == PLACEHOLDER_AUTHOR:
            authors = ""

    title, src = _pick(hints.title, cr_title, pdf.title, PLACEHOLDER_TITLE)
    sources.add(src)
    if not title:
        title = PLACEHOLDER_TITLE

    report_ids, src = _pick(hints.report_ids, cr_report, None, "")
    if report_ids:
        sources.add(src)

    patent_id, src = _pick(hints.patent_id, None, pdf.patent_id, "")
    if patent_id:
        sources.add(src)

    company, src = _pick(hints.company, cr_publisher, None, "")
    if company:
        sources.add(src)

    doi, src = _pick(hints.doi, None, pdf.doi, "")
    if doi:
        sources.add(src)
        if cr_doi:
            doi = cr_doi
    elif cr_doi:
        doi = cr_doi
        sources.add("crossref")

    file_type = resolve_file_type(hints, work, pdf)
    if hints.file_type and hints.file_type.strip():
        sources.add("user")

    if work and work.error:
        flags.append(work.error)

    if year == PLACEHOLDER_YEAR and first_author == PLACEHOLDER_AUTHOR and title == PLACEHOLDER_TITLE:
        flags.append("insufficient_metadata")

    meaningful = {s for s in sources if s}
    if meaningful <= {"placeholder"}:
        metadata_source = "placeholder"
    elif meaningful == {"user"}:
        metadata_source = "user"
    elif meaningful == {"crossref"}:
        metadata_source = "crossref"
    elif meaningful == {"pdf"}:
        metadata_source = "pdf"
    else:
        metadata_source = "mixed"

    return ResolvedMeta(
        year=year or PLACEHOLDER_YEAR,
        authors=authors or "",
        first_author=first_author or PLACEHOLDER_AUTHOR,
        title=title or PLACEHOLDER_TITLE,
        report_ids=report_ids or "",
        doi=doi or "",
        patent_id=patent_id or "",
        company=company or "",
        file_type=file_type,
        metadata_source=metadata_source,
        flags=flags,
    )


def _unique_dest_name(
    directory: Path,
    name: str,
    file_hash: str,
    *,
    name_spacer: str = "_",
) -> tuple[str, bool]:
    """Return a filename that does not already exist on disk in directory."""
    disambiguated = False
    candidate = name
    for attempt in range(8):
        dest = directory / candidate
        if not dest.exists():
            return candidate, disambiguated
        salt = hashlib.sha256(f"{file_hash}:{attempt}:{name}".encode()).hexdigest()
        candidate = with_hash_suffix(name, salt, name_spacer=name_spacer)
        disambiguated = True
    return candidate, True


def _unique_duplicates_name(duplicates_dir: Path, name: str, file_hash: str) -> str:
    name, _ = _unique_dest_name(duplicates_dir, name, file_hash)
    return name


def _try_move(src: Path, dest: Path, *, dry_run: bool) -> tuple[Path | None, str, str]:
    """
    Attempt safe_move. Returns (dest_or_none, status_on_failure_or_empty, error_message).
    On success: (dest, "", "").
    """
    if dry_run:
        return dest, "", ""
    try:
        safe_move(src, dest)
        return dest, "", ""
    except FileExistsError as exc:
        return None, "move_error", f"refusing to overwrite existing file: {exc}"
    except PermissionError as exc:
        return None, "move_error", f"permission denied, file may be open ({exc})"
    except OSError as exc:
        return None, "move_error", str(exc)


def process_one(
    path: Path,
    *,
    config: AppConfig,
    index: RepoIndex,
    log: ProcessLog,
    client: CrossrefClient,
    hints: MetadataHints | None = None,
    script: str = "import",
    dry_run: bool = False,
    skip_gate: SkipLogGate | None = None,
) -> ProcessResult:
    hints = hints or MetadataHints()
    source_name = path.name

    skip = should_skip_file(path, config.settle_seconds)
    if skip:
        try:
            st = path.stat()
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            mtime, size = 0.0, 0
        if skip_gate is None or skip_gate.should_log(source_name, mtime, size, skip):
            log.append(
                LogRow(
                    script=script,
                    source_path=str(path),
                    source_name=source_name,
                    status=skip,
                )
            )
        return ProcessResult(status=skip, source_path=path)

    try:
        file_hash = sha256_file(path)
    except PermissionError as exc:
        log.append(
            LogRow(
                script=script,
                source_path=str(path),
                source_name=source_name,
                status="skipped_in_use",
                error_message=str(exc),
            )
        )
        return ProcessResult(status="skipped_in_use", source_path=path, error_message=str(exc))
    except OSError as exc:
        log.append(
            LogRow(
                script=script,
                source_path=str(path),
                source_name=source_name,
                status="skipped_in_use",
                error_message=str(exc),
            )
        )
        return ProcessResult(status="skipped_in_use", source_path=path, error_message=str(exc))

    existing = index.has_hash(file_hash)
    if existing:
        dest_name = _unique_duplicates_name(config.duplicates_dir, source_name, file_hash)
        dest = config.duplicates_dir / dest_name
        status = "duplicate_content"
        moved, fail_status, msg = _try_move(path, dest, dry_run=dry_run)
        if fail_status:
            status = fail_status
            dest = None
        log.append(
            LogRow(
                script=script,
                source_path=str(path),
                source_name=source_name,
                dest_name=dest_name,
                dest_path=str(moved) if moved else "",
                status=status,
                error_message=msg,
                file_hash=file_hash,
                error_flags="duplicate_content",
            )
        )
        if skip_gate and status == "duplicate_content":
            skip_gate.clear(source_name)
        return ProcessResult(
            status=status,
            source_path=path,
            dest_path=moved,
            dest_name=dest_name,
            file_hash=file_hash,
            error_message=msg,
            flags=["duplicate_content"],
        )

    pdf = extract_pdf_fields(path)
    if pdf.error:
        dest_name = _unique_duplicates_name(config.failed_dir, source_name, file_hash)
        dest = config.failed_dir / dest_name
        moved, fail_status, msg = _try_move(path, dest, dry_run=dry_run)
        if fail_status:
            move_status = fail_status
            err = f"{pdf.error}; {msg}" if msg else pdf.error
            moved = None
        else:
            move_status = "unreadable_pdf"
            err = pdf.error
        log.append(
            LogRow(
                script=script,
                source_path=str(path),
                source_name=source_name,
                dest_name=dest_name if moved or dry_run else "",
                dest_path=str(moved) if moved else (str(dest) if dry_run else ""),
                status=move_status,
                error_message=err,
                file_hash=file_hash,
            )
        )
        return ProcessResult(
            status=move_status,
            source_path=path,
            dest_path=moved if moved else (dest if dry_run else None),
            dest_name=dest_name,
            file_hash=file_hash,
            error_message=err,
        )

    doi_for_lookup = (hints.doi or "").strip() or (pdf.doi or "")
    work: CrossrefWork | None = None
    if doi_for_lookup:
        work = client.fetch_work(doi_for_lookup)

    meta = merge_metadata(hints, pdf, work)

    if meta.doi:
        hit = index.has_doi(meta.doi)
        if hit and hit.sha256 != file_hash:
            dest_name = _unique_duplicates_name(config.duplicates_dir, source_name, file_hash)
            dest = config.duplicates_dir / dest_name
            status = "duplicate_doi"
            moved, fail_status, msg = _try_move(path, dest, dry_run=dry_run)
            if fail_status:
                status = fail_status
                moved = None
            else:
                msg = f"DOI {meta.doi} already in repository as {hit.name}"
            flags = meta.flags + ["duplicate_doi"]
            log.append(
                LogRow(
                    script=script,
                    source_path=str(path),
                    source_name=source_name,
                    dest_name=dest_name,
                    dest_path=str(moved) if moved else (str(dest) if dry_run else ""),
                    year=meta.year,
                    authors=meta.authors,
                    title=meta.title,
                    report_ids=meta.report_ids,
                    doi=meta.doi,
                    patent_id=meta.patent_id,
                    company=meta.company,
                    file_type=meta.file_type,
                    metadata_source=meta.metadata_source,
                    status=status,
                    error_flags="|".join(flags),
                    error_message=msg,
                    file_hash=file_hash,
                )
            )
            if skip_gate and status == "duplicate_doi":
                skip_gate.clear(source_name)
            return ProcessResult(
                status=status,
                source_path=path,
                dest_path=moved if moved else (dest if dry_run else None),
                dest_name=dest_name,
                meta=meta,
                file_hash=file_hash,
                error_message=msg,
                flags=flags,
            )

    naming_kwargs = dict(
        n_title_words=config.naming.n_title_words,
        name_spacer=config.naming.name_spacer,
        title_spacer=config.naming.title_spacer,
        max_filename_length=config.naming.max_filename_length,
    )
    parts = NameParts(
        year=meta.year,
        author=meta.first_author,
        title=meta.title,
        file_type=meta.file_type,
        patent_id=meta.patent_id or PLACEHOLDER_PATENT,
        company=meta.company or PLACEHOLDER_COMPANY,
    )
    dest_name = build_filename(parts, **naming_kwargs)
    flags = list(meta.flags)

    needs_suffix = "insufficient_metadata" in flags
    name_hit = index.has_name(dest_name)
    if name_hit and name_hit.sha256 != file_hash:
        needs_suffix = True
    if needs_suffix:
        dest_name = with_hash_suffix(dest_name, file_hash, name_spacer=config.naming.name_spacer)
        flags.append("name_disambiguated")

    dest_name, on_disk_clash = _unique_dest_name(
        config.repository_dir,
        dest_name,
        file_hash,
        name_spacer=config.naming.name_spacer,
    )
    if on_disk_clash and "name_disambiguated" not in flags:
        flags.append("name_disambiguated")

    dest = config.repository_dir / dest_name
    moved, fail_status, msg = _try_move(path, dest, dry_run=dry_run)
    if fail_status:
        status = fail_status
        if "exists" in msg.lower():
            flags.append("dest_exists")
        moved = None
    else:
        status = "renamed_moved"
        if moved is not None:
            # Update in-memory index even on dry-run so later files in this
            # batch get hash-suffix disambiguation for colliding names.
            index.add(
                RepoEntry(
                    path=moved,
                    name=dest_name,
                    size=path.stat().st_size if dry_run else moved.stat().st_size,
                    mtime=path.stat().st_mtime if dry_run else moved.stat().st_mtime,
                    sha256=file_hash,
                    doi=meta.doi or "",
                )
            )
        if skip_gate:
            skip_gate.clear(source_name)

    log_status = status
    if dry_run and status == "renamed_moved":
        log_status = "dry_run_renamed_moved"

    log.append(
        LogRow(
            script=script,
            source_path=str(path),
            source_name=source_name,
            dest_name=dest_name,
            dest_path=str(moved) if moved else (str(dest) if dry_run and status == "renamed_moved" else ""),
            year=meta.year,
            authors=meta.authors,
            title=meta.title,
            report_ids=meta.report_ids,
            doi=meta.doi,
            patent_id=meta.patent_id,
            company=meta.company,
            file_type=meta.file_type,
            metadata_source=meta.metadata_source,
            status=log_status,
            error_flags="|".join(dict.fromkeys(flags)),
            error_message=msg,
            file_hash=file_hash,
        )
    )

    return ProcessResult(
        status=log_status,
        source_path=path,
        dest_path=moved if moved else (dest if dry_run and status == "renamed_moved" else None),
        dest_name=dest_name,
        meta=meta,
        file_hash=file_hash,
        error_message=msg,
        flags=flags,
    )
