"""Terminal colours for human-facing status text.

Machine-readable output stays plain. Colour follows ``NO_COLOR`` and
``CLICOLOR_FORCE`` and is used only when the stream is a terminal.
"""

from __future__ import annotations

import os
import re
import sys
from typing import TextIO

_CODES = {
    "red": "31",
    "green": "32",
    "yellow": "33",
    "cyan": "36",
    "white": "97",
    "dim": "2",
}


def colour_enabled(stream: TextIO | None = None) -> bool:
    """Return whether ``stream`` should receive ANSI colours."""
    if os.environ.get("NO_COLOR"):
        return False
    target = stream if stream is not None else sys.stdout
    if os.environ.get("CLICOLOR_FORCE"):
        return True
    if os.environ.get("CLICOLOR") == "0":
        return False
    isatty = getattr(target, "isatty", None)
    return bool(isatty and isatty())


def paint(text: str, colour: str, *, stream: TextIO | None = None) -> str:
    """Wrap ``text`` in ``colour`` when that stream should be coloured."""
    if not colour_enabled(stream):
        return text
    code = _CODES[colour]
    return f"\033[{code}m{text}\033[0m"


_SYNTAX = re.compile(r"\{[^{}]+\}|--?[A-Za-z0-9][\w-]*|\b[A-Z][A-Z0-9_]+\b|\b[a-z][\w-]*\b")


def paint_syntax(text: str, *, stream: TextIO | None = None) -> str:
    """Colour command names, flags, and metavars inside ``text``."""
    if not colour_enabled(stream):
        return text
    parts: list[str] = []
    cursor = 0
    for match in _SYNTAX.finditer(text):
        parts.append(text[cursor : match.start()])
        token = match.group(0)
        if token.startswith("{"):
            names = ",".join(paint(name, "cyan", stream=stream) for name in token[1:-1].split(","))
            parts.append("{" + names + "}")
        elif token[:1].isupper():
            parts.append(paint(token, "yellow", stream=stream))
        else:
            parts.append(paint(token, "cyan", stream=stream))
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)


def success(message: str) -> None:
    """Print a success line in green."""
    print(paint(message, "green"))


def info(message: str) -> None:
    """Print an informational line in cyan."""
    print(paint(message, "cyan"))


def warning(message: str) -> None:
    """Print a warning line in yellow on stderr."""
    print(paint(message, "yellow", stream=sys.stderr), file=sys.stderr)


def error(message: str) -> None:
    """Print an error line in red on stderr."""
    print(paint(message, "red", stream=sys.stderr), file=sys.stderr)
