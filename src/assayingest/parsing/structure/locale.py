"""Per-column decimal-locale annotation — detect, never convert (D-12/D-15).

A column's decimal separator can only be inferred from *variance* across its
values, never from a single cell in isolation (01-RESEARCH.md Pattern 3,
Pitfall 7): thousands-grouping commas are always followed by exactly 3
digits, every time, with no exceptions, so a column that ever shows 1, 2, or
4+ digits after a comma cannot be pure thousands-grouping and is confidently
`decimal_comma`. A column where every comma group is exactly 3 digits (or
which mixes dot-decimal and comma-decimal notation) is genuinely ambiguous
and must be flagged, never guessed (D-14).
"""

from __future__ import annotations

import re

from ..hint import NumericLocale

#: The comma is the LAST separator seen — "1.234,56" reads as digits-after-
#: last-comma = "56", correctly ignoring a "." thousands separator without
#: any special-casing.
_COMMA_DECIMAL = re.compile(r"^-?\d[\d.]*,(\d+)$")
_DOT_DECIMAL = re.compile(r"^-?\d+\.\d+$")
_PLAIN_INT = re.compile(r"^-?\d+$")


def classify_column(values: list[str]) -> NumericLocale:
    """Classify one column's decimal locale from the variance across its values.

    Never per-cell (D-13) — a single 3-digit-group value has no way to
    disambiguate itself and is treated as ambiguous, not as evidence.
    """
    cleaned = [v.strip() for v in values if v.strip()]
    if not cleaned or _all_non_numeric(cleaned):
        return NumericLocale.NON_NUMERIC

    has_comma_decimal, comma_digit_counts = _scan_comma_decimals(cleaned)
    has_dot_decimal = any(_DOT_DECIMAL.match(v) for v in cleaned)
    return _resolve_locale(has_comma_decimal, comma_digit_counts, has_dot_decimal)


def annotate_columns(headers: list[str], rows: list[list[str]]) -> list[NumericLocale]:
    """One locale per column, read down the column across all data rows."""
    return [
        classify_column([row[i] for row in rows if i < len(row)])
        for i in range(len(headers))
    ]


def _scan_comma_decimals(values: list[str]) -> tuple[bool, set[int]]:
    """Find every value that reads as comma-decimal and count digits after it."""
    digit_counts: set[int] = set()
    found = False
    for v in values:
        match = _COMMA_DECIMAL.match(v)
        if match:
            found = True
            digit_counts.add(len(match.group(1)))
    return found, digit_counts


def _all_non_numeric(values: list[str]) -> bool:
    """True only when not one value looks like a number in any known notation."""
    return all(
        not (_COMMA_DECIMAL.match(v) or _DOT_DECIMAL.match(v) or _PLAIN_INT.match(v))
        for v in values
    )


def _resolve_locale(
    has_comma_decimal: bool, comma_digit_counts: set[int], has_dot_decimal: bool
) -> NumericLocale:
    """Apply the ambiguity rule: variance proves a decimal, uniformity doesn't."""
    if has_dot_decimal and has_comma_decimal:
        return NumericLocale.AMBIGUOUS  # mixed notation within one column
    if has_comma_decimal and comma_digit_counts == {3}:
        return NumericLocale.AMBIGUOUS  # every comma group is exactly 3 digits
    if has_comma_decimal:
        return NumericLocale.DECIMAL_COMMA
    return NumericLocale.DECIMAL_POINT  # dot-decimal or pure integers
