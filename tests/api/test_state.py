"""api/state.py -- UploadRegistry eviction cleanup + access-ordered recency,
TDD RED-first (Phase 4 code-review fixes, WR-01/IN-02).

`UploadRegistry` is exercised directly (no HTTP layer) -- this targets the
registry's own eviction/recency contract in isolation, mirroring
`tests/api/test_confirm_gate.py`'s "seed the registry directly" idiom.
"""

from __future__ import annotations

from assayingest.api.state import UploadEntry, UploadRegistry


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
