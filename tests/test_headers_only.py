"""D-10/P2: --headers-only sends column headers only -- zero data values --
to Anthropic. This is the privacy dial the judges must see highlighted: the
mapper's confidence may drop (more yellow for the human to resolve) but no
value ever leaves the machine on this path. The default (headers_only=False)
path stays byte-for-byte unchanged -- `test_mapper_boundary.py`'s existing
tests must not regress.
"""

from __future__ import annotations

from pathlib import Path

from assayingest import cli
from assayingest.domain.models import MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.mapping.mapper import _render_table, propose_mapping
from assayingest.parsing.table import RawTable

PRESET = Path(__file__).resolve().parent.parent / "presets" / "assay-potency.yaml"


def _distinctive_table() -> RawTable:
    return RawTable(
        headers=["compound", "value"],
        rows=[["NVS-0012", "CONFIDENTIAL-VALUE-42"]],
        source_name="secret.csv",
    )


# --- _render_table's headers_only branch (the 6-row send site) -------------


def test_headers_only_renders_headers_but_no_sample_rows_or_values():
    rendered = _render_table(_distinctive_table(), headers_only=True)
    assert "compound" in rendered
    assert "value" in rendered
    assert "CONFIDENTIAL-VALUE-42" not in rendered
    assert "NVS-0012" not in rendered
    assert "rows:" not in rendered  # the sample-rows header line itself is gone


def test_default_path_still_sends_sample_rows_unchanged():
    rendered = _render_table(_distinctive_table())
    assert "CONFIDENTIAL-VALUE-42" in rendered
    assert "rows:" in rendered


def test_headers_only_keeps_locale_evidence_lines():
    table = RawTable(
        headers=["Compound", "Value"],
        rows=[["PIN-010", "11,076"]],
        source_name="pinnacle_labs_export.csv",
        column_locales=["non_numeric", "decimal_comma"],
    )
    rendered = _render_table(table, headers_only=True)
    assert "decimal_comma" in rendered
    assert "11,076" not in rendered  # the value itself never appears


# --- propose_mapping threads headers_only through to the send site ---------


def test_propose_mapping_headers_only_kwarg_reaches_render_request():
    captured: dict = {}

    class _FakeMessages:
        def parse(self, **kwargs):
            captured["content"] = kwargs["messages"][0]["content"]

            class _Resp:
                parsed_output = None
                stop_reason = "end_turn"

            return _Resp()

    class _FakeClient:
        messages = _FakeMessages()

    table = _distinctive_table()
    field_set = FieldSet(fields=(Field(name="compound"), Field(name="value")))

    try:
        propose_mapping(table, field_set, client=_FakeClient(), headers_only=True)
    except ValueError:
        pass  # parsed_output is None -- expected; we only care what was sent

    assert "CONFIDENTIAL-VALUE-42" not in captured["content"]
    assert "compound" in captured["content"]


def test_propose_mapping_default_still_sends_sample_rows():
    captured: dict = {}

    class _FakeMessages:
        def parse(self, **kwargs):
            captured["content"] = kwargs["messages"][0]["content"]

            class _Resp:
                parsed_output = None
                stop_reason = "end_turn"

            return _Resp()

    class _FakeClient:
        messages = _FakeMessages()

    table = _distinctive_table()
    field_set = FieldSet(fields=(Field(name="compound"), Field(name="value")))

    try:
        propose_mapping(table, field_set, client=_FakeClient())
    except ValueError:
        pass

    assert "CONFIDENTIAL-VALUE-42" in captured["content"]


# --- CLI wiring: --headers-only threads into propose_mapping, fresh-Claude only


def test_cli_headers_only_flag_threads_into_propose_mapping(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = tmp_path / "secret.csv"
    csv_path.write_text("Compound,Value\nNVS-1,CONFIDENTIAL-99\n", encoding="utf-8")

    captured: dict = {}

    def _fake_propose(table, field_set, client=None, *, headers_only=False):
        captured["headers_only"] = headers_only
        return MappingProposal(source_columns=table.headers, field_mappings=[])

    monkeypatch.setattr(cli, "propose_mapping", _fake_propose)
    field_set = FieldSet(fields=(Field(name="compound"),))

    cli.run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
        headers_only=True,
    )

    assert captured["headers_only"] is True


def test_cli_headers_only_defaults_to_false(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = tmp_path / "secret.csv"
    csv_path.write_text("Compound,Value\nNVS-1,1\n", encoding="utf-8")

    captured: dict = {}

    def _fake_propose(table, field_set, client=None, *, headers_only=False):
        captured["headers_only"] = headers_only
        return MappingProposal(source_columns=table.headers, field_mappings=[])

    monkeypatch.setattr(cli, "propose_mapping", _fake_propose)
    field_set = FieldSet(fields=(Field(name="compound"),))

    cli.run(
        str(csv_path),
        field_set=field_set,
        profiles_db=str(tmp_path / "profiles.db"),
    )

    assert captured["headers_only"] is False


def test_main_accepts_headers_only_flag_and_threads_it_into_run(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    csv_path = tmp_path / "secret.csv"
    csv_path.write_text("Compound,Value\nNVS-1,1\n", encoding="utf-8")

    captured: dict = {}

    def _fake_run(*args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["assayingest", str(csv_path), "--fields", str(PRESET), "--headers-only"],
    )

    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert captured.get("headers_only") is True
