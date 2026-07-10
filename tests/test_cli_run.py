"""End-to-end `run()` exit codes, plus a live mapper check when a key exists."""

import os
from pathlib import Path

import pytest

from assayingest.cli import run
from assayingest.fields.loader import load as load_field_set
from assayingest.mapping.mapper import propose_mapping
from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent / "presets" / "assay-potency.yaml"


def test_run_reports_missing_file(capsys):
    assert run(str(DATA / "missing.csv")) == 2
    assert "no file" in capsys.readouterr().err


def test_run_reports_missing_credentials(monkeypatch, capsys):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert run(str(DATA / "novascreen_batch01.csv")) == 3
    assert "credentials" in capsys.readouterr().err


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live mapper test requires ANTHROPIC_API_KEY",
)
def test_mapper_flags_missing_unit_on_novascreen():
    # The money shot: NovaScreen's first file has no unit column, so the mapper
    # must infer nM from the value range and flag it for confirmation.
    field_set = load_field_set(PRESET)
    table = parse_file(DATA / "novascreen_batch01.csv")
    proposal = propose_mapping(table, field_set)

    assert {m.target_field for m in proposal.field_mappings} == set(
        field_set.field_names
    )
    unit = next(m for m in proposal.field_mappings if m.target_field == "unit")
    assert unit.needs_confirmation
    assert not proposal.is_ready


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live mapper test requires ANTHROPIC_API_KEY",
)
def test_run_exits_5_on_a_blocked_proposal():
    # D-23: a proposed-but-not-ready mapping is exit 5, never a silent 0.
    field_set = load_field_set(PRESET)
    exit_code = run(str(DATA / "novascreen_batch01.csv"), field_set=field_set)
    assert exit_code == 5
