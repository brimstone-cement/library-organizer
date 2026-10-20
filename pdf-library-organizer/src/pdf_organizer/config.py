"""Load and validate config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class CrossrefConfig(BaseModel):
    mailto: str
    timeout_seconds: float = 30.0
    max_retries: int = 3

    @field_validator("mailto")
    @classmethod
    def mailto_required(cls, value: str) -> str:
        value = value.strip()
        if not value or "@" not in value:
            raise ValueError("crossref.mailto must be a real contact email for the polite pool")
        domain = value.rsplit("@", 1)[-1].lower()
        if domain in {"example.com", "example.org", "example.net"}:
            raise ValueError(
                "crossref.mailto must not use an example.com/org/net address; "
                "use a real mailbox CrossRef can contact"
            )
        return value


class FoldersConfig(BaseModel):
    import_: str = Field(default="import", alias="import")
    import_form: str = "import-form"
    repository: str = "repository"
    duplicates: str = "duplicates"
    failed: str = "failed"
    logs: str = "logs"

    model_config = {"populate_by_name": True}


class NamingConfig(BaseModel):
    n_title_words: int = 6
    name_spacer: str = "_"
    title_spacer: str = "-"
    max_filename_length: int = 150


class AppConfig(BaseModel):
    library_root: Path
    folders: FoldersConfig = Field(default_factory=FoldersConfig)
    crossref: CrossrefConfig
    settle_seconds: float = 60.0
    naming: NamingConfig = Field(default_factory=NamingConfig)

    @property
    def import_dir(self) -> Path:
        return self.library_root / self.folders.import_

    @property
    def import_form_dir(self) -> Path:
        return self.library_root / self.folders.import_form

    @property
    def repository_dir(self) -> Path:
        return self.library_root / self.folders.repository

    @property
    def duplicates_dir(self) -> Path:
        return self.library_root / self.folders.duplicates

    @property
    def failed_dir(self) -> Path:
        return self.library_root / self.folders.failed

    @property
    def logs_dir(self) -> Path:
        return self.library_root / self.folders.logs

    @property
    def process_log_path(self) -> Path:
        return self.logs_dir / "process_log.csv"

    @property
    def repo_index_path(self) -> Path:
        return self.logs_dir / "repo_index.csv"

    @property
    def lock_path(self) -> Path:
        return self.logs_dir / "processor.lock"

    @property
    def skip_state_path(self) -> Path:
        return self.logs_dir / "skip_state.csv"

    def ensure_folders(self) -> None:
        for path in (
            self.import_dir,
            self.import_form_dir,
            self.repository_dir,
            self.duplicates_dir,
            self.failed_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load config from path, or config.yaml next to the project root / cwd."""
    if path is None:
        candidates = [
            Path.cwd() / "config.yaml",
            Path(__file__).resolve().parents[2] / "config.yaml",
        ]
        for candidate in candidates:
            if candidate.is_file():
                path = candidate
                break
        else:
            raise FileNotFoundError(
                "config.yaml not found. Copy config.example.yaml to config.yaml and edit it."
            )
    path = Path(path)
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
