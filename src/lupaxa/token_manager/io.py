"""Filesystem helpers for profile JSON."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from lupaxa.token_manager.exceptions import TokenManagerError


def ensure_dir(path: Path) -> None:
    """Create a directory, including parents, and keep it private to the owner."""
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise TokenManagerError(f"Unable to create directory: {path} ({exc})") from exc
    chmod_700(path)


def chmod_700(path: Path) -> None:
    """Restrict a directory to the owner. Ignore platforms without POSIX modes."""
    try:
        path.chmod(0o700)
    except OSError:
        return


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


def temporary_sibling(path: Path) -> Path:
    """Return a unique temporary path in the same directory as ``path``."""
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")


def dump_json(path: Path, data: Any) -> None:
    """Write JSON to ``path`` and flush it to disk. Does not replace another file."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    except OSError as exc:
        raise TokenManagerError(f"Failed to write {path}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise TokenManagerError(f"Failed to write {path}: {exc}") from exc
    chmod_600(path)


def publish(tmp: Path, dest: Path) -> None:
    """Replace ``dest`` with ``tmp`` only after ``tmp`` is on disk."""
    try:
        os.replace(tmp, dest)
        chmod_600(dest)
        directory = os.open(dest.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise TokenManagerError(f"Failed to replace {dest}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    """Atomically write JSON and restrict permissions."""
    tmp = temporary_sibling(path)
    try:
        dump_json(tmp, data)
        publish(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
