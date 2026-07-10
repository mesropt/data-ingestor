"""D-03: the validator runs on BOTH paths -- fresh-Claude AND an auto-applied
confidence-1.0 profile -- wired into `cli.py::run()` before the review/gate.
A violation forces exit 5 even when Claude (or a saved profile) reported the
field all-green; a genuinely clean file still exits 0 after the validator is
inserted (validation must not spuriously flag clean data).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from assayingest import cli
from assayingest.cli import run
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import stored_mapping_from
from assayingest.learning.signature import column_signature
from assayingest.learning.sqlite_store import SqliteProfileStore
from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent / "presets" / "assay-potency.yaml"

_FLAG_FIELD_SET = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L")),))


def _ready_field_mappings() -> list[FieldMapping]:
    """A fully-clear mapping for novascreen_batch01/02 (byte-identical
    headers): cmpd, assay, potency, "", target_gene, replicates, date."""
    return [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_type", source_column="assay", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="value", source_column="potency", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="unit", source_column=None, confidence=1.0,
            reasoning="confirmed by curator", needs_confirmation=False,
            inferred_value="nM",
        ),
        FieldMapping(
            target_field="target", source_column="target_gene", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="n_replicates", source_column="replicates", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="assay_date", source_column="date", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
    ]


# --- fresh-Claude path: a violation forces exit 5 despite an all-green proposal


def test_fresh_claude_path_validator_forces_exit_5_despite_a_green_proposal(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = tmp_path / "clinical.csv"
    csv_path.write_text("Flag\nX\n", encoding="utf-8")

    def _all_green(table, field_set, client=None):
        return MappingProposal(
            source_columns=table.headers,
            field_mappings=[
                FieldMapping(
                    target_field="flag", source_column="Flag", confidence=1.0,
                    reasoning="clean match, all green", needs_confirmation=False,
                )
            ],
        )

    monkeypatch.setattr(cli, "propose_mapping", _all_green)

    exit_code = run(
        str(csv_path), field_set=_FLAG_FIELD_SET, profiles_db=str(tmp_path / "profiles.db")
    )

    assert exit_code == 5


# --- auto-apply path (D-03, the critical one): validated even with no Claude call


def test_auto_apply_path_validator_still_runs_under_a_saved_profile(
    tmp_path, monkeypatch, capsys
):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called on a profile hit")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    csv_path = tmp_path / "clinical.csv"
    csv_path.write_text("Flag\nX\n", encoding="utf-8")
    table = parse_file(csv_path)

    ready_mapping = FieldMapping(
        target_field="flag", source_column="Flag", confidence=1.0,
        reasoning="curator confirmed", needs_confirmation=False,
    )
    db_path = tmp_path / "profiles.db"
    store = SqliteProfileStore(db_path)
    store.save(
        LearnedProfile(
            profile_id="clinic-1",
            field_set_signature=_FLAG_FIELD_SET.signature,
            column_signature=column_signature(table.headers),
            field_mappings=(stored_mapping_from(ready_mapping, table.headers),),
            structural_hint=None,
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    exit_code = run(str(csv_path), field_set=_FLAG_FIELD_SET, profiles_db=str(db_path))

    out = capsys.readouterr().out
    assert exit_code == 5
    assert "applied saved profile" in out
    assert "no Claude call" in out


# --- clean auto-apply stays green: validation must not spuriously flag ------


def test_clean_auto_apply_still_exits_0_after_the_validator_is_wired_in(
    tmp_path, monkeypatch, capsys
):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called on a profile hit")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    field_set = load_field_set(PRESET)
    table1 = parse_file(DATA / "novascreen_batch01.csv")
    db_path = tmp_path / "profiles.db"
    store = SqliteProfileStore(db_path)
    profile = LearnedProfile(
        profile_id="money-shot-validated",
        field_set_signature=field_set.signature,
        column_signature=column_signature(table1.headers),
        field_mappings=tuple(
            stored_mapping_from(m, table1.headers) for m in _ready_field_mappings()
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save(profile)

    exit_code = run(
        str(DATA / "novascreen_batch02.csv"), field_set=field_set, profiles_db=str(db_path)
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert f"applied saved profile {profile.profile_id}" in out
    assert "no Claude call" in out


# --- --strictness threading (D-11) -------------------------------------------


def test_run_defaults_to_strict_and_threads_a_lenient_choice_through_to_validate(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = tmp_path / "clinical.csv"
    csv_path.write_text("Flag\nH\n", encoding="utf-8")

    def _ready(table, field_set, client=None):
        return MappingProposal(
            source_columns=table.headers,
            field_mappings=[
                FieldMapping(
                    target_field="flag", source_column="Flag", confidence=1.0,
                    reasoning="clean match", needs_confirmation=False,
                )
            ],
        )

    monkeypatch.setattr(cli, "propose_mapping", _ready)

    seen_strictness: list[str] = []
    real_validate = cli.validate

    def _spy(table, proposal, field_set, *, strictness="strict"):
        seen_strictness.append(strictness)
        return real_validate(table, proposal, field_set, strictness=strictness)

    monkeypatch.setattr(cli, "validate", _spy)

    run(str(csv_path), field_set=_FLAG_FIELD_SET, profiles_db=str(tmp_path / "profiles-a.db"))
    run(
        str(csv_path),
        field_set=_FLAG_FIELD_SET,
        profiles_db=str(tmp_path / "profiles-b.db"),
        strictness="lenient",
    )

    assert seen_strictness == ["strict", "lenient"]


def test_main_accepts_a_strictness_flag_and_threads_it_into_run(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = tmp_path / "clinical.csv"
    csv_path.write_text("Flag\nH\n", encoding="utf-8")

    captured: dict = {}

    def _fake_run(*args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["assayingest", str(csv_path), "--fields", str(PRESET), "--strictness", "lenient"],
    )

    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert captured.get("strictness") == "lenient"
