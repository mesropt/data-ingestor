"""Shared authenticated-`TestClient` builders (10-09, D-10-13) — and the
shared judging fake client every API test that expects a dataset uses from
12-04 (Wave B) onward.

`POST /api/upload`, `/api/structural-hint/resolve`, and `/api/date-format/
resolve` are now gated by `require_user` (Task 2). Every test that drives
one of those routes through `TestClient` must inject a signed-in `User` via
`app.dependency_overrides[get_current_user]` -- overriding `get_current_user`
(not `require_user`) is deliberate: it is the single root dependency that
satisfies BOTH `require_user` and `require_verified_user`, so a file that
already overrides `require_verified_user` for `/api/confirm`'s gate keeps
working unchanged once this override is added alongside it.

Lifted verbatim from `tests/api/test_reconcile.py::_verified_user`/
`_unverified_user` (the exact shape it already established) so every other
affected test file shares ONE definition instead of re-deriving it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import get_args

import pytest

from assayingest.auth.models import User

_TS = "2026-01-01T00:00:00+00:00"


def verified_user() -> User:
    return User(
        id="u", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at=_TS,
    )


def unverified_user() -> User:
    return User(
        id="u2", email="new@example.com", password_hash=None,
        is_verified=False, auth_provider="password", created_at=_TS,
    )


# --- the shared judging fake client (12-04, SHAPE-01) -------------------------


class _JudgingMessages:
    """A duck-typed `client.messages` whose `parse` answers ONLY the layout
    judge, with a REAL instance of the judge's per-request wire model."""

    def parse(self, **kwargs):
        wire_model = kwargs.get("output_format")
        sheet_names = _judged_sheet_names(wire_model)
        assert sheet_names is not None, (
            "judging_client only answers the layout judge's structured-output "
            "call. Another Claude call reached the shared client — keep the "
            "mapper/ranker on whatever stub the test already installed "
            "(service.propose_mapping / service.propose_schema_ranking); this "
            "fixture composes with those overrides, it never replaces them."
        )
        verdict_model = get_args(wire_model.model_fields["sheets"].annotation)[0]
        parsed = wire_model(
            sheets=[
                verdict_model(
                    sheet_name=name,
                    kind="row_per_record",
                    confidence=1.0,
                    reasoning="judging_client fixture: an ordinary table",
                    header_row_index=None,
                    first_data_row=None,
                    last_data_row=None,
                    key_value_blocks=[],
                    one_record_per_value_column=False,
                )
                for name in sheet_names
            ]
        )
        return SimpleNamespace(parsed_output=parsed, stop_reason="end_turn")


def _judged_sheet_names(wire_model) -> list[str] | None:
    """The REAL sheet names, read from the wire model's runtime `Literal` —
    derived, never hardcoded, so the fake cannot drift from the schema. `None`
    when `wire_model` is not the judge's workbook-layout model."""
    if wire_model is None or not hasattr(wire_model, "model_fields"):
        return None
    sheets_field = wire_model.model_fields.get("sheets")
    if sheets_field is None:
        return None
    item_args = get_args(sheets_field.annotation)
    if not item_args:
        return None
    name_annotation = item_args[0].model_fields["sheet_name"].annotation
    names = get_args(name_annotation)
    return list(names) if names else None


class _JudgingClient:
    messages = _JudgingMessages()


@pytest.fixture
def judging_client():
    """The shared duck-typed structured-output fake for the layout judge —
    override `get_anthropic_client` with it wherever an API test expects a
    DATASET (real statuses, real headers) rather than the no-judge question.

    It exists because of a mechanical fact, not taste: API tests override
    `get_anthropic_client -> lambda: None`, and `service._judge_for(
    client=None, judge_fn=None)` short-circuits to None BEFORE any seam or
    monkeypatch can bind a judge — an HTTP test literally cannot reach the
    `judge_fn` kwarg. A fake CLIENT at the DI seam is the only lever.

    It stops at the SDK boundary and nowhere shallower: `parsed_output` is a
    REAL instance of the judge's per-request wire model, with the sheet names
    read from the model's own runtime `Literal`, so every verdict still runs
    the REAL `_to_domain_verdicts` — a fake that only satisfied a fake would
    prove nothing (pinned by this fixture's self-test in test_sheets_route).
    Every sheet gets a confident `row_per_record` verdict — the null
    hypothesis (D-12-15): read it the ordinary way.

    The honesty rule stands alongside it: a test whose subject IS the
    no-judge path KEEPS the `lambda: None` override and gets
    all-`layout_unknown` sheets — because no client really does mean no
    judge, in production exactly as here.
    """
    return _JudgingClient()
