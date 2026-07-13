"""api/state.py -- UploadRegistry eviction cleanup + access-ordered recency,
TDD RED-first (Phase 4 code-review fixes, WR-01/IN-02).

`UploadRegistry` is exercised directly (no HTTP layer) -- this targets the
registry's own eviction/recency contract in isolation, mirroring
`tests/api/test_confirm_gate.py`'s "seed the registry directly" idiom.
"""

from __future__ import annotations

import json

from assayingest.api.state import (
    GroupRegistry,
    UploadEntry,
    UploadGroup,
    UploadRegistry,
    _entry_from_json,
    _entry_to_json,
)
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable


def _entry(tmp_path: str | None) -> UploadEntry:
    return UploadEntry(field_set=None, headers_only=False, tmp_path=tmp_path)


# --- WR-01: eviction must not leak the evicted entry's temp file --------------


def test_eviction_unlinks_the_evicted_entrys_retained_temp_file(tmp_path):
    """A structural-question entry carries a live tmp_path holding uploaded
    cell values -- dropping it from the registry (over-capacity eviction)
    without unlinking leaks those values to disk with no remaining
    reference (P2 confidentiality)."""
    registry = UploadRegistry(max_entries=1)
    old_file = tmp_path / "old.csv"
    old_file.write_text("a,b\n1,2\n", encoding="utf-8")
    new_file = tmp_path / "new.csv"
    new_file.write_text("a,b\n3,4\n", encoding="utf-8")

    registry.put(_entry(str(old_file)))
    registry.put(_entry(str(new_file)))  # over capacity -- evicts old_file's entry

    assert not old_file.exists()
    assert new_file.exists()


def test_eviction_tolerates_an_entry_with_no_tmp_path():
    """The mapping-success branch already clears tmp_path to None once its
    file is unlinked -- eviction of such an entry must not raise trying to
    unlink a path that was never set."""
    registry = UploadRegistry(max_entries=1)
    registry.put(_entry(None))
    registry.put(_entry(None))  # must not raise


# --- IN-02: get() must refresh recency, not just insertion order --------------


def test_get_moves_the_touched_entry_to_the_end_so_it_survives_a_later_eviction(
    tmp_path,
):
    """A curator's long-lived, mid-review upload must not be evicted by a
    burst of newer uploads it was accessed more recently than -- `get()`
    must move the touched entry to the end of the eviction order, mirroring
    an LRU cache's own access-then-touch contract."""
    registry = UploadRegistry(max_entries=2)
    survivor_file = tmp_path / "survivor.csv"
    survivor_file.write_text("a,b\n1,2\n", encoding="utf-8")
    stale_file = tmp_path / "stale.csv"
    stale_file.write_text("a,b\n3,4\n", encoding="utf-8")
    fresh_file = tmp_path / "fresh.csv"
    fresh_file.write_text("a,b\n5,6\n", encoding="utf-8")

    survivor_token = registry.put(_entry(str(survivor_file)))
    registry.put(_entry(str(stale_file)))

    registry.get(survivor_token)  # touch -- must move survivor to the end

    registry.put(_entry(str(fresh_file)))  # over capacity -- evicts the LEAST recently used

    assert registry.get(survivor_token) is not None
    assert survivor_file.exists()
    assert not stale_file.exists()  # evicted -- it was the least recently used
    assert fresh_file.exists()


# --- SHEET-03: `origin_sheet` round-trips through the persistence boundary ----


def _review_ready_entry(origin_sheet: str | None) -> UploadEntry:
    return UploadEntry(
        field_set=FieldSet(fields=(Field(name="compound_id"),)),
        headers_only=False,
        tmp_path=None,
        table=RawTable(
            headers=["cmpd"],
            rows=[["NVS-1"]],
            source_name="tmpxyz.xlsx",
            sheet_name=None,
            origin_sheet=origin_sheet,
        ),
        provenance="fresh-claude",
    )


def test_entry_json_round_trip_preserves_the_tables_origin_sheet():
    """SHEET-03/D-11-15: the worksheet a row came from is the provenance the
    export writes on EVERY ingest. A pending upload that crosses a restart
    without it would export rows whose source sheet is silently blank -- a
    traceability column that only sometimes exists is not one."""
    rehydrated = _entry_from_json(_entry_to_json(_review_ready_entry("Week 2")))

    assert rehydrated.table is not None
    assert rehydrated.table.origin_sheet == "Week 2"
    assert rehydrated.table.sheet_name is None  # the tag stays independent


def test_entry_json_round_trip_preserves_a_none_origin_sheet_for_a_csv():
    rehydrated = _entry_from_json(_entry_to_json(_review_ready_entry(None)))

    assert rehydrated.table is not None
    assert rehydrated.table.origin_sheet is None


def test_a_row_persisted_before_origin_sheet_existed_still_rehydrates():
    """The `.get()` idiom (already used for `source_file_name`): a
    `pending_uploads` row written before this key existed has nothing
    truthful to offer here, and must rehydrate rather than 500 on a
    KeyError -- a curator's mid-review upload must survive the deploy that
    ADDED provenance, not be destroyed by it."""
    old_payload = json.loads(_entry_to_json(_review_ready_entry("Week 2")))
    del old_payload["table"]["origin_sheet"]  # as an older server wrote it

    rehydrated = _entry_from_json(json.dumps(old_payload))

    assert rehydrated.table is not None
    assert rehydrated.table.origin_sheet is None


# --- SHEET-01/D-11-20: the run group -- a group id over N ORDINARY tokens ------


def test_the_group_registry_mints_a_server_side_id_and_returns_the_group():
    """T-11-25: the `group_id` is a server-minted uuid4, exactly like every
    `upload_token` -- the client never supplies one, and never chooses
    anything but among server-retained options."""
    groups = GroupRegistry()

    group_id = groups.put(
        UploadGroup(members={"Week 1": "tok-1", "Week 2": "tok-2"}, source_file_name="zephyr.xlsx")
    )

    assert group_id
    assert group_id not in ("Week 1", "tok-1")  # nothing the caller supplied
    group = groups.get(group_id)
    assert group is not None
    assert group.members == {"Week 1": "tok-1", "Week 2": "tok-2"}
    assert group.runs == {}
    assert group.source_file_name == "zephyr.xlsx"


def test_two_groups_never_share_an_id():
    groups = GroupRegistry()

    first = groups.put(UploadGroup(members={"A": "t1"}))
    second = groups.put(UploadGroup(members={"A": "t1"}))

    assert first != second


def test_an_unknown_group_id_returns_none_and_never_raises():
    """A group is memory-only (see `GroupRegistry`'s docstring): a restart
    loses the "download all" convenience, never a curator's review. A lookup
    for a group this process never saw is therefore a NORMAL outcome, not an
    error -- the caller decides what to say about it."""
    assert GroupRegistry().get("no-such-group") is None


def test_record_run_accumulates_one_run_id_per_confirmed_sheet():
    """D-11-08: N INDEPENDENT datasets. Each member confirms on its OWN gate
    and mints its OWN run, so the group only ever ACCUMULATES what already
    happened -- it never gates, aggregates, or confirms anything itself."""
    groups = GroupRegistry()
    group_id = groups.put(UploadGroup(members={"Week 1": "tok-1", "Week 2": "tok-2"}))

    groups.record_run(group_id, "Week 1", "run-a")
    groups.record_run(group_id, "Week 2", "run-b")

    assert groups.get(group_id).runs == {"Week 1": "run-a", "Week 2": "run-b"}


def test_record_run_on_an_unknown_group_is_a_no_op_and_never_raises():
    """The bookkeeping a group offers is a convenience. An expired or
    never-seen group must not turn a SUCCESSFUL confirm -- a run already
    written to disk -- into a 500."""
    GroupRegistry().record_run("no-such-group", "Week 1", "run-a")  # must not raise


def test_entry_json_round_trip_preserves_the_group_id():
    entry = _review_ready_entry("Week 2")
    entry.group_id = "grp-1"

    rehydrated = _entry_from_json(_entry_to_json(entry))

    assert rehydrated.group_id == "grp-1"


def test_a_row_persisted_before_group_id_existed_still_rehydrates():
    old_payload = json.loads(_entry_to_json(_review_ready_entry("Week 2")))
    del old_payload["group_id"]  # as an older server wrote it

    rehydrated = _entry_from_json(json.dumps(old_payload))

    assert rehydrated.group_id is None
