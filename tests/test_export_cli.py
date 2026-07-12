"""EXPORT-02/03/04 CLI wiring (D-09/P1): --export writes CSV/.xlsx/JSON +
manifest.json only when the mapping is fully clear; a yellow mapping writes
nothing and stays exit 5; the manifest records provenance
(auto-applied-from-profile vs fresh-claude) and strictness; a run with no
--export flag writes no export files at all.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from assayingest import cli
from assayingest.cli import run
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import stored_mapping_from
from assayingest.learning.signature import column_signature
from assayingest.learning.sqlite_store import SqliteProfileStore
from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent / "presets" / "assay-potency.yaml"


def _ready_field_mappings() -> list[FieldMapping]:
    """A fully-clear mapping for novascreen_batch01.csv's headers:
    cmpd, assay, potency, "", target_gene, replicates, date."""
    return [
        FieldMapping(target_field="compound_id", source_column="cmpd", confidence=1.0,
                     reasoning="exact match", needs_confirmation=False),
        FieldMapping(target_field="assay_type", source_column="assay", confidence=1.0,
                     reasoning="exact match", needs_confirmation=False),
        FieldMapping(target_field="value", source_column="potency", confidence=1.0,
                     reasoning="exact match", needs_confirmation=False),
        FieldMapping(target_field="unit", source_column=None, confidence=1.0,
                     reasoning="confirmed by curator", needs_confirmation=False,
                     inferred_value="nM"),
        FieldMapping(target_field="target", source_column="target_gene", confidence=1.0,
                     reasoning="exact match", needs_confirmation=False),
        FieldMapping(target_field="n_replicates", source_column="replicates", confidence=1.0,
                     reasoning="exact match", needs_confirmation=False),
        FieldMapping(target_field="assay_date", source_column="date", confidence=1.0,
                     reasoning="exact match", needs_confirmation=False),
    ]


def _blocked_field_mappings(field_names: list[str]) -> list[FieldMapping]:
    return [
        FieldMapping(target_field=name, source_column=None, confidence=0.4,
                     reasoning="ambiguous", needs_confirmation=True)
        for name in field_names
    ]


def _copy_batch01(tmp_path: Path) -> Path:
    """Export's default-dir test needs a source file the CLI can resolve a
    parent directory from -- copy rather than reuse the shared fixture path
    directly, so nothing is ever written into the repo's data/ directory."""
    dest = tmp_path / "batch01.csv"
    shutil.copy(DATA / "novascreen_batch01.csv", dest)
    return dest


# --- gate: a blocked mapping writes nothing (D-09/P1) -----------------------


def test_export_blocked_on_a_not_ready_mapping_writes_nothing_and_stays_exit_5(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    csv_path = _copy_batch01(tmp_path)

    def _blocked(table, fs, client=None, **kwargs):
        return MappingProposal(
            source_columns=table.headers,
            field_mappings=_blocked_field_mappings(fs.field_names),
        )

    monkeypatch.setattr(cli, "propose_mapping", _blocked)
    out_dir = tmp_path / "out"

    exit_code = run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
        export=True,
        output_dir=str(out_dir),
    )

    assert exit_code == 5
    assert not out_dir.exists()


# --- ready export writes exactly 4 files (EXPORT-02/03/04) ------------------


def test_export_writes_exactly_csv_xlsx_json_and_manifest_when_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    csv_path = _copy_batch01(tmp_path)

    def _ready(table, fs, client=None, **kwargs):
        return MappingProposal(source_columns=table.headers, field_mappings=_ready_field_mappings())

    monkeypatch.setattr(cli, "propose_mapping", _ready)
    out_dir = tmp_path / "out"

    exit_code = run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
        export=True,
        output_dir=str(out_dir),
    )

    assert exit_code == 0
    written = {p.name for p in out_dir.iterdir()}
    assert written == {"export.csv", "export.xlsx", "export.json", "manifest.json"}


# --- default dir is beside the source file (D-09) ---------------------------


def test_export_default_output_dir_is_beside_the_source_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    csv_path = _copy_batch01(tmp_path)

    def _ready(table, fs, client=None, **kwargs):
        return MappingProposal(source_columns=table.headers, field_mappings=_ready_field_mappings())

    monkeypatch.setattr(cli, "propose_mapping", _ready)

    exit_code = run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
        export=True,
    )

    assert exit_code == 0
    assert (tmp_path / "export.csv").exists()
    assert (tmp_path / "manifest.json").exists()


# --- provenance + strictness recorded in the manifest (D-08/D-11) -----------


def test_manifest_records_fresh_claude_provenance_and_strictness(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    csv_path = _copy_batch01(tmp_path)

    def _ready(table, fs, client=None, **kwargs):
        return MappingProposal(source_columns=table.headers, field_mappings=_ready_field_mappings())

    monkeypatch.setattr(cli, "propose_mapping", _ready)
    out_dir = tmp_path / "out"

    run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
        export=True,
        output_dir=str(out_dir),
        strictness="lenient",
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance"] == "fresh-claude"
    assert manifest["strictness"] == "lenient"


def test_manifest_records_auto_applied_provenance_on_a_profile_hit(tmp_path, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("propose_mapping must never be called on a profile hit")

    monkeypatch.setattr(cli, "propose_mapping", _fail_if_called)

    field_set = load_field_set(PRESET)
    csv_path = _copy_batch01(tmp_path)
    table = parse_file(csv_path)
    db_path = tmp_path / "profiles.db"
    store = SqliteProfileStore(db_path)
    store.save(
        LearnedProfile(
            profile_id="export-money-shot",
            field_set_signature=field_set.signature,
            column_signature=column_signature(table.headers),
            field_mappings=tuple(
                stored_mapping_from(m, table.headers) for m in _ready_field_mappings()
            ),
            structural_hint=None,
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    out_dir = tmp_path / "out"

    exit_code = run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(db_path),
        export=True,
        output_dir=str(out_dir),
    )

    assert exit_code == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance"] == "auto-applied-from-profile"


# --- no implicit writes: a normal run with no --export writes nothing -------


def test_no_export_flag_writes_no_export_files_at_all(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = load_field_set(PRESET)
    csv_path = _copy_batch01(tmp_path)

    def _ready(table, fs, client=None, **kwargs):
        return MappingProposal(source_columns=table.headers, field_mappings=_ready_field_mappings())

    monkeypatch.setattr(cli, "propose_mapping", _ready)

    exit_code = run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
    )

    assert exit_code == 0
    for name in ("export.csv", "export.xlsx", "export.json", "manifest.json"):
        assert not (tmp_path / name).exists()


# --- main() argparse wiring --------------------------------------------------


def test_main_accepts_export_and_output_dir_flags_and_threads_them_into_run(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = _copy_batch01(tmp_path)

    captured: dict = {}

    def _fake_run(*args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "assayingest", str(csv_path), "--fields", str(PRESET),
            "--export", "-o", str(tmp_path / "out"),
        ],
    )

    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert captured.get("export") is True
    assert captured.get("output_dir") == str(tmp_path / "out")
