from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def atomic_write_json(path: Path, value: BaseModel | dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload: Any
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


class JobStore:
    def __init__(self, root: Path, job_id: str) -> None:
        if not job_id or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in job_id
        ):
            raise ValueError("job_id contains unsafe characters")
        self.root = root.resolve()
        self.job_id = job_id
        self.path = (self.root / job_id).resolve()
        if self.root not in self.path.parents:
            raise ValueError("job path escapes configured job root")

    def initialize(self) -> None:
        for relative in ("source", "pages", "document", "output"):
            (self.path / relative).mkdir(parents=True, exist_ok=True)

    def page_dir(self, page_number: int) -> Path:
        if page_number < 1:
            raise ValueError("page numbers are one-based")
        path = self.path / "pages" / f"{page_number:04d}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, relative_path: str, value: BaseModel | dict[str, Any] | list[Any]) -> Path:
        path = self.path / relative_path
        atomic_write_json(path, value)
        return path
