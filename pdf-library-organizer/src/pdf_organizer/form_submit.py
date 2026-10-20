"""
Script 2 UI — pick a PDF from import-form/, optional metadata, Detect from PDF, Submit.

Usage:
  python -m pdf_organizer.form_submit [--config config.yaml]
"""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from pdf_organizer.config import load_config
from pdf_organizer.crossref import CrossrefClient
from pdf_organizer.detect import detect_prefill
from pdf_organizer.hints import MetadataHints, sidecar_path_for, write_sidecar
from pdf_organizer.process_form import process_with_hints

FILE_TYPES = ("", "article", "report", "book", "patent", "manual")
FIELD_ORDER = (
    "doi",
    "year",
    "authors",
    "title",
    "report_ids",
    "patent_id",
    "company",
    "file_type",
)

_SUCCESS_STATUSES = frozenset(
    {
        "renamed_moved",
        "dry_run_renamed_moved",
        "duplicate_content",
        "duplicate_doi",
        "unreadable_pdf",
    }
)


class FormApp:
    def __init__(self, root: tk.Tk, config_path: Path | None) -> None:
        self.root = root
        self.config_path = config_path
        self.config = load_config(config_path)
        self.config.ensure_folders()

        self.root.title("PDF Library — Script 2 Form")
        self.root.minsize(520, 460)

        self.pdf_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Select a PDF from import-form/")
        self.dry_run_var = tk.BooleanVar(value=False)
        self.entries: dict[str, tk.Variable] = {}

        self._build()
        self.refresh_pdf_list()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="PDF").grid(row=0, column=0, sticky="w", **pad)
        self.pdf_combo = ttk.Combobox(frm, textvariable=self.pdf_var, state="readonly")
        self.pdf_combo.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Refresh", command=self.refresh_pdf_list).grid(
            row=0, column=2, **pad
        )

        labels = {
            "doi": "DOI",
            "year": "Year",
            "authors": "Authors",
            "title": "Title",
            "report_ids": "Report IDs",
            "patent_id": "Patent ID",
            "company": "Company",
            "file_type": "File type",
        }
        row = 1
        for key in FIELD_ORDER:
            ttk.Label(frm, text=labels[key]).grid(row=row, column=0, sticky="w", **pad)
            if key == "file_type":
                var = tk.StringVar(value="")
                widget = ttk.Combobox(
                    frm, textvariable=var, values=FILE_TYPES, state="readonly"
                )
            else:
                var = tk.StringVar(value="")
                widget = ttk.Entry(frm, textvariable=var)
            widget.grid(row=row, column=1, columnspan=2, sticky="ew", **pad)
            self.entries[key] = var
            row += 1

        ttk.Checkbutton(
            frm,
            text="Dry run (preview only — do not move files)",
            variable=self.dry_run_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Button(btn_row, text="Detect from PDF", command=self.on_detect).pack(
            side="left", padx=4
        )
        ttk.Button(btn_row, text="Clear fields", command=self.clear_fields).pack(
            side="left", padx=4
        )
        ttk.Button(btn_row, text="Submit", command=self.on_submit).pack(
            side="right", padx=4
        )

        ttk.Label(frm, textvariable=self.status_var, wraplength=480).grid(
            row=row + 1, column=0, columnspan=3, sticky="w", **pad
        )

    def import_form_dir(self) -> Path:
        return self.config.import_form_dir

    def refresh_pdf_list(self) -> None:
        folder = self.import_form_dir()
        folder.mkdir(parents=True, exist_ok=True)
        pdfs = sorted(
            p.name
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith("~$")
        )
        self.pdf_combo["values"] = pdfs
        if pdfs and self.pdf_var.get() not in pdfs:
            self.pdf_var.set(pdfs[0])
        elif not pdfs:
            self.pdf_var.set("")
        self.status_var.set(
            f"{len(pdfs)} PDF(s) in {folder}" if pdfs else f"No PDFs in {folder}"
        )

    def selected_pdf(self) -> Path | None:
        name = self.pdf_var.get().strip()
        if not name:
            return None
        path = self.import_form_dir() / name
        return path if path.is_file() else None

    def hints_from_form(self) -> MetadataHints:
        data = {key: self.entries[key].get() for key in FIELD_ORDER}
        return MetadataHints.from_mapping(data)

    def _filled_fields(self) -> list[str]:
        return [key for key in FIELD_ORDER if self.entries[key].get().strip()]

    def apply_hints_to_form(self, hints: MetadataHints, *, overwrite: bool) -> int:
        """Apply detected hints. Returns count of fields changed."""
        mapping = hints.to_dict()
        changed = 0
        for key in FIELD_ORDER:
            if key not in mapping:
                continue
            current = self.entries[key].get().strip()
            if overwrite or not current:
                if self.entries[key].get() != mapping[key]:
                    changed += 1
                self.entries[key].set(mapping[key])
        return changed

    def clear_fields(self) -> None:
        for key in FIELD_ORDER:
            self.entries[key].set("")
        self.status_var.set("Fields cleared")

    def on_detect(self) -> None:
        pdf = self.selected_pdf()
        if pdf is None:
            messagebox.showwarning("Detect", "Select a PDF first.")
            return
        self.status_var.set("Detecting…")
        self.root.update_idletasks()
        try:
            with CrossrefClient(self.config.crossref) as client:
                result = detect_prefill(pdf, client)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Detect failed", str(exc))
            self.status_var.set(f"Detect failed: {exc}")
            return
        if result.error:
            messagebox.showerror("Detect failed", result.error)
            self.status_var.set(result.error)
            return

        filled = self._filled_fields()
        overwrite = False
        if filled:
            # Default: fill blanks only. Offer overwrite if user already typed values.
            choice = messagebox.askyesnocancel(
                "Detect from PDF",
                "Some fields already have values.\n\n"
                "Yes = overwrite all with detected values\n"
                "No = fill blank fields only\n"
                "Cancel = do nothing",
            )
            if choice is None:
                self.status_var.set("Detect cancelled")
                return
            overwrite = bool(choice)

        changed = self.apply_hints_to_form(result.hints, overwrite=overwrite)
        mode = "overwrite" if overwrite else "blanks only"
        self.status_var.set(f"Detect ({mode}, {changed} fields): {result.message}")

    def on_submit(self) -> None:
        pdf = self.selected_pdf()
        if pdf is None:
            messagebox.showwarning("Submit", "Select a PDF first.")
            return
        hints = self.hints_from_form()
        sidecar = sidecar_path_for(pdf)
        dry_run = bool(self.dry_run_var.get())
        self.status_var.set("Dry run…" if dry_run else "Processing…")
        self.root.update_idletasks()
        try:
            write_sidecar(sidecar, hints)
            result = process_with_hints(
                pdf,
                hints,
                config=self.config,
                dry_run=dry_run,
                write_meta=sidecar,
                settle_seconds=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Submit failed", str(exc))
            self.status_var.set(f"Submit failed: {exc}")
            return

        msg = f"{result.status}"
        if result.dest_name:
            msg += f"\n→ {result.dest_name}"
        if result.flags:
            msg += f"\nFlags: {'|'.join(result.flags)}"
        if result.error_message:
            msg += f"\n{result.error_message}"
        if result.status in {"move_error", "skipped_in_use", "error"}:
            msg += "\n\nFile left in import-form/. Fix the issue and Submit again."

        if result.status in _SUCCESS_STATUSES:
            title = "Dry run" if dry_run else "Done"
            messagebox.showinfo(title, msg)
            if not dry_run:
                self.clear_fields()
                self.refresh_pdf_list()
        else:
            messagebox.showwarning("Finished with issues", msg)
        self.status_var.set(msg.replace("\n", " | "))


def run_ui(config_path: Path | None = None) -> None:
    root = tk.Tk()
    FormApp(root, config_path)
    root.mainloop()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Script 2 form UI for PDF metadata.")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    run_ui(args.config)


if __name__ == "__main__":
    main()
