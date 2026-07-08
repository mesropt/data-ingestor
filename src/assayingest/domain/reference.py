"""Reference dictionary — the allowed vocabulary, defined without any LLM.

This is the ground truth the mapper's proposals are checked against. It is a
plain data structure on purpose: Claude proposes a mapping, and this dictionary
(not another model) says what a valid assay type and unit look like.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssayType:
    """One allowed assay type and the units that are physically compatible."""

    canonical: str
    compatible_units: tuple[str, ...]
    #: Lower-cased spellings a CRO might use for this type, normalised on match.
    aliases: tuple[str, ...] = ()


#: Concentration-style potencies share the same unit set.
_CONCENTRATION_UNITS = ("µM", "nM")

ASSAY_TYPES: tuple[AssayType, ...] = (
    AssayType("IC50", _CONCENTRATION_UNITS, aliases=("ic50", "ic-50")),
    AssayType("EC50", _CONCENTRATION_UNITS, aliases=("ec50", "ec-50")),
    AssayType("Ki", _CONCENTRATION_UNITS, aliases=("ki",)),
    AssayType("Kd", _CONCENTRATION_UNITS, aliases=("kd",)),
    AssayType(
        "%inhibition",
        ("%",),
        aliases=("inhibition %", "% inhibition", "percent inhibition", "inhibition"),
    ),
)

ALLOWED_UNITS: tuple[str, ...] = ("µM", "nM", "%")

#: Typical potency magnitudes, used to sanity-check an inferred unit. Ranges
#: overlap by design — which is exactly why a bare unit guess is unsafe.
UNIT_VALUE_RANGES: dict[str, tuple[float, float]] = {
    "nM": (0.1, 1000.0),
    "µM": (0.001, 100.0),
    "%": (0.0, 100.0),
}


def canonical_assay_type(raw: str) -> str | None:
    """Return the canonical assay type for a raw label, or None if unknown."""
    needle = raw.strip().lower()
    for assay in ASSAY_TYPES:
        if needle == assay.canonical.lower() or needle in assay.aliases:
            return assay.canonical
    return None


def units_for(assay_type: str) -> tuple[str, ...]:
    """Units compatible with a canonical assay type (empty if type unknown)."""
    for assay in ASSAY_TYPES:
        if assay.canonical == assay_type:
            return assay.compatible_units
    return ()