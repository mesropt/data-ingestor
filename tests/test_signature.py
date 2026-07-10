"""learning.signature -- order-independent, duplicate-preserving column
signature (LEARN-01, D-02). Written test-first (TDD RED)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from assayingest.learning.signature import column_signature
from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_signature_is_order_independent():
    assert column_signature(["b", "a"]) == column_signature(["a", "b"])


def test_signature_tolerates_case_whitespace_and_nfc():
    a = column_signature(["Compound ID"])
    b = column_signature(["compound id"])
    c = column_signature(["  compound   id "])
    assert a == b == c


def test_signature_never_collapses_duplicate_or_blank_headers():
    # D-02: column count defines the signature -- two blanks must NOT hash
    # the same as one blank (a `set()` would silently collapse them).
    two_blanks = column_signature(["A", "", ""])
    one_blank = column_signature(["A", ""])
    assert two_blanks != one_blank


def test_signature_never_collapses_duplicate_named_headers():
    assert column_signature(["A", "A"]) != column_signature(["A"])


def test_signature_is_stable_across_a_fresh_process():
    # LEARN-01: a profile saved in one CLI invocation must be found by a
    # lookup in the next -- hashlib.sha256, never the salted builtin hash().
    headers = ["Compound ID", "Assay", "", "Target"]
    in_process = column_signature(headers)
    code = (
        "from assayingest.learning.signature import column_signature; "
        f"print(column_signature({headers!r}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == in_process


def test_novascreen_batch01_and_batch02_share_a_signature():
    # The ready-made demo pair (byte-identical headers) -- the simplest
    # possible signature-match case.
    table1 = parse_file(DATA / "novascreen_batch01.csv")
    table2 = parse_file(DATA / "novascreen_batch02.csv")
    assert column_signature(table1.headers) == column_signature(table2.headers)
