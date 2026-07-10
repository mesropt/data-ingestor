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

from ..domain.models import FieldMapping, MappingProposal
from .profile import LearnedProfile, StoredFieldMapping
from .signature import _normalise_header

_AUTO_APPLIED_REASONING = (
    "Auto-applied from a saved profile (D-08): this column matched a "
    "previously confirmed mapping for this exact column signature."
)


def reconstruct_proposal(profile: LearnedProfile, new_headers: list[str]) -> MappingProposal:
    """Rebuild the confirmed mapping at confidence 1.0 / `needs_confirmation`
    `False` (D-05) -- an exact column-signature match already proved the new
    file's headers are the same normalisation-tolerant multiset the profile
    was saved against; every stored column is resolved by NORMALISED
    equality (`_resolve_new_header`), never `headers.index()`.
    """
    mappings = [_reconstruct_field(stored, new_headers) for stored in profile.field_mappings]
    return MappingProposal(source_columns=list(new_headers), field_mappings=mappings)


def _reconstruct_field(stored: StoredFieldMapping, new_headers: list[str]) -> FieldMapping:
    source_column = _resolve_new_header(
        new_headers, stored.source_column_normalised, stored.source_column_occurrence
    )
    return FieldMapping(
        target_field=stored.target_field,
        source_column=source_column,
        confidence=1.0,
        reasoning=_AUTO_APPLIED_REASONING,
        needs_confirmation=False,
        inferred_value=stored.inferred_value,
    )


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
