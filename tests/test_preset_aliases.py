"""The shipped presets' starter alias sets (SHEET-05, D-11-18), TDD RED-first.

Each canonical field in `presets/*.yaml` now declares a handful of real-world
header spellings a CRO actually writes (`IC50 (nM)`, `Cmpd ID`, `# Reps`). They
are DATA -- plain editable YAML, read by `fields.presets.load_preset_aliases()`
-- and no vocabulary is compiled into any `.py` file (D-20).

The coverage tests below are the ones that matter: without a starter alias set
the Schema scorer's crosswalk is EMPTY on a fresh install, every sheet scores
0/N against every Schema, and SHEET-05 ships dead. So these tests assert against
the REAL corpus headers (`data/synthetic/`, read through the same
`parsing.table.parse_file` the app itself uses), not against invented ones -- an
alias set that only matches spellings we made up would pass a weaker test and
still leave the feature dead on the first messy file.

Pure/offline: no API key, no network, no database.
"""

from __future__ import annotations

from pathlib import Path

from assayingest.fields.loader import load
from assayingest.fields.presets import load_preset_aliases, load_presets
from assayingest.learning.signature import _normalise_header
from assayingest.parsing.table import parse_file

_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"

_PRESET_NAMES = {"assay-potency", "clinical-labs", "pk-parameters", "reagent-inventory"}

_ASSAY_POTENCY_FIELDS = {
    "compound_id",
    "assay_type",
    "value",
    "unit",
    "target",
    "n_replicates",
    "assay_date",
}


def _alias_index(field_aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Normalised spelling -> canonical field name, exactly the key the
    crosswalk index builds (`_normalise_header`, never `.lower().strip()` --
    forking normalisation would silently split this index from the learning
    loop's)."""
    return {
        _normalise_header(spelling): field_name
        for field_name, spellings in field_aliases.items()
        for spelling in spellings
    }


def _covered_fields(headers: list[str], field_aliases: dict[str, tuple[str, ...]]) -> set[str]:
    index = _alias_index(field_aliases)
    return {
        index[_normalise_header(header)]
        for header in headers
        if _normalise_header(header) in index
    }


# --- the reader -------------------------------------------------------------


def test_load_preset_aliases_returns_a_starter_set_for_every_shipped_preset():
    aliases = load_preset_aliases()

    assert set(aliases) == _PRESET_NAMES
    for preset_name, field_aliases in aliases.items():
        assert field_aliases, f"{preset_name} ships no starter aliases -- the scorer would be dead"
        for field_name, spellings in field_aliases.items():
            assert isinstance(spellings, tuple)
            assert spellings, f"{preset_name}.{field_name} declares an empty alias list"
            assert all(isinstance(s, str) and s.strip() for s in spellings)


def test_every_alias_names_a_field_that_actually_exists_in_its_preset():
    """An alias for a field the preset does not declare would seed nothing --
    a silently dead entry. The shipped data must not contain one."""
    for path in sorted(Path("presets").glob("*.yaml")):
        field_set = load(path)
        preset_name = field_set.name or path.stem
        field_aliases = load_preset_aliases()[preset_name]

        unknown = set(field_aliases) - set(field_set.field_names)
        assert not unknown, f"{preset_name} declares aliases for absent fields: {sorted(unknown)}"


def test_no_two_fields_in_one_preset_declare_the_same_normalised_alias():
    """A within-Schema collision makes `_vendor_agnostic_alias_index` map the
    spelling to `None` (it refuses to guess), so the colliding header matches
    NOTHING. The shipped data must never contain such a pair."""
    for preset_name, field_aliases in load_preset_aliases().items():
        seen: dict[str, str] = {}
        for field_name, spellings in field_aliases.items():
            for spelling in spellings:
                key = _normalise_header(spelling)
                assert key not in seen, (
                    f"{preset_name}: {spelling!r} is claimed by both "
                    f"{seen.get(key)!r} and {field_name!r} -- it would match neither"
                )
                seen[key] = field_name


# --- coverage against the REAL corpus (the test that would have caught
# "the scorer ships dead") ----------------------------------------------------


def test_delta_egfr_sheet_headers_all_resolve_through_the_assay_potency_starter_aliases():
    """`delta_screening_per_target.xlsx` spells the SAME four columns three
    different ways across its three sheets. Every one of its four EGFR headers
    must land on a canonical field -- the sheet carries no unit/assay_type/target
    column at all, so four covered fields IS full coverage of what it offers."""
    field_aliases = load_preset_aliases()["assay-potency"]
    headers = parse_file(_FIXTURES / "delta_screening_per_target.xlsx", "EGFR panel").headers

    covered = _covered_fields(headers, field_aliases)

    assert covered == {"compound_id", "value", "n_replicates", "assay_date"}
    assert len(covered) == len(headers)  # 4/4 headers resolved, nothing left over


def test_deltas_other_two_sheets_resolve_to_the_same_canonical_fields():
    """The per-sheet-Schema-proposal case (11-CONTEXT fixtures): `Cmpd ID` /
    `compound_id`, `IC50 nM` / `ic50_nm`, `# runs` / `n`, `Tested on` / `date`
    are different spellings of one canonical set. The crosswalk must resolve all
    three sheets identically, or the scorer would rank the same workbook's sheets
    against different Schemas."""
    field_aliases = load_preset_aliases()["assay-potency"]
    expected = {"compound_id", "value", "n_replicates", "assay_date"}

    for sheet in ("JAK2 panel", "BRAF panel"):
        headers = parse_file(_FIXTURES / "delta_screening_per_target.xlsx", sheet).headers
        assert _covered_fields(headers, field_aliases) == expected, sheet


def test_novascreen_headers_cover_at_least_five_of_the_seven_assay_potency_fields():
    """A messy real CSV (`cmpd`, `potency`, `target_gene`, a blank column) must
    reach the scorer with substantial coverage on a FRESH install -- this is the
    assertion that proves the starter set makes SHEET-05 live rather than dead."""
    field_aliases = load_preset_aliases()["assay-potency"]
    headers = parse_file(_FIXTURES / "novascreen_batch01.csv").headers

    covered = _covered_fields(headers, field_aliases)

    assert covered <= _ASSAY_POTENCY_FIELDS
    assert len(covered) >= 5, f"only {sorted(covered)} covered -- the scorer would propose skip"


def test_reagent_inventory_starter_aliases_cover_the_verity_stockroom_headers():
    """The non-life-sciences preset gets the same treatment (D-21): its starter
    set is derived from the real `verity_reagents_stock.xlsx` spellings, not from
    assay vocabulary."""
    field_aliases = load_preset_aliases()["reagent-inventory"]
    headers = ["SKU", "Item", "On hand", "Units", "Use By", "Location"]

    covered = _covered_fields(headers, field_aliases)

    assert covered == {"catalogue_number", "name", "quantity", "unit", "expiry_date", "shelf"}


# --- the `aliases:` block must not leak into `FieldSet` ----------------------


def test_the_aliases_block_never_reaches_the_field_set_loader():
    """`fields/loader.py::_build_field` reads only known keys, so an `aliases:`
    block is inert to `FieldSet` loading. `tests/test_presets.py` stays green
    UNCHANGED and no `Field` gains an alias attribute -- presets remain data the
    loader does not interpret."""
    presets = load_presets()

    assert len(presets) == 4
    for _, field_set in presets:
        assert field_set.field_names
        for field in field_set.fields:
            assert not hasattr(field, "aliases")
