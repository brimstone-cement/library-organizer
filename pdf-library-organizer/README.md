# Script 1 — PDF library organizer

**Canonical project path:** `C:\Users\ericl\Desktop\Working Folder\pdf-library-organizer`  
(Do not use a second copy under `C:\Users\ericl\pdf-library-organizer` — keep one tree.)

Rename and move PDFs from a SharePoint-synced `import/` folder into `repository/` using CrossRef (via DOI) and PDF metadata.

## Setup

```powershell
cd "C:\Users\ericl\Desktop\Working Folder\pdf-library-organizer"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy config.example.yaml config.yaml
# Edit config.yaml: set library_root and a real crossref.mailto (not @example.com)
```

Create these folders under `library_root` (Script 1 also creates them on run):

- `import/` — drop zone for daily auto processing
- `import-form/` — reserved for Script 2
- `repository/` — canonical store
- `duplicates/`, `failed/`, `logs/`

## Run Script 1

```powershell
python -m pdf_organizer.process_import --config config.yaml
```

Preview without moving files:

```powershell
python -m pdf_organizer.process_import --config config.yaml --dry-run
```

## Run Script 2 (form)

Drop PDFs into `import-form/`, then:

```powershell
python -m pdf_organizer.form_submit --config config.yaml
```

Or headless:

```powershell
python -m pdf_organizer.process_form --pdf "C:\path\to\import-form\file.pdf" --meta "C:\path\to\file.meta.json"
```

All form fields are optional. Blank fields use the same auto path as Script 1. **Detect from PDF** fills blank fields by default (asks before overwriting). Check **Dry run** to preview without moving.

Naming (ported from `0_rename_EL.py`):

- Article/report/book: `Year_FirstAuthor_first-six-title-words.pdf`
- Patent: `PatentID_Year_FirstAuthor_first-six-title-words.pdf` (when CrossRef type is patent, the form supplies patent metadata, or a patent ID is found on page 1 / in the filename)
- Manual: `Manual_Company_first-six-title-words.pdf`

Placeholders: `NoYear`, `NoAuthor`, `NoTitle`, `NoPatent`, `NoCompany`.

## Task Scheduler

Use `python` (not `pythonw`) and redirect output:

```powershell
python -m pdf_organizer.process_import --config "C:\Users\ericl\Desktop\Working Folder\pdf-library-organizer\config.yaml" >> "C:\Users\ericl\Brimstone Energy\Library - Documents\R&D\logs\job_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log" 2>&1
```

## Tests

```powershell
pytest
```
