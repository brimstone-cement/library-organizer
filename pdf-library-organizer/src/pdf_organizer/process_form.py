"""
Script 2 — process one PDF with optional form/sidecar metadata hints.

Usage:
  python -m pdf_organizer.process_form --pdf path/to/file.pdf [--meta path.json] [--config config.yaml]
  python -m pdf_organizer.process_form --pdf path/to/file.pdf --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf_organizer.config import AppConfig, load_config
from pdf_organizer.console import configure_stdio, safe_print
from pdf_organizer.crossref import CrossrefClient
from pdf_organizer.duplicates import build_repo_index_light
from pdf_organizer.hints import (
    MetadataHints,
    delete_sidecar,
    load_sidecar,
    sidecar_path_for,
    write_sidecar,
)
from pdf_organizer.lock import ProcessorLock
from pdf_organizer.log import ProcessLog
from pdf_organizer.pipeline import ProcessResult, process_one
from pdf_organizer.skip_gate import SkipLogGate

# Statuses where the sidecar should be removed (file left import-form)
_SIDECAR_DONE = frozenset(
    {
        "renamed_moved",
        "duplicate_content",
        "duplicate_doi",
        "unreadable_pdf",
        "dry_run_renamed_moved",
    }
)


def process_with_hints(
    pdf_path: Path,
    hints: MetadataHints,
    *,
    config: AppConfig,
    dry_run: bool = False,
    write_meta: Path | None = None,
    settle_seconds: float | None = 0.0,
) -> ProcessResult:
    """
    Run the shared pipeline for one PDF with hints.

    settle_seconds defaults to 0 for form submit (user confirmed the file is ready).
    Pass None to use config.settle_seconds.
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    # Form path: user explicitly submitted — do not wait for settle window
    cfg = config
    if settle_seconds is not None:
        cfg = config.model_copy(update={"settle_seconds": settle_seconds})

    sidecar = write_meta
    if sidecar is not None:
        write_sidecar(sidecar, hints)

    log = ProcessLog(cfg.process_log_path)
    skip_gate = SkipLogGate(cfg.skip_state_path)

    with ProcessorLock(cfg.lock_path):
        # Light index: cache + log DOIs only (no PDF text scrape of whole repo)
        index = build_repo_index_light(
            cfg.repository_dir,
            cfg.repo_index_path,
            cfg.process_log_path,
        )
        with CrossrefClient(cfg.crossref) as client:
            result = process_one(
                pdf_path,
                config=cfg,
                index=index,
                log=log,
                client=client,
                hints=hints,
                script="form",
                dry_run=dry_run,
                skip_gate=skip_gate,
            )
        if not dry_run:
            index.save(cfg.repo_index_path)
        skip_gate.save()

    if not dry_run and result.status in _SIDECAR_DONE:
        delete_sidecar(sidecar if sidecar is not None else sidecar_path_for(pdf_path))

    return result


def run(
    pdf: Path,
    *,
    meta: Path | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> int:
    config = load_config(config_path)
    config.ensure_folders()

    pdf = pdf.resolve()
    hints = load_sidecar(meta) if meta else MetadataHints()

    # Default sidecar next to PDF when writing on success path via process_with_hints
    sidecar = meta if meta is not None else sidecar_path_for(pdf)
    # Always persist current hints before processing (empty object is fine)
    write_sidecar(sidecar, hints)

    safe_print(f"PDF: {pdf}")
    safe_print(f"Hints: {hints.to_dict() or '(none — auto only)'}")
    if dry_run:
        safe_print("DRY RUN — no files will be moved")

    try:
        result = process_with_hints(
            pdf,
            hints,
            config=config,
            dry_run=dry_run,
            write_meta=sidecar,
        )
    except TimeoutError as exc:
        safe_print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        safe_print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    safe_print(f"Status: {result.status}")
    if result.dest_name:
        safe_print(f"Dest:  {result.dest_name}")
    if result.flags:
        safe_print(f"Flags: {'|'.join(result.flags)}")
    if result.error_message:
        safe_print(f"Error: {result.error_message}")
    if result.meta:
        safe_print(
            f"Meta:  year={result.meta.year} author={result.meta.first_author} "
            f"title={result.meta.title!r} type={result.meta.file_type}"
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(
        description="Process one PDF with optional metadata hints (Script 2)."
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Path to the PDF file")
    parser.add_argument(
        "--meta",
        type=Path,
        default=None,
        help="Optional sidecar JSON with hints (default: empty / auto only)",
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve names and log outcomes without moving files",
    )
    args = parser.parse_args(argv)
    raise SystemExit(
        run(args.pdf, meta=args.meta, config_path=args.config, dry_run=args.dry_run)
    )


if __name__ == "__main__":
    main()
