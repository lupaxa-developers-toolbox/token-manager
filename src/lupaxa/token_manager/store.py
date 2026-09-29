"""Profile directories and token persistence."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

from lupaxa.token_manager import crypto
from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.io import ensure_dir, read_json, write_json
from lupaxa.token_manager.models import (
    VALID_ENCRYPTION,
    ProfileConfig,
    Token,
    require_encryption,
)

APP_NAME = "tokenctl"
DEFAULT_PROFILE = "default"
TOKENS_FILE = "tokens.json"
TOKENS_FILE_GPG = "tokens.json.gpg"
TOKENS_FILE_OPENSSL = "tokens.json.enc"


def default_config_dir() -> Path:
    """Return ``$XDG_CONFIG_HOME/tokenctl`` (or ``~/.config/tokenctl``)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_NAME


class Store:
    """Read and write one named profile."""

    def __init__(self, profile: str = DEFAULT_PROFILE, *, config_dir: Path | None = None) -> None:
        self.profile = profile or DEFAULT_PROFILE
        root = config_dir if config_dir is not None else default_config_dir()
        self.profile_dir = root / "profiles" / self.profile
        ensure_dir(self.profile_dir)
        self.config = ProfileConfig.load(self.profile_dir)

    def _paths(self) -> tuple[Path, Path, Path]:
        return (
            self.profile_dir / TOKENS_FILE,
            self.profile_dir / TOKENS_FILE_GPG,
            self.profile_dir / TOKENS_FILE_OPENSSL,
        )

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
            rows: list[dict[str, Any]] = []
        elif mode == "none":
            data = read_json(path)
            rows = data if isinstance(data, list) else []
        elif mode == "gpg":
            rows = crypto.read_gpg(path)
        else:
            rows = crypto.read_openssl(path)
        return [Token.from_dict(row) for row in rows]

    def save(self, tokens: list[Token]) -> None:
        """Write every token using the profile's encryption mode."""
        mode, path = self._active_paths()
        rows = [dataclasses.asdict(token) for token in tokens]
        if mode == "none":
            write_json(path, rows)
        elif mode == "gpg":
            crypto.write_gpg(path, rows)
        else:
            crypto.write_openssl(path, rows)

    def init_profile(self, encryption: str) -> None:
        """Create or re-initialise the profile with an encryption mode."""
        mode = (encryption or "none").lower()
        if mode not in VALID_ENCRYPTION:
            raise TokenManagerError(
                "Invalid encryption mode. Use: none | gpg | openssl",
                exit_code=2,
            )
        if mode != "none":
            require_encryption(mode)
        tokens = self.load()
        self.config.encryption = mode
        self.config.save(self.profile_dir)
        self.save(tokens)
        self._drop_inactive()

    def set_encryption(self, encryption: str) -> None:
        """Rewrite the current tokens in a new encryption mode."""
        mode = (encryption or "none").lower()
        if mode not in VALID_ENCRYPTION:
            raise TokenManagerError(
                "Invalid encryption mode. Use: none | gpg | openssl",
                exit_code=2,
            )
        require_encryption(mode)
        tokens = self.load()
        self.config.encryption = mode
        self.config.save(self.profile_dir)
        self.save(tokens)
        self._drop_inactive()

    def _drop_inactive(self) -> None:
        """Remove token files that are not the active encryption envelope."""
        _mode, active = self._active_paths()
        for path in self._paths():
            if path != active and path.exists():
                path.unlink()
