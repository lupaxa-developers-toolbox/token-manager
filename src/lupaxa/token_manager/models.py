"""Token and profile records."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any

from lupaxa.token_manager.exceptions import TokenManagerError

CONFIG_FILE = "config.json"
VALID_ENCRYPTION = frozenset({"none", "gpg", "openssl"})


def now_iso() -> str:
    """Return a timezone-aware UTC timestamp in RFC3339 ``Z`` form."""
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


@dataclasses.dataclass
class Token:
    """One stored secret, unique by ``type`` plus ``name`` inside a profile."""

    id: str
    type: str
    name: str
    value: str
    env_var: str
    created_at: str
    updated_at: str

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Token:
        """Build a token from a JSON object."""
        return Token(
            id=data["id"],
            type=(data.get("type") or "").lower(),
            name=data["name"],
            value=data["value"],
            env_var=data.get("env_var") or "",
            created_at=data.get("created_at") or now_iso(),
            updated_at=data.get("updated_at") or now_iso(),
        )

    def to_public(self) -> dict[str, Any]:
        """Return token metadata without the secret value."""
        data = dataclasses.asdict(self)
        data.pop("value", None)
        return data


@dataclasses.dataclass
class ProfileConfig:
    """Per-profile encryption setting."""

    encryption: str = "none"

    @staticmethod
    def load(profile_dir: Path) -> ProfileConfig:
        """Load ``config.json``, defaulting to plaintext when it is missing."""
        from lupaxa.token_manager.io import read_json

        try:
            data = read_json(profile_dir / CONFIG_FILE)
        except json.JSONDecodeError as exc:
            raise TokenManagerError("config.json is not valid JSON. Refusing to continue.") from exc
        if data is None:
            return ProfileConfig()
        if not isinstance(data, dict):
            raise TokenManagerError("config.json is not an object. Refusing to continue.")
        encryption = data.get("encryption", "none")
        if not isinstance(encryption, str) or encryption.lower() not in VALID_ENCRYPTION:
            raise TokenManagerError(
                f"config.json has unknown encryption mode {encryption!r}. Refusing to continue."
            )
        return ProfileConfig(encryption=encryption.lower())

    def save(self, profile_dir: Path) -> None:
        """Write ``config.json``."""
        from lupaxa.token_manager.io import write_json

        write_json(profile_dir / CONFIG_FILE, dataclasses.asdict(self))


def require_encryption(encryption: str) -> None:
    """Raise when the selected encryption tool is not on ``PATH``."""
    import shutil

    if encryption == "gpg" and shutil.which("gpg") is None:
        raise TokenManagerError("Encryption mode 'gpg' selected, but 'gpg' is not installed.")
    if encryption == "openssl" and shutil.which("openssl") is None:
        raise TokenManagerError(
            "Encryption mode 'openssl' selected, but 'openssl' is not installed."
        )
