"""Per-column date-order ambiguity predicate — detect, never convert (D-10-06/07).

The structural sibling of `structure/locale.py`'s decimal-comma predicate:
a column's date-component order can only be *proven* by evidence, never
guessed. `datetime.strptime("03/04/2025", "%m/%d/%Y")` does not raise even
when the true value is 3 April -- a successful parse is not the same as a
*correct* parse. The only real evidence available is a component that
cannot possibly be a month: any value with a first or second numeric
component > 12 proves the column's order outright. A column where every
value's two leading components are both <= 12 has no such evidence and is
genuinely AMBIGUOUS -- it must be asked about once, never inferred (D-10-07).

Unlike `locale.py`'s decimal-comma rule -- which genuinely needs *several*
values to disambiguate (a lone 3-digit comma group can never prove
anything) -- a SINGLE asymmetric date value is sufficient evidence on its
own: `"13/07/2026"` alone proves DAY_FIRST because 13 cannot be a month.
locale.py's Pitfall-7 "a single-value column is always ambiguous" special
case does NOT apply here and is deliberately not ported.

Excel-serial dates (a raw int/float like `46092` for a cell whose
`number_format` was never recognised as a date) convert through
`openpyxl.utils.datetime.from_excel`, never a hand-rolled 1900-epoch
formula -- openpyxl already encodes the Lotus 1-2-3 leap-year-bug
compensation correctly. This module assumes the standard 1900 epoch system
(correct for every fixture in this project's corpus); a 1904-epoch
workbook (old Mac Excel) would convert roughly 4 years off, and `RawTable`
carries no workbook-epoch flag to disambiguate -- a known, documented
limitation, not a silent gap. A defensive plausible-date range (~1970-2100)
rejects anything wildly implausible rather than emitting a garbage date.

No `dateutil` anywhere in this module: `dateutil.parser` guesses an order
by design when a string is ambiguous, which is precisely the failure mode
this module exists to eliminate. Explicit candidate-format templates +
`datetime.strptime` only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from openpyxl.utils.datetime import from_excel

#: The sane range a bare integer must fall in to be treated as a plausible
#: Excel date serial rather than an arbitrary number. Corresponds to
#: 1970-01-01 (serial 25569) through 2099-12-31 (serial 73050) under the
#: standard 1900-epoch system -- computed directly via
#: `openpyxl.utils.datetime.to_excel`, not guessed. A bare int outside this
#: range (e.g. "5", "900000") is not date-shaped enough to call
#: EXCEL_SERIAL; it falls through to NON_DATE so the caller flags the field
#: instead of silently emitting a date in 1900 or 4370 (10-RESEARCH.md
#: Pitfall 2 / Assumption A2).
_EXCEL_SERIAL_MIN = 25569
_EXCEL_SERIAL_MAX = 73050

#: Sentinel a resolved-format dict/field can carry for an Excel-serial
#: column, so a caller (e.g. `canonical.py`) can branch on it without
#: importing `DateOrder` at all.
EXCEL_SERIAL_MARKER = "excel_serial"

#: A non-ISO, separator-delimited two-component date: `03/11/2025`,
#: `1/2/25`, `07/14/26 13:44`. Components are 1-2 digits (no zero-padding
#: assumed); the year is 2 or 4 digits; an optional time suffix carries
#: either `HH:MM` or `HH:MM:SS`.
_DM_RE = re.compile(
    r"^(\d{1,2})([/\-.])(\d{1,2})\2(\d{2}|\d{4})"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

#: A leading-4-digit-year, separator-delimited date: `2025-01-01`,
#: `2025-01-01 00:00:00`. Order is never ambiguous for this shape.
_ISO_RE = re.compile(
    r"^(\d{4})([/\-.])(\d{1,2})\2(\d{1,2})"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

#: A bare 8-digit compact date (`20250101`) -- order fixed by convention.
_ISO_COMPACT_RE = re.compile(r"^(\d{8})$")

#: A bare integer -- either an Excel serial candidate or nothing date-shaped.
_BARE_INT_RE = re.compile(r"^\d+$")

#: How many raw example values `classify_column` keeps for the evidence panel.
_EXAMPLE_LIMIT = 3


class DateOrder(str, Enum):
    """The outcome of classifying one column's date-order evidence."""

    DAY_FIRST = "day_first"
    MONTH_FIRST = "month_first"
    ISO = "iso"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    NON_DATE = "non_date"
    EXCEL_SERIAL = "excel_serial"


@dataclass(frozen=True)
class DateColumnFormat:
    """One column's date-order verdict, with enough evidence to act on it.

    `date_format` is the resolved strptime format when the order is
    provably DAY_FIRST/MONTH_FIRST/ISO, `EXCEL_SERIAL_MARKER` when
    EXCEL_SERIAL, and `None` for AMBIGUOUS/INVALID/NON_DATE (nothing to
    convert with yet). `day_first_format`/`month_first_format` are
    populated ONLY when `order` is AMBIGUOUS -- the two options a human
    picks between; `format_for_order` reads them to resolve an answer.
    """

    order: DateOrder
    date_format: str | None
    day_first_format: str | None = None
    month_first_format: str | None = None
    example_values: tuple[str, ...] = ()


def classify_column(values: list[str]) -> DateColumnFormat:
    """Classify one column's date order from the evidence across its values.

    Non-date-shaped values (blanks, or cells that match no known date
    shape at all) are ignored -- the order is derived only from the values
    that look like a date; the validator flags an individual bad cell
    independently of this column-level classification.
    """
    cleaned = [v.strip() for v in values if v.strip()]
    if not cleaned:
        return _non_date_result(cleaned)

    iso_values, compact_values, dm_values, bare_int_values = _shape_values(cleaned)

    if iso_values or compact_values:
        return _classify_iso(iso_values, compact_values, cleaned)
    if dm_values:
        return _classify_dm(dm_values, cleaned)
    if bare_int_values:
        return _classify_bare_int(bare_int_values, cleaned)
    return _non_date_result(cleaned)


def implied_order(date_format: str) -> DateOrder | None:
    """What component order a strptime format string implies.

    Returns `None` when the format carries no date components at all
    (e.g. `"%H:%M"`) -- there is no order to imply, so there is nothing to
    compare a column's evidence against.
    """
    has_day = "%d" in date_format
    has_month = "%m" in date_format
    if not has_day and not has_month:
        return None
    if date_format.startswith("%Y"):
        return DateOrder.ISO
    if has_day and has_month:
        return DateOrder.DAY_FIRST if date_format.index("%d") < date_format.index("%m") else DateOrder.MONTH_FIRST
    return None


def iso_from_excel_serial(raw: str) -> str | None:
    """Convert a raw Excel date serial to an ISO date, or `None`.

    `None` covers both "not a bare integer at all" and "a bare integer
    outside the plausible 1970-2100 range" -- the caller flags the field
    in both cases rather than trusting an implausible converted date.
    """
    raw = raw.strip()
    if not _BARE_INT_RE.match(raw):
        return None
    serial = int(raw)
    if not (_EXCEL_SERIAL_MIN <= serial <= _EXCEL_SERIAL_MAX):
        return None
    return from_excel(serial).date().isoformat()


def parses_all(values: list[str], date_format: str) -> bool:
    """Whether EVERY non-blank value in `values` parses under `date_format`.

    This is the only evidence that can (fail to) refute a declared
    `date_format` (D-10-06/quick-260712-qgc): a clean parse of every value
    does NOT prove the format is CORRECT -- the module docstring's own
    `03/04/2025` warning still stands, a format can parse every row and
    still silently pick the wrong order. It only proves the data cannot
    REFUTE the declaration, which is the sole question a caller deciding
    whether to trust a human's claim needs answered. Blank values are
    ignored (strip-and-drop), mirroring `classify_column`'s own cleaning
    rule, so a column with blank cells is never falsely refuted.
    """
    cleaned = [v.strip() for v in values if v.strip()]
    try:
        for value in cleaned:
            datetime.strptime(value, date_format)
    except ValueError:
        return False
    return True


def format_for_order(column: DateColumnFormat, order: DateOrder) -> str:
    """Turn a human's day-first/month-first answer into this column's own
    concrete strptime format -- mirrors `locale.resolve_ambiguity`.

    Returns the format matching the COLUMN's own separator/year-width
    (never a hardcoded `%d/%m/%Y`), so an ambiguous `1/2/25` column
    resolved day-first yields `%d/%m/%y`. Raises `ValueError` naming the
    consequence when `column` was never AMBIGUOUS (no candidate formats to
    choose between) or `order` is not one its two candidates.
    """
    if order == DateOrder.DAY_FIRST and column.day_first_format:
        return column.day_first_format
    if order == DateOrder.MONTH_FIRST and column.month_first_format:
        return column.month_first_format
    raise ValueError(
        f"Cannot resolve this column's date order to '{order}': the column has no "
        "matching candidate format (it was not classified AMBIGUOUS, or the answer "
        "was neither day_first nor month_first)."
    )


def _shape_values(
    cleaned: list[str],
) -> tuple[list[tuple[str, re.Match]], list[str], list[tuple[str, re.Match]], list[str]]:
    """Bucket every cleaned value by the one date shape it matches, if any."""
    iso_values: list[tuple[str, re.Match]] = []
    compact_values: list[str] = []
    dm_values: list[tuple[str, re.Match]] = []
    bare_int_values: list[str] = []

    for value in cleaned:
        iso_match = _ISO_RE.match(value)
        if iso_match:
            iso_values.append((value, iso_match))
            continue
        compact_match = _ISO_COMPACT_RE.match(value)
        if compact_match and _plausible_year(int(value[:4])):
            compact_values.append(value)
            continue
        dm_match = _DM_RE.match(value)
        if dm_match:
            dm_values.append((value, dm_match))
            continue
        if _BARE_INT_RE.match(value):
            bare_int_values.append(value)

    return iso_values, compact_values, dm_values, bare_int_values


def _plausible_year(year: int) -> bool:
    return 1900 <= year <= 2100


def _classify_iso(
    iso_values: list[tuple[str, re.Match]], compact_values: list[str], cleaned: list[str]
) -> DateColumnFormat:
    """ISO-shaped columns carry no order ambiguity -- only validate the
    resolved format actually parses every ISO-shaped value."""
    date_format = _iso_format_from_match(iso_values[0][1]) if iso_values else "%Y%m%d"
    date_shaped = [v for v, _ in iso_values] + compact_values
    if not parses_all(date_shaped, date_format):
        return DateColumnFormat(order=DateOrder.INVALID, date_format=None, example_values=_examples(cleaned))
    return DateColumnFormat(order=DateOrder.ISO, date_format=date_format, example_values=_examples(cleaned))


def _iso_format_from_match(match: re.Match) -> str:
    sep = match.group(2)
    return f"%Y{sep}%m{sep}%d{_time_suffix(match, start=5)}"


def _classify_dm(dm_values: list[tuple[str, re.Match]], cleaned: list[str]) -> DateColumnFormat:
    """Apply the evidence rule: a component > 12 proves the order; no
    component ever exceeding 12 anywhere is genuinely AMBIGUOUS."""
    sep, year_format, time_suffix = _dm_shape(dm_values[0][1])
    day_first_format = f"%d{sep}%m{sep}{year_format}{time_suffix}"
    month_first_format = f"%m{sep}%d{sep}{year_format}{time_suffix}"

    first_over = any(int(match.group(1)) > 12 for _, match in dm_values)
    second_over = any(int(match.group(3)) > 12 for _, match in dm_values)
    date_shaped = [v for v, _ in dm_values]
    example_values = _examples(cleaned)

    if first_over and second_over:
        return DateColumnFormat(order=DateOrder.INVALID, date_format=None, example_values=example_values)
    if first_over:
        return _resolved_dm_result(DateOrder.DAY_FIRST, day_first_format, date_shaped, example_values)
    if second_over:
        return _resolved_dm_result(DateOrder.MONTH_FIRST, month_first_format, date_shaped, example_values)
    return DateColumnFormat(
        order=DateOrder.AMBIGUOUS,
        date_format=None,
        day_first_format=day_first_format,
        month_first_format=month_first_format,
        example_values=example_values,
    )


def _resolved_dm_result(
    order: DateOrder, date_format: str, date_shaped: list[str], example_values: tuple[str, ...]
) -> DateColumnFormat:
    """A proven order's format must actually parse every value before it is
    trusted -- if it doesn't, the column is not confidently that format."""
    if not parses_all(date_shaped, date_format):
        return DateColumnFormat(order=DateOrder.INVALID, date_format=None, example_values=example_values)
    return DateColumnFormat(order=order, date_format=date_format, example_values=example_values)


def _dm_shape(match: re.Match) -> tuple[str, str, str]:
    sep = match.group(2)
    year_format = "%Y" if len(match.group(4)) == 4 else "%y"
    return sep, year_format, _time_suffix(match, start=5)


def _time_suffix(match: re.Match, *, start: int) -> str:
    groups = match.groups()
    hour_idx, minute_idx, second_idx = start - 1, start, start + 1
    if len(groups) <= minute_idx or groups[hour_idx] is None:
        return ""
    if len(groups) > second_idx and groups[second_idx] is not None:
        return " %H:%M:%S"
    return " %H:%M"


def _classify_bare_int(bare_int_values: list[str], cleaned: list[str]) -> DateColumnFormat:
    """All-bare-integer columns: EXCEL_SERIAL only when every value falls in
    the plausible serial range; otherwise nothing date-shaped is proven."""
    if all(_EXCEL_SERIAL_MIN <= int(v) <= _EXCEL_SERIAL_MAX for v in bare_int_values):
        return DateColumnFormat(
            order=DateOrder.EXCEL_SERIAL, date_format=EXCEL_SERIAL_MARKER, example_values=_examples(cleaned)
        )
    return _non_date_result(cleaned)


def _non_date_result(cleaned: list[str]) -> DateColumnFormat:
    return DateColumnFormat(order=DateOrder.NON_DATE, date_format=None, example_values=_examples(cleaned))


def _examples(cleaned: list[str]) -> tuple[str, ...]:
    return tuple(cleaned[:_EXAMPLE_LIMIT])
