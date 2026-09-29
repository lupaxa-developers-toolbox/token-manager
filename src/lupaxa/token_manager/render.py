"""Grouped text tables for ``tokenctl list``."""

from __future__ import annotations

import textwrap
from collections import defaultdict

from lupaxa.token_manager.exceptions import TokenManagerError
from lupaxa.token_manager.models import Token
from lupaxa.token_manager.style import colour_enabled, paint

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
    if key == "env_var":
        return token.env_var
    field = {"updated": "updated_at", "created": "created_at"}.get(key, key)
    return str(getattr(token, field))


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


def _center(text: str, width: int) -> str:
    """Return ``text`` centered in ``width`` with spaces."""
    if len(text) >= width:
        return text
    gap = width - len(text)
    left = gap // 2
    return f"{' ' * left}{text}{' ' * (gap - left)}"


def _paint_prefix(text: str, prefix: str, rest_colour: str) -> str:
    """Paint ``prefix`` bright white and the remainder ``rest_colour``."""
    if not colour_enabled():
        return text
    start = text.find(prefix)
    if start < 0:
        return paint(text, rest_colour)
    end = start + len(prefix)
    return text[:start] + paint(prefix, "white") + paint(text[end:], rest_colour)


def _center_in_rule(text: str, width: int, colour: str, *, prefix: str | None = None) -> str:
    """Place ``text`` in the middle of a rule, with one space on each side."""
    label = f" {text} "
    if len(label) > width:
        width = len(label)
    gap = width - len(label)
    left = gap // 2
    right = gap - left
    middle = _paint_prefix(label, prefix, colour) if prefix else paint(label, colour)
    return paint("-" * left, "dim") + middle + paint("-" * right, "dim")


def render_profile_table(profiles: list[tuple[str, bool, str]]) -> str:
    """Render every profile directory as a name, initialised, and encryption table."""
    if not profiles:
        return paint("No profiles.", "cyan") + "\n"

    headers = ["Name", "Initialised", "Encryption"]
    rows = [[name, "yes" if ready else "no", encryption] for name, ready, encryption in profiles]
    widths = _widths(headers, rows, None)
    total_width = sum(widths) + 3 * (len(widths) - 1)
    sep_line = paint("-" * (total_width + 2), "dim")
    rule = paint(" | ", "dim")

    def join_row(cells: list[str]) -> str:
        return rule.join(cells)

    header_cells = [
        paint(header.ljust(widths[index]), "cyan") for index, header in enumerate(headers)
    ]
    out_lines = [sep_line, join_row(header_cells), sep_line]
    for name, ready, encryption in profiles:
        state = "yes" if ready else "no"
        state_colour = "green" if ready else "yellow"
        if encryption:
            enc_colour = "yellow" if encryption == "none" else "cyan"
            enc_cell = paint(encryption.ljust(widths[2]), enc_colour)
        else:
            enc_cell = "".ljust(widths[2])
        out_lines.append(
            join_row(
                [
                    name.ljust(widths[0]),
                    paint(state.ljust(widths[1]), state_colour),
                    enc_cell,
                ]
            )
        )
    out_lines.append(sep_line)
    return "\n".join(out_lines) + "\n"


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
        return paint("No tokens.", "cyan") + "\n"

    selected = columns if columns is not None else list(DEFAULT_COLUMNS)
    headers = [COLUMN_LABELS[key] for key in selected]
    rows_by_group: dict[str, list[list[str]]] = {}
    for token_type, group in group_by_type(tokens).items():
        ordered = sorted(group, key=lambda token: (token.name, token.updated_at))
        rows_by_group[token_type] = [
            [_cell(token, key, reveal=reveal) for key in selected] for token in ordered
        ]
    all_rows = [row for rows in rows_by_group.values() for row in rows]
    widths = _widths(headers, all_rows, max_width)
    total_width = sum(widths) + 3 * (len(widths) - 1)
    rule_width = total_width + 2
    sep_line = paint("-" * rule_width, "dim")
    title_colour = "yellow" if encryption == "none" else "cyan"

    rule = paint(" | ", "dim")

    def pad_row(cells: list[str], *, colour: str | None = None) -> str:
        parts: list[str] = []
        for index, cell in enumerate(cells):
            text = str(cell).ljust(widths[index])
            parts.append(paint(text, colour) if colour else text)
        return rule.join(parts)

    out_lines = [
        _center_in_rule(
            f"Profile: {profile} (enc: {encryption})",
            rule_width,
            title_colour,
            prefix="Profile:",
        ),
    ]
    header_line = pad_row(headers, colour="cyan")
    for index, (token_type, rows) in enumerate(rows_by_group.items()):
        if index:
            out_lines.append(sep_line)
        out_lines.append(
            _paint_prefix(_center(f"Token type: {token_type}", rule_width), "Token type:", "cyan")
        )
        out_lines.append(sep_line)
        out_lines.append(header_line)
        out_lines.append(sep_line)
        for row in rows:
            for line in _wrap_row(row, widths, wrap=max_width is not None):
                out_lines.append(pad_row(line))
    out_lines.append(sep_line)
    return "\n".join(out_lines) + "\n"
