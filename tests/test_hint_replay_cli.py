"""LEARN-06 / ROADMAP SC5: a saved profile's structural hint replays
automatically on a later run of the same odd-layout file, so the human is
never re-asked the identical `StructureQuestion` (03-VERIFICATION.md gap).

Fail-closed (P1): a candidate hint is only ever accepted when the re-parsed
table reproduces THAT profile's exact stored `column_signature` -- the same
exact-signature guarantee LEARN-03/04 already require for mapping auto-apply,
applied here to the hint itself. A hint that resolves a DIFFERENT file's
structure but yields a different signature must never auto-apply; the human
is asked exactly as before. Written test-first (TDD RED)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from assayingest import cli
from assayingest.cli import run
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.learning.signature import column_signature
from assayingest.parsing.hint import StructuralHint
from assayingest.parsing.table import parse

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent / "presets" / "reagent-inventory.yaml"

_VERITY_FILE = DATA / "verity_reagents_stock.xlsx"

#: SKU, Item, On hand, Units, Use By, Location, Reordered? -> the six
#: reagent-inventory target fields (Reordered? has no target field).
_FIELD_TO_COLUMN = {
    "catalogue_number": "SKU",
    "name": "Item",
    "quantity": "On hand",
    "unit": "Units",
    "expiry_date": "Use By",
    "shelf": "Location",
}


def _ready_reagent_mapping(headers: list[str]) -> list[FieldMapping]:
    return [
        FieldMapping(
            target_field=field,
            source_column=column,
            confidence=1.0,
            reasoning="exact match",
            needs_confirmation=False,
        )
        for field, column in _FIELD_TO_COLUMN.items()
    ]


def _seed_verity_profile(store, field_set, monkeypatch) -> None:
    """Simulates a curator's first-ever run: parse with an explicit
    `--hint`, get a fully-clear mapping, and save the profile (with its
    hint) -- the save half LEARN-06 already gets right."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _ready(table, fs, client=None, **kwargs):
        return MappingProposal(
            source_columns=table.headers,
            field_mappings=_ready_reagent_mapping(table.headers),
        )

    monkeypatch.setattr(cli, "propose_mapping", _ready)

    exit_code = run(
        str(_VERITY_FILE),
        hint=StructuralHint(header_row_index=2),
        field_set=field_set,
        store=store,
        save_profile=True,
    )
    assert exit_code == 0, "save-path setup must itself succeed (fully clear)"


def _other_odd_layout_workbook(tmp_path: Path) -> Path:
    """The SAME odd shape as verity's fixture (banner row, blank row,
    header at row index 2, matching column count/types) but with DIFFERENT
    headers and data -- genuinely ambiguous on its own (no --hint resolves
    it either, exactly like verity), so this proves the fail-closed guard:
    verity's saved header-row=2 hint successfully reparses THIS file too,
    but the resulting column signature does not match verity's stored
    signature, so it must never auto-apply."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in (
        ("Other Labs — reagent export", None, None, None, None, None, None),
        (None, None, None, None, None, None, None),
        ("Code", "Description", "Count", "UOM", "Expiry", "Loc", "Flag"),
        ("X-11023", "Widget assembly", 2.5, "ea", "2026-03-01", "Bay B / rack 4", "no"),
        ("Y-90455", "Gadget housing", 12, "ea", "2026-01-15", "Bay 2 / shelf 1", "yes"),
        ("Z-20881", "Sprocket set", 8, "sets", "2025-11-30", "Bay A / rack 1", "no"),
        ("W-33017", "Bracket bulk", 500, "ea", "2026-06-20", "Bay 1 / shelf 3", "no"),
        ("V-14200", "Fastener pack", 100, "ea", "2026-02-28", "Bay 2 / shelf 2", "yes"),
        ("U-77310", "Panel sheet", 25, "ea", "2027-01-10", "Cab C / shelf 2", "no"),
        ("T-50012", "Tube stock", 1000, "units", "2028-09-01", "Cab C / shelf 1", "no"),
        ("S-60934", "Coil spring", 0.75, "ea", "2025-12-05", "Bay B / rack 2", "yes"),
    ):
        ws.append(row)
    path = tmp_path / "other_odd_layout.xlsx"
    wb.save(path)
    return path


def test_second_run_with_no_hint_replays_saved_hint_and_auto_applies(tmp_path, monkeypatch, capsys, profile_store):
    field_set = load_field_set(PRESET)
    db_path = tmp_path / "profiles.db"
    _seed_verity_profile(profile_store, field_set, monkeypatch)

    saved_table = parse(_VERITY_FILE, hint=StructuralHint(header_row_index=2))
    store = profile_store
    saved_profile = store.find(field_set.signature, column_signature(saved_table.headers))
    assert saved_profile is not None
    assert saved_profile.structural_hint == StructuralHint(header_row_index=2)

    # -- Replay path: SAME file, SAME field set, NO --hint, NO Claude call --
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called on hint replay")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    exit_code = run(
        str(_VERITY_FILE),
        field_set=field_set,
        store=profile_store,
    )

    out = capsys.readouterr().out
    # Must NOT reproduce the identical StructureQuestion / exit 4 (the
    # LEARN-06 gap 03-VERIFICATION.md reproduced live).
    assert exit_code == 0
    assert "which row is the real header" not in out
    assert "BLOCKED: structure unresolved" not in out
    # Transparency (D-08): the replay is announced, not silent.
    assert f"replayed saved structural hint from profile {saved_profile.profile_id}" in out
    # The replayed table also auto-applies the saved mapping (no Claude call).
    assert f"applied saved profile {saved_profile.profile_id}" in out
    assert "no Claude call" in out


def test_explicit_hint_always_wins_over_replay(tmp_path, monkeypatch, profile_store):
    """An explicit --hint from the human must never be silently overridden
    by a saved profile's replayed hint, even when one exists."""
    field_set = load_field_set(PRESET)
    db_path = tmp_path / "profiles.db"
    _seed_verity_profile(profile_store, field_set, monkeypatch)

    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called on a profile hit")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    exit_code = run(
        str(_VERITY_FILE),
        hint=StructuralHint(header_row_index=2),  # explicit, matches the saved one
        field_set=field_set,
        store=profile_store,
    )
    assert exit_code == 0


def test_mismatched_file_with_replayed_hint_still_asks_the_human(tmp_path, monkeypatch, capsys, profile_store):
    """Fail-closed control (P1): a DIFFERENT file's hinted reparse resolves
    structurally but does NOT reproduce the saved profile's column
    signature -- the tool must still surface the StructureQuestion, never
    silently apply a stale hint from an unrelated file."""
    field_set = load_field_set(PRESET)
    db_path = tmp_path / "profiles.db"
    _seed_verity_profile(profile_store, field_set, monkeypatch)

    other_file = _other_odd_layout_workbook(tmp_path)

    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    exit_code = run(
        str(other_file),
        field_set=field_set,
        store=profile_store,
    )

    out = capsys.readouterr().out
    assert exit_code == 4
    assert "BLOCKED: structure unresolved" in out
    assert "replayed saved structural hint" not in out
