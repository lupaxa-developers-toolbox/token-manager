"""Allow ``python -m lupaxa.token_manager`` to run the CLI."""

from __future__ import annotations

from lupaxa.token_manager.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
