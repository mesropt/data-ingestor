"""Per-column date-order ambiguity predicate — detect, never guess (D-10-06/07).

The structural sibling of `structure/locale.py`'s decimal-comma predicate:
order is proven only by a component > 12 somewhere in a column, or the
column is genuinely AMBIGUOUS and must ask a human once. Unlike the decimal
locale case, a SINGLE asymmetric value is sufficient evidence for a date
order (locale.py's Pitfall-7 "single value = ambiguous" rule does NOT
apply here — see `test_single_asymmetric_value_is_unambiguous_...` below).

Every concrete date value asserted in this file was read from a real
fixture in this repo (10-RESEARCH.md's "verified ambiguity examples"
section, executed against the actual files) — none are invented.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from assayingest.parsing.structure import date_order
from assayingest.parsing.structure.date_order import (
    EXCEL_SERIAL_MARKER,
    DateColumnFormat,
    DateOrder,
    classify_column,
    format_for_order,
    implied_order,
    iso_from_excel_serial,
)

# --- AMBIGUOUS: the fail-closed case (D-10-07) -------------------------------


def test_helixbio_experiment_date_is_ambiguous_and_names_both_formats():
    # data/synthetic/helixbio_export.csv, column "Experiment Date"
    values = ["03/11/2025", "03/11/2025", "04/11/2025", "05/11/2025"]
    result = classify_column(values)
    assert result.order == DateOrder.AMBIGUOUS
    assert result.date_format is None
    assert result.day_first_format == "%d/%m/%Y"
    assert result.month_first_format == "%m/%d/%Y"


def test_summit_discovery_unpadded_single_digit_is_ambiguous():
    # data/synthetic/summit_discovery_mixed.xlsx, column "date" (unpadded variant) --
    # pins that the detector does not depend on zero-padding.
    values = ["1/1/2025", "1/2/2025", "1/3/2025", "1/7/2025"]
    result = classify_column(values)
    assert result.order == DateOrder.AMBIGUOUS
    assert result.day_first_format == "%d/%m/%Y"
    assert result.month_first_format == "%m/%d/%Y"


# --- UNAMBIGUOUS by a component > 12 -----------------------------------------


def test_meridian_dt_is_unambiguous_day_first():
    # data/synthetic/meridian_cro_codes.xlsx, sheet "DATA", column "DT" -- "21" proves it.
    values = ["01-01-2025", "03-01-2025", "21-01-2025"]
    result = classify_column(values)
    assert result.order == DateOrder.DAY_FIRST
    assert result.date_format == "%d-%m-%Y"


def test_pinnacle_date_is_unambiguous_day_first():
    # data/synthetic/pinnacle_labs_export.csv, column "Date" -- "13" proves it.
    values = ["01/01/2025", "13/01/2025", "14/01/2025"]
    result = classify_column(values)
    assert result.order == DateOrder.DAY_FIRST
    assert result.date_format == "%d/%m/%Y"


def test_quill_reported_two_digit_year_with_time_is_month_first_from_single_value():
    # data/synthetic/lab_corpus/quill_coag_QF2630229.xlsx, "Reported" -- one value,
    # two-digit year AND a time suffix: "14" as the second component proves MONTH_FIRST.
    values = ["07/14/26 13:44"]
    result = classify_column(values)
    assert result.order == DateOrder.MONTH_FIRST
    assert result.date_format == "%m/%d/%y %H:%M"


def test_single_asymmetric_value_is_unambiguous_unlike_locale_pitfall_7():
    """The single-value rule -- explicitly NOT locale.py's Pitfall 7.

    A lone 3-digit comma group can never disambiguate a decimal (locale.py
    treats a single value as AMBIGUOUS). A lone asymmetric date value IS
    sufficient evidence: "13" cannot be a month, so `13/07/2026` alone
    proves DAY_FIRST even though the column has exactly one row.
    """
    # data/synthetic/lab_corpus/quill_coag_QF2630229.xlsx, "Received" (genuinely one value)
    values = ["13/07/2026"]
    result = classify_column(values)
    assert result.order == DateOrder.DAY_FIRST
    assert result.date_format == "%d/%m/%Y"


# --- ISO / no order ambiguity at all -----------------------------------------


def test_castlebio_native_datetime_string_is_iso():
    # data/synthetic/castlebio_native_dates.xlsx, "Tested On" -- the str(datetime)
    # shape BOTH the openpyxl and pandas paths produce (10-RESEARCH Pitfall 1).
    values = ["2025-01-01 00:00:00", "2025-01-02 00:00:00"]
    result = classify_column(values)
    assert result.order == DateOrder.ISO
    assert result.date_format == "%Y-%m-%d %H:%M:%S"


def test_bare_iso_date_is_iso():
    values = ["2025-01-01", "2025-02-14"]
    result = classify_column(values)
    assert result.order == DateOrder.ISO
    assert result.date_format == "%Y-%m-%d"


def test_cascade_compact_eight_digit_is_iso():
    # data/synthetic/cascade_assays_nounit.xlsx, column "run"
    values = ["20250101", "20250102", "20250103"]
    result = classify_column(values)
    assert result.order == DateOrder.ISO
    assert result.date_format == "%Y%m%d"


# --- EXCEL_SERIAL (D-10-08) ---------------------------------------------------


def test_excel_serial_column_is_recognized():
    values = ["46092", "46093"]
    result = classify_column(values)
    assert result.order == DateOrder.EXCEL_SERIAL
    assert result.date_format == EXCEL_SERIAL_MARKER


def test_iso_from_excel_serial_converts_a_real_serial():
    # data/synthetic/lab_corpus/wild/10_genelab_date_disaster.xlsx, row 6 "Collection Date"
    assert iso_from_excel_serial("46092") == "2026-03-11"


def test_iso_from_excel_serial_rejects_a_value_far_below_the_sane_range():
    assert iso_from_excel_serial("5") is None


def test_iso_from_excel_serial_rejects_a_value_far_above_the_sane_range():
    assert iso_from_excel_serial("900000") is None


def test_classify_column_does_not_call_a_bare_int_excel_serial_outside_the_sane_range():
    """A serial outside the defensive plausible range is not date-shaped
    enough to call EXCEL_SERIAL -- it falls through to NON_DATE so the caller
    flags the field instead of ever computing a year-1900 or year-4370 date."""
    assert classify_column(["5"]).order == DateOrder.NON_DATE
    assert classify_column(["900000"]).order == DateOrder.NON_DATE


# --- NON_DATE / INVALID -------------------------------------------------------


def test_non_date_column_of_gene_symbols():
    result = classify_column(["EGFR", "JAK2"])
    assert result.order == DateOrder.NON_DATE


def test_empty_column_is_non_date():
    assert classify_column([]).order == DateOrder.NON_DATE


def test_blank_only_column_is_non_date():
    assert classify_column(["", "  "]).order == DateOrder.NON_DATE


def test_both_components_over_twelve_is_invalid_under_either_order():
    result = classify_column(["25/25/2025"])
    assert result.order == DateOrder.INVALID


def test_invalid_is_distinguishable_from_ambiguous_and_never_asked_about():
    """INVALID (no valid interpretation under either order) must never be
    confused with AMBIGUOUS (both interpretations are valid, order unknown):
    an INVALID column is flagged; an AMBIGUOUS column is asked about."""
    invalid = classify_column(["25/25/2025"])
    ambiguous = classify_column(["03/11/2025", "04/11/2025"])
    assert invalid.order != ambiguous.order
    assert invalid.order == DateOrder.INVALID
    assert ambiguous.order == DateOrder.AMBIGUOUS


def test_mixed_column_classifies_from_the_date_shaped_values_ignoring_the_rest():
    # Design choice (stated here per Task 1's instruction): a non-date-shaped
    # cell in an otherwise date-shaped column is ignored by the classifier --
    # the validator flags that individual bad cell independently; the column
    # order is derived only from values that look like a date at all.
    result = classify_column(["03/11/2025", "not a date"])
    assert result.order == DateOrder.AMBIGUOUS


# --- implied_order(date_format) -- the D-10-06 comparison primitive ----------


def test_implied_order_day_first_format():
    assert implied_order("%d/%m/%Y") == DateOrder.DAY_FIRST


def test_implied_order_month_first_format():
    assert implied_order("%m/%d/%Y") == DateOrder.MONTH_FIRST


def test_implied_order_iso_dashed_format():
    assert implied_order("%Y-%m-%d") == DateOrder.ISO


def test_implied_order_iso_compact_format():
    assert implied_order("%Y%m%d") == DateOrder.ISO


def test_implied_order_with_no_date_components_is_pinned_to_none():
    # No %d/%m at all -- there is no order to imply. Pinned to None.
    assert implied_order("%H:%M") is None


# --- THE DANGEROUS TEST: D-10-06's whole reason for existing -----------------


def test_a_declared_format_can_be_contradicted_by_evidence_even_when_every_row_parses():
    """`strptime` succeeding is not the same as a declared format being correct.

    (a) pinnacle's provably day-first data: a naive "did it parse?" check
    WOULD catch this one -- `strptime("13/01/2025", "%m/%d/%Y")` raises
    because 13 is not a valid month.

    (b) `classify_column`'s own proof -- the "21" in this column -- is
    independent of whether any particular strptime call happens to raise.
    Every value here parses cleanly under the column's own (correct)
    `%d/%m/%Y` format, and the classifier still proves DAY_FIRST from the
    21; comparing that against a wrongly-declared `%m/%d/%Y`'s implied
    order is what actually catches the mismatch (not a parse-failure scan).
    """
    with pytest.raises(ValueError):
        datetime.strptime("13/01/2025", "%m/%d/%Y")

    values = ["03/04/2025", "05/06/2025", "21/07/2025"]
    column = classify_column(values)
    assert column.order == DateOrder.DAY_FIRST

    for value in values:
        datetime.strptime(value, "%d/%m/%Y")  # must not raise -- correct order

    assert implied_order("%m/%d/%Y") != column.order


# --- format_for_order(column, order) -- mirrors locale.py's resolve_ambiguity -


def test_format_for_order_resolves_day_first_matching_the_columns_own_shape():
    """The resolved format must match the column's OWN separator/year-width,
    never a hardcoded `%d/%m/%Y` -- an ambiguous 2-digit-year column resolved
    day-first must yield `%d/%m/%y`, not `%d/%m/%Y`."""
    column = classify_column(["1/2/25", "2/3/25", "3/4/25"])
    assert column.order == DateOrder.AMBIGUOUS
    assert format_for_order(column, DateOrder.DAY_FIRST) == "%d/%m/%y"


def test_format_for_order_resolves_month_first_matching_the_columns_own_shape():
    column = classify_column(["1/2/25", "2/3/25", "3/4/25"])
    assert format_for_order(column, DateOrder.MONTH_FIRST) == "%m/%d/%y"


def test_format_for_order_raises_naming_the_consequence_on_a_non_ambiguous_column():
    column = classify_column(["01-01-2025", "21-01-2025"])  # already DAY_FIRST, not ambiguous
    with pytest.raises(ValueError):
        format_for_order(column, DateOrder.MONTH_FIRST)


# --- parses_all(values, date_format) -- the D-10-06 "check before trust" primitive


def test_parses_all_is_false_when_the_declared_format_cannot_parse_the_values():
    # quick-260712-qgc: the exact stale-preset-vs-real-data mismatch that
    # caused the Confirm dead-end -- "%Y-%m-%d" cannot parse "03/11/2025".
    assert date_order.parses_all(["03/11/2025"], "%Y-%m-%d") is False


def test_parses_all_is_true_when_the_declared_format_parses_every_value():
    assert date_order.parses_all(["03/11/2025", "04/11/2025"], "%d/%m/%Y") is True


def test_parses_all_ignores_blank_values_like_classify_column_does():
    assert date_order.parses_all(["03/11/2025", "", "  ", "04/11/2025"], "%d/%m/%Y") is True


# --- Public-surface sanity ----------------------------------------------------


def test_date_order_enum_has_every_required_member():
    names = {member.name for member in DateOrder}
    assert names == {
        "DAY_FIRST",
        "MONTH_FIRST",
        "ISO",
        "AMBIGUOUS",
        "INVALID",
        "NON_DATE",
        "EXCEL_SERIAL",
    }


def test_date_column_format_carries_example_values():
    result = classify_column(["03/11/2025", "04/11/2025", "05/11/2025", "06/11/2025"])
    assert isinstance(result, DateColumnFormat)
    assert result.example_values == ("03/11/2025", "04/11/2025", "05/11/2025")
