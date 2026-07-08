"""End-to-end `run()` exit codes, plus a live mapper check when a key exists."""

import os
from pathlib import Path

import pytest

from assayingest.cli import run
from assayingest.domain.models import TargetField
from assayingest.mapping.mapper import propose_mapping
from assayingest.parsing.table import parse_file

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


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
    table = parse_file(DATA / "novascreen_batch01.csv")
    proposal = propose_mapping(table)

    assert {m.target_field for m in proposal.field_mappings} == set(TargetField)
    unit = next(m for m in proposal.field_mappings
                if m.target_field is TargetField.UNIT)
    assert unit.needs_confirmation
    assert not proposal.is_ready