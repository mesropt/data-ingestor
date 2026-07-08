"""The reference dictionary is the no-LLM ground truth; pin its behaviour."""

from assayingest.domain.reference import (
    ALLOWED_UNITS,
    canonical_assay_type,
    units_for,
)


def test_canonical_normalises_known_aliases():
    assert canonical_assay_type("Inhibition %") == "%inhibition"
    assert canonical_assay_type("ic50") == "IC50"
    assert canonical_assay_type("  Kd ") == "Kd"


def test_canonical_returns_none_for_unknown_type():
    assert canonical_assay_type("melting point") is None


def test_units_for_concentration_type():
    assert units_for("IC50") == ("µM", "nM")


def test_units_for_percent_inhibition():
    assert units_for("%inhibition") == ("%",)


def test_units_for_unknown_type_is_empty():
    assert units_for("nonsense") == ()


def test_allowed_units_are_the_three_domain_units():
    assert set(ALLOWED_UNITS) == {"µM", "nM", "%"}