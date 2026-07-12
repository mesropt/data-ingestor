"""Order-independent, duplicate-preserving column signature (LEARN-01, D-02).

Two files whose headers differ only in case, incidental whitespace, or
column ORDER must hash to the same signature -- but two files with a
different number of duplicate or blank headers must NOT: this signature's
job is to prove "the same columns, in some order", never "roughly the same
shape". A typo, a renamed column, or an added/removed column is a genuinely
different file layout and must yield a genuinely different signature (D-02,
D-05) -- over-normalising here is exactly the "wrong-file profile match
corrupts data" hazard the P1 binding principle exists to prevent.

Deliberately mirrors `fields/models.py::FieldSet.signature` -- this
project's one other content-addressed identity hash: normalise each item,
sort a LIST (never collapse into a `set` -- a set silently drops duplicate
or blank entries, corrupting the "column count defines the signature"
invariant D-02 requires), then `hashlib.sha256(json.dumps(...)).hexdigest()`.
`hash()` (the Python builtin) is never used here: it is salted per process
by `PYTHONHASHSEED` and would never reproduce across separate CLI
invocations, which is exactly when a save-time signature must match a
later lookup-time signature.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata


def column_signature(headers: list[str]) -> str:
    """An order-independent, duplicate-preserving hash of a file's headers.

    A sorted LIST of normalised headers, never a `set` (Pitfall 1) -- a
    `set` would silently collapse two blank or duplicate headers into one,
    corrupting the "column count defines the signature" invariant D-02
    requires. Computed identically at profile save-time and lookup-time
    (`learning/reconstruct.py` relies on this being bit-for-bit stable).
    """
    normalised = sorted(_normalise_header(h) for h in headers)
    digest = hashlib.sha256(json.dumps(normalised).encode("utf-8"))
    return digest.hexdigest()


def _normalise_header(header: str) -> str:
    """Unicode NFC + case-fold + trim + collapse internal whitespace (D-02 STRICT).

    NFC does not fold *meaning* -- it only canonicalises Unicode code-point
    sequences that render as the same visual character (e.g. an accented
    letter encoded as one code point vs. base+combining-accent), so two
    files with visually-identical headers never hash differently purely
    from an encoding artifact -- a false LEARN-05 format-drift signal,
    which D-02 exists to prevent, not cause. A typo or a genuinely
    different word is UNCHANGED by this function and still produces a
    different signature, exactly as D-02 requires.

    `casefold()`, not `.lower()`: the Unicode-correct choice (handles cases
    `.lower()` misses). `fields/models.py::_normalise_field` uses
    `.lower()` for field *names* only -- a deliberately weaker comparison
    this module does not need to match.
    """
    nfc = unicodedata.normalize("NFC", header)
    return " ".join(nfc.casefold().split())
