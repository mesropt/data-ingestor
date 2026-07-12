"""The "wild" corpus — real lab-interchange formats, most of them out of scope.

`data/synthetic/lab_corpus/wild/` holds the formats a lab actually emits into
the world: HL7 v2, ASTM/LIS2-A2, FHIR R4 JSON, CDA XML, an HTML report, a PDF,
a fixed-width text dump, a ZIP batch — and, mixed in, genuinely messy `.xlsx`
and `.csv` files. Ground truth is in `manifest_wild.json` / `MAP_wild.md`.

Data Ingestor ingests spreadsheets, by deliberate scope: a data curator's job is
reformatting the Excel/CSV a CRO hands them, not decoding machine-to-machine
interchange. These tests pin both halves of that decision:

  * An unsupported format is REFUSED with a named error that says what the tool
    accepts — never parsed on a guess, never crashed on a traceback.
  * A supported spreadsheet, however messy, resolves to a table, a structural
    question, or a named error — the same D-05 invariant the rest of the corpus
    holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest.parsing.hint import StructureQuestion
from assayingest.parsing.table import RawTable, parse

_WILD = Path("data/synthetic/lab_corpus/wild")

#: Formats Data Ingestor does not ingest. Each must be refused, not read.
_UNSUPPORTED_SUFFIXES = {".hl7", ".txt", ".json", ".xml", ".html", ".pdf", ".zip"}
#: The only formats in scope.
_SUPPORTED_SUFFIXES = {".xlsx", ".csv"}


def _wild(suffixes: set[str]) -> list[Path]:
    return sorted(
        p for p in _WILD.iterdir() if p.suffix.lower() in suffixes
    )


def test_the_wild_corpus_is_present():
    assert len(_wild(_UNSUPPORTED_SUFFIXES)) >= 8
    assert len(_wild(_SUPPORTED_SUFFIXES)) >= 8


@pytest.mark.parametrize(
    "path", _wild(_UNSUPPORTED_SUFFIXES), ids=lambda p: p.name
)
def test_an_unsupported_interchange_format_is_named_not_parsed(path: Path):
    """HL7, FHIR, CDA, HTML, PDF, fixed-width, ZIP: out of scope. The tool must
    say so in a message a curator can act on, not silently parse a fragment of
    it as if it were a table."""
    with pytest.raises(ValueError) as excinfo:
        parse(path)

    message = str(excinfo.value)
    assert message.startswith("Cannot ingest")
    assert ".csv" in message and ".xlsx" in message, (
        f"{path.name}: refusal should name what the tool does accept: {message!r}"
    )


@pytest.mark.parametrize(
    "path", _wild(_SUPPORTED_SUFFIXES), ids=lambda p: p.name
)
def test_a_supported_spreadsheet_never_leaks_a_raw_exception(path: Path):
    """The messy .xlsx/.csv files carry Excel error strings, NBSP-glued units,
    homoglyph headers, sep= hints. However they resolve, they never crash the
    tool with a library traceback (D-05)."""
    try:
        result = parse(path)
    except (ValueError, FileNotFoundError) as named:
        assert str(named).startswith("Cannot ingest") or str(named).startswith(
            "Cannot load"
        ), f"{path.name}: error does not name the consequence: {named}"
        return

    assert isinstance(result, (RawTable, StructureQuestion))
