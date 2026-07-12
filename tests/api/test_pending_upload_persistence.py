"""A pending upload must survive a server restart / worker switch (TDD
RED-first, quick 260712 confirm-after-reload defect).

The reproduced failure: a curator resolves the Review screen, the dev server
reloads (or a deploy restarts a worker), and Confirm answers `404 no pending
upload for token '<uuid>'` -- the parsed table, the field set, and the
human's date answers all lived in one process's `OrderedDict` and died with
it. These tests pin the fix end to end:

  * a review-ready entry written by one `UploadRegistry` is readable by a
    FRESH `UploadRegistry` against the same database (the simulated restart),
    and `/api/confirm` succeeds through it -- including `date_answers`, the
    one thing the server cannot re-derive;
  * persisted rows are transient: they expire (TTL) and are purged the
    moment a confirm succeeds -- uploaded cell values never outlive the
    review they exist for;
  * question-branch entries (a retained temp file, a pending date question)
    are NEVER written to the database, and the registry still owns their
    temp-file lifecycle (WR-01) exactly as before;
  * the failure path is honest: a genuinely-gone upload 404s with the
    consequence and the remedy, never the raw token.

Mirrors `tests/api/test_confirm_gate.py`'s seed-the-registry-directly and
auth-override idioms.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from assayingest.api.state import UploadEntry, UploadRegistry
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.structure.date_order import DateOrder
from assayingest.parsing.table import RawTable
from assayingest.persistence.models import PendingUploadRow


def _table() -> RawTable:
    """A table whose date column is genuinely order-ambiguous (03/04/2025 --
    both components <= 12), so a confirm that LOST the human's date answer
    would re-flag `assay_date` amber and 422 instead of succeeding."""
    return RawTable(
        headers=["Compound Name", "Date"],
        rows=[["CPD-1", "03/04/2025"], ["CPD-2", "03/04/2025"]],
        source_name="cascade_assays_nounit.xlsx",
        sheet_name="Sheet1",
    )


def _field_set() -> FieldSet:
    return FieldSet(
        fields=(Field(name="compound_id"), Field(name="assay_date", type="date"))
    )


def _review_ready_entry() -> UploadEntry:
    """The exact shape `/api/date-format/resolve` re-puts once the human has
    answered a date question: mapping resolved, no temp file, and the
    answer -- the one thing the server cannot re-derive -- retained."""
    return UploadEntry(
        field_set=_field_set(),
        headers_only=False,
        tmp_path=None,
        table=_table(),
        provenance="fresh-claude",
        date_answers={"assay_date": DateOrder.DAY_FIRST},
    )


def _mappings_body() -> list[dict]:
    return [
        {
            "target_field": "compound_id",
            "source_column": "Compound Name",
            "confidence": 1.0,
            "reasoning": "exact match",
            "needs_confirmation": False,
            "inferred_value": None,
            "alternatives": [],
        },
        {
            "target_field": "assay_date",
            "source_column": "Date",
            "confidence": 1.0,
            "reasoning": "resolved by curator",
            "needs_confirmation": False,
            "inferred_value": None,
            "alternatives": [],
        },
    ]


def _client(profile_store) -> TestClient:
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store, require_verified_user
    from assayingest.auth.models import User

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[require_verified_user] = lambda: User(
        id="t", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at="2026-07-11T00:00:00Z",
    )
    return TestClient(app)


def _clear() -> None:
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _row_for(db_session, token: str) -> PendingUploadRow | None:
    return db_session.scalars(
        select(PendingUploadRow).where(PendingUploadRow.token == token)
    ).first()


# --- the reproduction: restart survival ----------------------------------------


def test_a_review_ready_entry_survives_a_simulated_process_restart():
    """The defect itself: the entry one process retained must be readable by
    a brand-new registry (fresh memory, same database) -- a restarted
    server, or a different worker, resolving the same token."""
    token = UploadRegistry().put(_review_ready_entry())

    restarted = UploadRegistry()  # a fresh process: empty memory, same DB
    entry = restarted.get(token)

    assert entry is not None
    assert entry.table is not None
    assert entry.table.headers == ["Compound Name", "Date"]
    assert entry.table.rows == [["CPD-1", "03/04/2025"], ["CPD-2", "03/04/2025"]]
    assert entry.table.source_name == "cascade_assays_nounit.xlsx"
    assert entry.table.sheet_name == "Sheet1"
    assert entry.field_set is not None
    assert entry.field_set.signature == _field_set().signature
    assert entry.provenance == "fresh-claude"
    assert entry.date_answers == {"assay_date": DateOrder.DAY_FIRST}
    assert entry.tmp_path is None  # a rehydrated entry never owns a file


def test_confirm_succeeds_after_a_restart_including_the_humans_date_answers(
    monkeypatch, profile_store
):
    """The end-to-end money case: upload retained by process A, server
    restarts, Confirm lands on process B -- and succeeds, because the
    retained `date_answers` crossed the restart too. Losing them would
    re-flag the ambiguous date column and 422 (the dead end fixed earlier
    today); losing the whole entry would 404 (this defect)."""
    token = UploadRegistry().put(_review_ready_entry())

    # Simulate the restart at the route boundary: the confirm route's own
    # registry binding becomes a brand-new, empty-memory instance.
    import assayingest.api.routes.confirm as confirm_module

    monkeypatch.setattr(confirm_module, "registry", UploadRegistry())

    client = _client(profile_store)
    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "vendor": "test-vendor",
            "field_set": _field_set().to_dict(),
            "field_mappings": _mappings_body(),
        },
    )
    _clear()

    assert response.status_code == 200, response.json()
    assert response.json()["ready"] is True


def test_pop_after_a_restart_returns_the_entry_and_removes_the_row(db_session):
    token = UploadRegistry().put(_review_ready_entry())

    restarted = UploadRegistry()
    entry = restarted.pop(token)

    assert entry is not None and entry.table is not None
    assert _row_for(db_session, token) is None
    assert restarted.pop(token) is None


# --- TTL: a pending upload's rows are transient ---------------------------------


def test_an_expired_entry_is_gone_and_its_rows_leave_the_database(db_session):
    """TTL is a real mechanism, not a comment: an expired row resolves to
    nothing AND is deleted on that very lookup -- the uploaded cell values
    do not linger at rest just because nobody confirmed."""
    token = UploadRegistry(ttl_seconds=0).put(_review_ready_entry())

    restarted = UploadRegistry()
    assert restarted.get(token) is None
    assert _row_for(db_session, token) is None


def test_put_sweeps_other_expired_rows_from_the_database(db_session):
    """Expiry must not depend on someone asking for the dead token: any
    later put sweeps every already-expired row out of the table."""
    expired_token = UploadRegistry(ttl_seconds=0).put(_review_ready_entry())

    UploadRegistry().put(_review_ready_entry())

    assert _row_for(db_session, expired_token) is None


# --- purge on confirm ------------------------------------------------------------


def test_a_confirmed_upload_is_purged_from_memory_and_database(db_session, profile_store):
    """A pending upload exists FOR the review; once the confirm succeeds
    there is no reason for the file's rows to outlive it -- neither in the
    registry's memory nor at rest in the database."""
    from assayingest.api.state import registry

    token = registry.put(_review_ready_entry())
    client = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "vendor": "test-vendor",
            "field_set": _field_set().to_dict(),
            "field_mappings": _mappings_body(),
        },
    )
    _clear()

    assert response.status_code == 200, response.json()
    assert _row_for(db_session, token) is None
    assert registry.get(token) is None


# --- the honest 404 --------------------------------------------------------------


def test_a_missing_upload_404_names_the_consequence_and_remedy_without_the_token(
    profile_store,
):
    """An upload can legitimately be gone (expired, already confirmed, or a
    garbage token). The refusal must say what did not happen and what to do
    next -- and must never echo the raw UUID back at the human."""
    ghost = str(uuid.uuid4())
    client = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": ghost,
            "vendor": "test-vendor",
            "field_set": _field_set().to_dict(),
            "field_mappings": _mappings_body(),
        },
    )
    _clear()

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert ghost not in detail  # never leak the token into user-facing copy
    assert "Nothing was saved" in detail  # the consequence
    assert "Upload the file again" in detail  # the remedy


# --- question-branch entries stay memory-only, temp files stay owned ------------


def test_a_structural_question_entry_is_never_written_to_the_database(
    db_session, tmp_path
):
    """A structural-question entry retains a live temp file, not a table --
    there is nothing a confirm could rebuild from it, and persisting the
    path of a per-process temp file would be a lie after a restart. It
    stays memory-only, and eviction still owns its temp file (WR-01)."""
    retained = tmp_path / "pending.csv"
    retained.write_text("a,b\n1,2\n", encoding="utf-8")
    registry = UploadRegistry(max_entries=1)

    token = registry.put(
        UploadEntry(field_set=None, headers_only=False, tmp_path=str(retained))
    )

    assert _row_for(db_session, token) is None
    registry.put(UploadEntry(field_set=None, headers_only=False, tmp_path=None))
    assert not retained.exists()  # evicted entry's file unlinked, as before


def test_a_pending_date_question_entry_is_never_written_to_the_database(db_session):
    """A date-question entry is mid-question: its retained proposal exists
    for `/api/date-format/resolve`, which re-puts a review-ready entry once
    the human answers. THAT entry is what persists -- not the half-answered
    question, whose lifecycle stays exactly as it is today."""
    registry = UploadRegistry()
    proposal = MappingProposal(
        source_columns=["Compound Name", "Date"],
        field_mappings=[
            FieldMapping(
                target_field="assay_date", source_column="Date", confidence=1.0,
                reasoning="fixture", needs_confirmation=True,
            )
        ],
    )

    token = registry.put(
        UploadEntry(
            field_set=_field_set(), headers_only=False, tmp_path=None,
            table=_table(), provenance="fresh-claude", proposal=proposal,
        )
    )

    assert _row_for(db_session, token) is None


def test_headers_only_entries_persist_like_any_other_review(db_session):
    """`headers_only` restricts what CLAUDE sees, not what the server
    reads: confirm still validates real cell values, so the retained table
    persists identically. This pin is what keeps the flag's meaning from
    quietly drifting into 'also changes server-side storage'."""
    entry = UploadEntry(
        field_set=_field_set(), headers_only=True, tmp_path=None,
        table=_table(), provenance="fresh-claude",
    )
    token = UploadRegistry().put(entry)

    restarted = UploadRegistry()
    rehydrated = restarted.get(token)

    assert rehydrated is not None
    assert rehydrated.headers_only is True
    assert rehydrated.table.rows == _table().rows
