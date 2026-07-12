"""Rebuild a `MappingProposal` from a stored profile, resolved against the
NEW file's actual headers (LEARN-03, D-05) -- the P1 correctness core of the
learning loop.

Because the column signature is deliberately case/whitespace/order-tolerant
(D-02), a signature match does NOT guarantee any header in the new file is
byte-identical to the one the profile was saved against. `canonical.py`'s
existing `_column_index` resolves `FieldMapping.source_column` via
`table.headers.index(source_column)` -- an EXACT string match -- and must
NOT be reused here (Pitfall 2): doing so would silently and non-obviously
drop a column on any legitimately-matching file whose header casing or
incidental whitespace differs, while the reconstructed proposal is (by
D-05) built at confidence 1.0 / `needs_confirmation=False` -- i.e. exactly
the kind of wrong-or-missing-field-with-no-error P1 forbids.

`reconstruct_proposal` is a SIBLING of `mapping/mapper.py::propose_mapping`,
never a wrapper around it: it returns the same `MappingProposal` shape via a
completely different, client-free path, and constructs no `anthropic.Anthropic`
client at all (Pattern 5, Pitfall 3) -- this module has no Anthropic SDK
import.
"""

from __future__ import annotations

from collections import Counter

from ..domain.models import FieldMapping, MappingProposal
from .profile import LearnedProfile, StoredFieldMapping
from .signature import _normalise_header

_AUTO_APPLIED_REASONING = (
    "Auto-applied from a saved profile (D-08): this column matched a "
    "previously confirmed mapping for this exact column signature."
)

#: MAP-02/D-02b: a field the profile resolved to an INFERRED value, not a
#: column. The value is reproduced (a curator confirmed it once for exactly
#: this column signature -- i.e. for this lab's format, whose files carry no
#: such column at all -- and `canonical.assemble` now writes it to every row),
#: but it must never read as something the new file contained: it is stated as
#: inferred, so the curator confirming this file sees, before exporting
#: anything, that the tool is about to write a value no column here supplies.
#: The no-LLM validator still re-checks it against the field's declared
#: constraints on this branch too (D-03) -- a profile's confidence exempts
#: nothing.
_AUTO_APPLIED_INFERRED_REASONING = (
    "Auto-applied from a saved profile: no column in this file supplies this "
    "field, so the value a curator previously confirmed for this file format "
    "is INFERRED here -- {value!r}. It is not read from the file."
)

#: WR-01, P1 fail-closed: `column_signature` is order-independent (a sorted
#: multiset), while `_resolve_new_header` disambiguates same-normalised
#: (duplicate OR blank) headers by left-to-right occurrence rank, which IS
#: order-dependent. Two same-signature files can carry duplicate/blank
#: columns in a different physical order, so resolving one of these by
#: occurrence alone is not provably the same data column the profile was
#: saved against -- auto-apply must never clear this to confidence 1.0.
_AMBIGUOUS_DUPLICATE_REASONING = (
    "Auto-applied from a saved profile, but this header is not unique in "
    "the new file (duplicate or blank column name): the signature match "
    "cannot prove which physical column the profile's mapping refers to, "
    "so this field needs the curator's confirmation."
)


def reconstruct_proposal(profile: LearnedProfile, new_headers: list[str]) -> MappingProposal:
    """Rebuild the confirmed mapping at confidence 1.0 / `needs_confirmation`
    `False` (D-05) -- an exact column-signature match already proved the new
    file's headers are the same normalisation-tolerant multiset the profile
    was saved against; every stored column is resolved by NORMALISED
    equality (`_resolve_new_header`), never `headers.index()`.

    A stored column whose normalised header occurs more than once in
    `new_headers` (WR-01) is not safely disambiguated by occurrence rank
    alone -- that field is resolved (so its column is still shown) but
    fails closed to `needs_confirmation=True` rather than silently clearing.
    """
    occurrence_counts = Counter(_normalise_header(h) for h in new_headers)
    mappings = [
        _reconstruct_field(stored, new_headers, occurrence_counts)
        for stored in profile.field_mappings
    ]
    return MappingProposal(source_columns=list(new_headers), field_mappings=mappings)


def _reconstruct_field(
    stored: StoredFieldMapping, new_headers: list[str], occurrence_counts: Counter
) -> FieldMapping:
    source_column = _resolve_new_header(
        new_headers, stored.source_column_normalised, stored.source_column_occurrence
    )
    ambiguous = (
        stored.source_column_normalised is not None
        and occurrence_counts[stored.source_column_normalised] > 1
    )
    if ambiguous:
        return FieldMapping(
            target_field=stored.target_field,
            source_column=source_column,
            confidence=1.0,
            reasoning=_AMBIGUOUS_DUPLICATE_REASONING,
            needs_confirmation=True,
            inferred_value=stored.inferred_value,
        )
    return FieldMapping(
        target_field=stored.target_field,
        source_column=source_column,
        confidence=1.0,
        reasoning=_reasoning_for(source_column, stored.inferred_value),
        needs_confirmation=False,
        inferred_value=stored.inferred_value,
    )


def _reasoning_for(source_column: str | None, inferred_value: str | None) -> str:
    """Say which of the two inputs this replay actually resolved to -- the
    same precedence `canonical.value_source` enforces (a real column wins). The
    inferred branch names the value explicitly, because it is the one case
    where the tool writes something the file itself never said."""
    if source_column is None and inferred_value is not None:
        return _AUTO_APPLIED_INFERRED_REASONING.format(value=inferred_value)
    return _AUTO_APPLIED_REASONING


def _resolve_new_header(
    new_headers: list[str], normalised_source: str | None, occurrence: int
) -> str | None:
    """Find the new file's actual header string matching a stored
    `(normalised_header, occurrence_rank)` pair -- occurrence disambiguates
    duplicate/blank headers deterministically by left-to-right order
    (RESEARCH Pattern 4).
    """
    if normalised_source is None:
        return None
    seen = 0
    for header in new_headers:
        if _normalise_header(header) == normalised_source:
            if seen == occurrence:
                return header
            seen += 1
    return None  # an exact-signature match guarantees this should not happen


def stored_mapping_from(mapping: FieldMapping, headers: list[str]) -> StoredFieldMapping:
    """The save-side mirror of `_resolve_new_header` -- computed with the
    SAME `_normalise_header` function so save-time and apply-time agree
    bit-for-bit (the key_link invariant this module exists to protect: any
    divergence and auto-apply silently never fires, or resolves the wrong
    column).

    `mapping.source_column` is guaranteed to be an exact string from
    `headers` (the mapper only ever names a real header, or `None`), so
    `headers.index(...)` here is safe -- unlike at reconstruction time,
    where the new file's headers are a DIFFERENT list this string is not
    guaranteed to appear in verbatim.
    """
    if mapping.source_column is None:
        return StoredFieldMapping(
            target_field=mapping.target_field,
            source_column_normalised=None,
            source_column_occurrence=0,
            inferred_value=mapping.inferred_value,
        )
    normalised = _normalise_header(mapping.source_column)
    index = headers.index(mapping.source_column)
    occurrence = sum(1 for h in headers[:index] if _normalise_header(h) == normalised)
    return StoredFieldMapping(
        target_field=mapping.target_field,
        source_column_normalised=normalised,
        source_column_occurrence=occurrence,
        inferred_value=mapping.inferred_value,
    )
