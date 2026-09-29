"""Grouped text tables for ``tokenctl list``."""

from __future__ import annotations

import textwrap
from collections import defaultdict

from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.models import Token

COLUMN_LABELS: dict[str, str] = {
    "name": "Name",
    "env_var": "Env var",
    "id": "ID",
    "updated": "Updated",
    "created": "Created",
    "value": "Value",
    "type": "Type",
}
DEFAULT_COLUMNS: tuple[str, ...] = ("name", "env_var", "id", "updated", "created", "value")


def mask_secret(secret: str) -> str:
    """Hide a secret, keeping its length visible."""
    if not secret:
        return ""
    shown = "•" * min(len(secret), 8)
    if len(secret) > 8:
        return f"{shown}… ({len(secret)})"
    return f"{shown} ({len(secret)})"


def parse_columns(raw: str | None) -> list[str]:
    """Parse a comma-separated column list. ``None`` selects the default set."""
    if raw is None:
        return list(DEFAULT_COLUMNS)
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    if not keys:
        raise TokenManagerError("No columns selected.", exit_code=2)
    unknown = [key for key in keys if key not in COLUMN_LABELS]
    if unknown:
        names = ", ".join(COLUMN_LABELS)
        raise TokenManagerError(
            f"Unknown column '{unknown[0]}'. Choose from: {names}.",
            exit_code=2,
        )
    return keys


def group_by_type(tokens: list[Token]) -> dict[str, list[Token]]:
    """Group tokens by type, with type names sorted."""
    grouped: dict[str, list[Token]] = defaultdict(list)
    for token in tokens:
        grouped[token.type].append(token)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _cell(token: Token, key: str, *, reveal: bool) -> str:
    if key == "value":
        return token.value if reveal else mask_secret(token.value)
    return str(getattr(token, key))


def _widths(headers: list[str], rows: list[list[str]], max_width: int | None) -> list[int]:
    natural = [
        max([len(header), *(len(row[index]) for row in rows)])
        for index, header in enumerate(headers)
    ]
    if max_width is None:
        return natural
    gaps = 3 * (len(headers) - 1) if len(headers) > 1 else 0
    budget = max(max_width - gaps, len(headers))
    if sum(natural) <= budget:
        return natural
    widths = natural[:]
    while sum(widths) > budget:
        index = max(range(len(widths)), key=lambda item: widths[item])
        if widths[index] <= 1:
            break
        widths[index] -= 1
    return widths


def _wrap_row(cells: list[str], widths: list[int], *, wrap: bool) -> list[list[str]]:
    if not wrap:
        return [cells]
    wrapped: list[list[str]] = []
    for cell, width in zip(cells, widths, strict=True):
        wrapped.append(textwrap.wrap(cell, width=width) or [""])
    height = max(len(lines) for lines in wrapped)
    lines_out: list[list[str]] = []
    for line_index in range(height):
        lines_out.append(
            [lines[line_index] if line_index < len(lines) else "" for lines in wrapped]
        )
    return lines_out


def render_pretty_table(
    tokens: list[Token],
    profile: str,
    encryption: str,
    *,
    reveal: bool,
    columns: list[str] | None = None,
    max_width: int | None = None,
) -> str:
    """Render tokens as a grouped plain-text table."""
    if not tokens:
        return "No tokens.\n"

    selected = columns if columns is not None else list(DEFAULT_COLUMNS)
    headers = [COLUMN_LABELS[key] for key in selected]
    rows_by_group: dict[str, list[list[str]]] = {}
    for token_type, group in group_by_type(tokens).items():
        ordered = sorted(group, key=lambda token: (token.name, token.updated_at))
        rows_by_group[token_type] = [
            [_cell(token, key, reveal=reveal) for key in selected] for token in ordered
        ]

    out_lines: list[str] = []
    for token_type, rows in rows_by_group.items():
        widths = _widths(headers, rows, max_width)
        total_width = sum(widths) + 3 * (len(widths) - 1)
        left_title = f"Token type: {token_type}"
        right_title = f"Profile: {profile} (enc: {encryption})"
        sep_line = "-" * (total_width + 2)
        title_line = left_title.ljust(total_width // 2) + " | " + right_title

        def pad_row(cells: list[str], column_widths: list[int] = widths) -> str:
            parts = [str(cell).ljust(column_widths[index]) for index, cell in enumerate(cells)]
            return " | ".join(parts)

        out_lines.append(sep_line)
        out_lines.append(title_line)
        out_lines.append(sep_line)
        out_lines.append(pad_row(headers))
        out_lines.append(sep_line)
        for row in rows:
            for line in _wrap_row(row, widths, wrap=max_width is not None):
                out_lines.append(pad_row(line))
        out_lines.append(sep_line)
        out_lines.append("")

    return "\n".join(out_lines).rstrip() + "\n"
