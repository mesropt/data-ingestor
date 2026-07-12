"""End-to-end `run()` exit codes, plus a live mapper check gated behind an
explicit ASSAYINGEST_LIVE_TESTS=1 opt-in (never merely "a key is present" --
an auto-loaded .env means a key can be present with no intent to spend
money, so intent is what gates the call, not credential presence)."""

import os
from pathlib import Path

import pytest

from assayingest import cli
from assayingest.cli import run
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.fields.models import Field, FieldSet
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


# --- D-23 exit-code gate, exercised offline with a monkeypatched mapper -----


def _blocked_proposal() -> MappingProposal:
    return MappingProposal(
        source_columns=["a"],
        field_mappings=[
            FieldMapping(
                target_field="value",
                source_column=None,
                confidence=0.5,
                reasoning="ambiguous column",
                needs_confirmation=True,
            )
        ],
    )


def _ready_proposal() -> MappingProposal:
    return MappingProposal(
        source_columns=["a"],
        field_mappings=[
            FieldMapping(
                target_field="value",
                source_column="a",
                confidence=1.0,
                reasoning="exact match",
                needs_confirmation=False,
            )
        ],
    )


def test_map_one_exits_5_when_the_proposal_is_blocked(monkeypatch):
    monkeypatch.setattr(
        cli, "propose_mapping", lambda table, field_set, client=None, **kwargs: _blocked_proposal()
    )
    # `_map_one`'s credential check now lives on the no-profile branch
    # (Pitfall 3) -- with no `store` this always takes that branch, so it
    # needs a (fake) key even though `propose_mapping` is monkeypatched.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")
    # WR-03: field_set=None + credentials now raises before reaching the
    # (monkeypatched) mapper at all -- a real minimal field_set is required
    # to exercise the D-23 exit-code gate this test targets.
    field_set = FieldSet(fields=(Field(name="value"),))
    assert cli._map_one(table, field_set=field_set) == 5


def test_map_one_exits_0_only_when_the_proposal_is_ready(monkeypatch):
    monkeypatch.setattr(
        cli, "propose_mapping", lambda table, field_set, client=None, **kwargs: _ready_proposal()
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")
    field_set = FieldSet(fields=(Field(name="value"),))
    assert cli._map_one(table, field_set=field_set) == 0


# --- WR-03: field_set=None + credentials must not crash with AttributeError -


def test_resolve_proposal_raises_value_error_when_field_set_is_none_with_credentials(
    monkeypatch,
):
    """`run()`/`_resolve_proposal` accept `field_set=None` for early-exit
    callers, but if credentials ARE configured, the fresh-Claude branch used
    to dereference `field_set.fields` with no guard -- a bare
    `AttributeError` instead of a consequence-naming error `_map_one` can
    catch and report cleanly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")

    with pytest.raises(ValueError, match="no field set"):
        cli._resolve_proposal(table, None, None)


def test_map_one_reports_a_clean_exit_1_when_field_set_is_none_with_credentials(
    monkeypatch, capsys
):
    """The same hazard exercised through `_map_one`: it must already catch
    `ValueError` and exit 1, never propagate a bare traceback."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    table = parse_file(DATA / "novascreen_batch01.csv")

    assert cli._map_one(table, field_set=None, store=None) == 1
    assert "no field set" in capsys.readouterr().err


@pytest.mark.skipif(
    os.environ.get("ASSAYINGEST_LIVE_TESTS") != "1",
    reason="live mapper test costs real money -- opt in with ASSAYINGEST_LIVE_TESTS=1",
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
    os.environ.get("ASSAYINGEST_LIVE_TESTS") != "1",
    reason="live mapper test costs real money -- opt in with ASSAYINGEST_LIVE_TESTS=1",
)
def test_run_exits_5_on_a_blocked_proposal(profile_store):
    # D-23: a proposed-but-not-ready mapping is exit 5, never a silent 0.
    # The store is injected even though this test is normally skipped: without it,
    # `run()` would open a session on the composition root -- i.e. the DEV database.
    field_set = load_field_set(PRESET)
    exit_code = run(
        str(DATA / "novascreen_batch01.csv"), field_set=field_set, store=profile_store
    )
    assert exit_code == 5
