"""The parser, run against a large corpus of messy synthetic lab reports.

`data/synthetic/lab_corpus/` holds 30 documented vendor files plus an `edge/`
folder of deliberate parser-killers (legacy binary .xls, wrong encodings,
ragged rows, zero-byte files, header-only files). Ground truth for the
quirks lives beside them in `manifest.json` / `MAP.md`.

The load-bearing invariant this file pins is Phase 1's D-05: **structural
uncertainty is a returned `StructureQuestion`, and a broken or unsupported
file is a named `ValueError` — never a raw exception leaking from pandas,
openpyxl or the csv module.** A stranger's file must never crash the tool
with a traceback the curator cannot act on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest.parsing.hint import StructureQuestion
from assayingest.parsing.table import RawTable, parse

_CORPUS = Path("data/synthetic/lab_corpus")
_READABLE_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv", ".txt"}


def _corpus_files() -> list[Path]:
    return sorted(
        path
        for path in _CORPUS.rglob("*")
        if path.suffix.lower() in _READABLE_SUFFIXES
    )


def test_the_corpus_is_present():
    files = _corpus_files()
    assert len(files) >= 50, f"expected the full lab corpus, found {len(files)}"


@pytest.mark.parametrize("path", _corpus_files(), ids=lambda p: str(p.relative_to(_CORPUS)))
def test_parse_never_raises_a_raw_exception(path: Path):
    """Whatever the file throws at it, `parse()` resolves to a table, a
    question, or a message a human can read — not a leaked library traceback.
    """
    try:
        result = parse(path)
    except (ValueError, FileNotFoundError) as named:
        message = str(named)
        assert message.startswith("Cannot ingest") or message.startswith(
            "Cannot load"
        ), f"{path.name}: error does not name the consequence: {message!r}"
        return

    assert isinstance(result, (RawTable, StructureQuestion)), (
        f"{path.name}: parse() returned {type(result).__name__}, "
        "expected RawTable or StructureQuestion"
    )
