"""
Script 1 — daily batch processor for PDFs dropped in the import/ folder.

Usage:
  python -m pdf_organizer.process_import [--config config.yaml] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from pdf_organizer.config import load_config
from pdf_organizer.console import configure_stdio, safe_print
from pdf_organizer.crossref import CrossrefClient
from pdf_organizer.duplicates import build_repo_index
from pdf_organizer.hints import MetadataHints
from pdf_organizer.lock import ProcessorLock
from pdf_organizer.log import LogRow, ProcessLog
from pdf_organizer.pdf_meta import extract_pdf_fields
from pdf_organizer.pipeline import process_one
from pdf_organizer.skip_gate import SkipLogGate


def iter_import_pdfs(import_dir: Path) -> list[Path]:
    pdfs = []
    for path in sorted(import_dir.iterdir()):
        if not path.is_file():
            continue
        if not path.name.lower().endswith(".pdf"):
            continue
        if path.name.startswith("~$"):
            continue
        pdfs.append(path)
    return pdfs


def run(config_path: Path | None = None, *, dry_run: bool = False) -> int:
    config = load_config(config_path)
    config.ensure_folders()

    pdfs = iter_import_pdfs(config.import_dir)
    print(f"Library root: {config.library_root}")
    print(f"Found {len(pdfs)} PDF(s) in {config.import_dir}")
    if dry_run:
        print("DRY RUN — no files will be moved")

    if not pdfs:
        return 0

    log = ProcessLog(config.process_log_path)
    skip_gate = SkipLogGate(config.skip_state_path)
    counts: dict[str, int] = {}
    try:
        with ProcessorLock(config.lock_path):
            index = build_repo_index(
                config.repository_dir,
                config.repo_index_path,
                config.process_log_path,
                extract_doi_fn=extract_pdf_fields,
            )
            with CrossrefClient(config.crossref) as client:
                for path in pdfs:
                    if not path.is_file():
                        continue
                    try:
                        result = process_one(
                            path,
                            config=config,
                            index=index,
                            log=log,
                            client=client,
                            hints=MetadataHints(),
                            script="import",
                            dry_run=dry_run,
                            skip_gate=skip_gate,
                        )
                    except Exception as exc:  # noqa: BLE001 — keep batch alive
                        err = f"{type(exc).__name__}: {exc}"
                        print(f"  [error] {path.name}: {err}", file=sys.stderr)
                        traceback.print_exc()
                        log.append(
                            LogRow(
                                script="import",
                                source_path=str(path),
                                source_name=path.name,
                                status="error",
                                error_message=err,
                            )
                        )
                        counts["error"] = counts.get("error", 0) + 1
                        continue
                    counts[result.status] = counts.get(result.status, 0) + 1
                    dest = result.dest_name or "(none)"
                    safe_print(f"  [{result.status}] {path.name} -> {dest}")
            if not dry_run:
                index.save(config.repo_index_path)
            skip_gate.save()
    except TimeoutError as exc:
        safe_print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"Done. {summary}")
    print(f"Log: {config.process_log_path}")
    return 0


def main(argv: list[str] | None = None) -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(
        description="Process PDFs in the import folder (Script 1 — daily auto rename/move)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve names and log outcomes without moving files",
    )
    args = parser.parse_args(argv)
    raise SystemExit(run(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
