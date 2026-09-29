"""Profile directories and token persistence."""

from __future__ import annotations

import dataclasses
import fcntl
import json
import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from lupaxa.token_manager import crypto
from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.io import (
    chmod_700,
    dump_json,
    ensure_dir,
    publish,
    read_json,
    temporary_sibling,
)
from lupaxa.token_manager.models import (
    CONFIG_FILE,
    VALID_ENCRYPTION,
    ProfileConfig,
    Token,
    require_encryption,
)
from lupaxa.token_manager.style import warning

APP_NAME = "tokenctl"
DEFAULT_PROFILE = "default"
_PROFILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
TOKENS_FILE = "tokens.json"
TOKENS_FILE_GPG = "tokens.json.gpg"
TOKENS_FILE_OPENSSL = "tokens.json.enc"


def _same_rows(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> bool:
    """True when both lists contain the same id, type, name, value, and env var."""

    def key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(row.get("id", "")),
            str(row.get("type", "")),
            str(row.get("name", "")),
            str(row.get("value", "")),
            str(row.get("env_var") or ""),
        )

    return sorted(key(row) for row in expected) == sorted(key(row) for row in actual)


def _token_paths(profile_dir: Path) -> tuple[Path, Path, Path]:
    return (
        profile_dir / TOKENS_FILE,
        profile_dir / TOKENS_FILE_GPG,
        profile_dir / TOKENS_FILE_OPENSSL,
    )


def _present_token_files(profile_dir: Path) -> list[Path]:
    return [path for path in _token_paths(profile_dir) if path.is_file()]


def profile_exists(profile_dir: Path) -> bool:
    """True when the directory has a config or a token file."""
    if (profile_dir / CONFIG_FILE).is_file():
        return True
    return bool(_present_token_files(profile_dir))


def inferred_encryption(profile_dir: Path) -> str:
    """Return the encryption mode implied by a profile with no ``config.json``."""
    files = _present_token_files(profile_dir)
    if len(files) > 1:
        names = ", ".join(path.name for path in files)
        raise TokenManagerError(
            f"Profile '{profile_dir.name}' has {names} and no config.json. "
            "Refusing to guess an encryption mode."
        )
    if not files:
        return "none"
    if files[0].name == TOKENS_FILE_GPG:
        return "gpg"
    if files[0].name == TOKENS_FILE_OPENSSL:
        return "openssl"
    return "none"


def profile_encryption(profile_dir: Path) -> str:
    """Return the encryption mode stored for this profile, or inferred from its files."""
    if (profile_dir / CONFIG_FILE).is_file():
        return ProfileConfig.load(profile_dir).encryption
    return inferred_encryption(profile_dir)


def list_profiles(config_dir: Path | None = None) -> list[tuple[str, bool, str]]:
    """Return ``(name, initialised, encryption)`` for every profile directory.

    A directory with no config and no token file is included and marked not
    initialised. Its encryption is an empty string.
    """
    root = (config_dir if config_dir is not None else default_config_dir()) / "profiles"
    if not root.is_dir():
        return []
    found: list[tuple[str, bool, str]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        ready = profile_exists(path)
        encryption = profile_encryption(path) if ready else ""
        found.append((path.name, ready, encryption))
    return sorted(found)


def default_config_dir() -> Path:
    """Return ``$XDG_CONFIG_HOME/tokenctl`` (or ``~/.config/tokenctl``)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_NAME


class Store:
    """Read and write one named profile."""

    def __init__(
        self,
        profile: str = DEFAULT_PROFILE,
        *,
        config_dir: Path | None = None,
        create: bool = False,
    ) -> None:
        chosen = profile or DEFAULT_PROFILE
        if not _PROFILE_NAME.fullmatch(chosen):
            raise TokenManagerError(
                f"Invalid profile name '{chosen}'. Use letters, digits, '.', '_' or '-'.",
                exit_code=2,
            )
        self.profile = chosen
        root = config_dir if config_dir is not None else default_config_dir()
        self.profile_dir = root / "profiles" / self.profile
        self._lock_fd: int | None = None
        self._mutex = threading.RLock()
        if create:
            ensure_dir(self.profile_dir)
        elif not profile_exists(self.profile_dir):
            raise TokenManagerError(
                f"Profile '{self.profile}' does not exist. Run 'profile init' first.",
                exit_code=2,
            )
        self._tighten_tree(root)
        self._load_config()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Hold this profile's lock across a read-modify-write."""
        with self._mutex:
            outer = self._lock_fd is None
            if outer:
                lock_path = self.profile_dir / ".lock"
                try:
                    self._lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
                    fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
                    self._load_config()
                except OSError as exc:
                    self._release_lock()
                    raise TokenManagerError(
                        f"Unable to lock profile '{self.profile}': {exc}"
                    ) from exc
                except Exception:
                    self._release_lock()
                    raise
            try:
                yield
            finally:
                if outer:
                    self._release_lock()

    def _release_lock(self) -> None:
        if self._lock_fd is None:
            return
        fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        os.close(self._lock_fd)
        self._lock_fd = None

    def _tighten_tree(self, root: Path) -> None:
        """Keep the config root, profiles directory, and this profile private."""
        root_resolved = root.resolve()
        for directory in (root, root / "profiles", self.profile_dir):
            resolved = directory.resolve()
            inside = resolved == root_resolved or root_resolved in resolved.parents
            if inside:
                chmod_700(directory)

    def _paths(self) -> tuple[Path, Path, Path]:
        return _token_paths(self.profile_dir)

    def _active_paths(self) -> tuple[str, Path]:
        plain, gpg_path, enc_path = self._paths()
        mode = self.config.encryption
        if mode == "none":
            return ("none", plain)
        if mode == "gpg":
            return ("gpg", gpg_path)
        if mode == "openssl":
            return ("openssl", enc_path)
        if gpg_path.exists():
            return ("gpg", gpg_path)
        if enc_path.exists():
            return ("openssl", enc_path)
        return ("none", plain)

    def load(self) -> list[Token]:
        """Load every token in this profile."""
        mode, path = self._active_paths()
        if not path.exists():
            leftovers = [candidate for candidate in self._paths() if candidate.exists()]
            if leftovers:
                names = ", ".join(candidate.name for candidate in leftovers)
                raise TokenManagerError(
                    f"Profile '{self.profile}' has {names}, which does not match "
                    f"encryption mode '{mode}'. Refusing to treat the profile as empty."
                )
            return []
        try:
            return [Token.from_dict(row) for row in self._read_rows(mode, path)]
        except (KeyError, TypeError) as exc:
            raise TokenManagerError(
                f"{path.name} has an invalid token record. Refusing to continue."
            ) from exc

    def _load_config(self) -> None:
        """Load config.json, or infer encryption from a legacy token file."""
        self.config = ProfileConfig.load(self.profile_dir)
        if not (self.profile_dir / CONFIG_FILE).is_file():
            self.config.encryption = inferred_encryption(self.profile_dir)

    def update_profile(self) -> bool:
        """Write ``config.json`` for a legacy profile.

        Returns True when the file was written. The token file is not rewritten.
        """
        if (self.profile_dir / CONFIG_FILE).is_file():
            return False
        if not _present_token_files(self.profile_dir):
            raise TokenManagerError(
                f"Profile '{self.profile}' has no token file to update. "
                "Run 'profile init' to create it.",
                exit_code=2,
            )
        self.config.save(self.profile_dir)
        return True

    def save(self, tokens: list[Token]) -> None:
        """Write every token using the profile's encryption mode."""
        mode, path = self._active_paths()
        rows = [dataclasses.asdict(token) for token in tokens]
        self._write_verified(mode, path, rows)
        if not (self.profile_dir / CONFIG_FILE).is_file():
            self.config.save(self.profile_dir)

    def init_profile(self, encryption: str) -> None:
        """Create a profile. Refuse when the profile already has data."""
        mode = (encryption or "none").lower()
        if mode not in VALID_ENCRYPTION:
            raise TokenManagerError(
                "Invalid encryption mode. Use: none | gpg | openssl",
                exit_code=2,
            )
        if self._has_existing_data():
            raise TokenManagerError(
                f"Profile '{self.profile}' already exists. "
                "Init will not change it. "
                "Use 'profile set-encryption' to change the encryption mode."
            )
        if mode != "none":
            require_encryption(mode)
        new_path = self._path_for(mode)
        self._write_verified(mode, new_path, [])
        self.config.encryption = mode
        try:
            self.config.save(self.profile_dir)
        except Exception as exc:
            if self._encryption_on_disk() != mode:
                self.config.encryption = "none"
                new_path.unlink(missing_ok=True)
                if isinstance(exc, TokenManagerError):
                    raise
                raise TokenManagerError(f"Failed to save profile config: {exc}") from exc

    def set_encryption(self, encryption: str) -> None:
        """Rewrite the current tokens in a new encryption mode."""
        mode = (encryption or "none").lower()
        if mode not in VALID_ENCRYPTION:
            raise TokenManagerError(
                "Invalid encryption mode. Use: none | gpg | openssl",
                exit_code=2,
            )
        require_encryption(mode)
        if mode == self.config.encryption:
            return
        old_mode = self.config.encryption
        rewrap = old_mode != "none" and mode != "none"
        if rewrap and crypto.require_separate_passphrases():
            warning(
                f"{crypto.PASSPHRASE_ENV} is ignored because the profile needs two passphrases."
            )
        if rewrap:
            crypto.use_passphrase_slot("current")
        try:
            tokens = self.load()
            if rewrap:
                crypto.use_passphrase_slot("new")
            rows = [dataclasses.asdict(token) for token in tokens]
            old_path = self._path_for(old_mode)
            new_path = self._path_for(mode)
            self._write_verified(mode, new_path, rows)
        finally:
            crypto.use_passphrase_slot("")
        self.config.encryption = mode
        try:
            self.config.save(self.profile_dir)
        except Exception as exc:
            if self._encryption_on_disk() != mode:
                self.config.encryption = old_mode
                if new_path != old_path:
                    new_path.unlink(missing_ok=True)
                if isinstance(exc, TokenManagerError):
                    raise
                raise TokenManagerError(f"Failed to save profile config: {exc}") from exc
        if old_path != new_path and old_path.exists():
            try:
                old_path.unlink()
            except OSError as exc:
                raise TokenManagerError(
                    f"Encryption is now {mode}, but the previous file could not be removed: "
                    f"{old_path} ({exc})"
                ) from exc

    def _path_for(self, mode: str) -> Path:
        plain, gpg_path, enc_path = self._paths()
        if mode == "gpg":
            return gpg_path
        if mode == "openssl":
            return enc_path
        return plain

    def _read_rows(self, mode: str, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            raise TokenManagerError(f"Token file is missing: {path}")
        if mode == "none":
            try:
                data = read_json(path)
            except json.JSONDecodeError as exc:
                raise TokenManagerError(
                    f"{path.name} is not valid JSON. Refusing to continue."
                ) from exc
            if not isinstance(data, list):
                raise TokenManagerError(
                    f"{path.name} is not a list of tokens. Refusing to continue."
                )
            return data
        if mode == "gpg":
            return crypto.read_gpg(path, profile=self.profile)
        return crypto.read_openssl(path, profile=self.profile)

    def _write_verified(self, mode: str, path: Path, rows: list[dict[str, Any]]) -> None:
        """Write ``rows`` beside ``path``, read them back, then replace ``path``."""
        tmp = temporary_sibling(path)
        try:
            if tmp.exists():
                tmp.unlink()
            if mode == "none":
                dump_json(tmp, rows)
            elif mode == "gpg":
                crypto.write_gpg(tmp, rows, profile=self.profile)
            else:
                crypto.write_openssl(tmp, rows, profile=self.profile)
            actual = self._read_rows(mode, tmp)
            if not _same_rows(rows, actual):
                raise TokenManagerError(
                    f"Refusing to replace {path.name}: written tokens did not read back."
                )
            publish(tmp, path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def _encryption_on_disk(self) -> str | None:
        """Return the saved encryption mode, or ``None`` when config cannot be read."""
        try:
            return ProfileConfig.load(self.profile_dir).encryption
        except TokenManagerError:
            return None

    def _has_existing_data(self) -> bool:
        """True when this profile already has a config or a token file."""
        if (self.profile_dir / CONFIG_FILE).exists():
            return True
        return any(path.exists() for path in self._paths())
