"""Filesystem helpers for profile JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lupaxa.token_manager.exceptions import TokenManagerError


def ensure_dir(path: Path) -> None:
    """Create a directory, including parents."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise TokenManagerError(f"Unable to create directory: {path} ({exc})") from exc


def chmod_600(path: Path) -> None:
    """Restrict a file to the owner. Ignore platforms without POSIX modes."""
    try:
        path.chmod(0o600)
    except OSError:
        return


def read_json(path: Path) -> Any:
    """Load JSON, or return ``None`` when the file does not exist."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def write_json(path: Path, data: Any) -> None:
    """Atomically write JSON and restrict permissions."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=False)
            handle.write("\n")
        tmp.replace(path)
        chmod_600(path)
    except OSError as exc:
        raise TokenManagerError(f"Failed to write {path}: {exc}") from exc
