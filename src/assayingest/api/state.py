"""In-memory upload correlation registry (P2, RESEARCH.md Open Question 1).

Maps `upload_token` (a UUID minted on `/api/upload`) to the server-side
state a later `/api/confirm` or `/api/structural-hint/resolve` call (Plan
03) needs to re-find without trusting anything the client sends back: the
originally parsed `RawTable` (mapping-success branch), the `FieldSet` the
upload was resolved against, the `headers_only` flag, and the temp file
path -- kept alive ONLY for the still-pending structural-question branch
(the mapping-success branch unlinks its temp file immediately, Task 2).

A single-process, single-user local demo (CONTEXT.md's Phase Boundary)
makes a module-level dict sufficient -- no Redis/session store needed. A
max-count eviction (`_MAX_ENTRIES`) keeps a long demo session from
accumulating unbounded state (T-04-06): the LEAST RECENTLY USED entry is
dropped first (`OrderedDict.popitem(last=False)`, combined with `get()`
moving a touched entry to the end, IN-02), never a random one and never
purely by insertion order, so "the upload I'm mid-review on" is the last
thing ever evicted even under a burst of newer uploads. An evicted entry's
retained temp file (if any) is unlinked as it is dropped (WR-01, P2) -- the
registry is the one place a temp file's lifecycle is fully owned, so no
route needs its own eviction-cleanup logic.
"""

from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from ..domain.models import MappingProposal
from ..fields.models import FieldSet
from ..parsing.structure.date_order import DateOrder
from ..parsing.table import RawTable
from ..service import Escalation

#: A generous cap for a demo session -- large enough that a real review
#: workflow never hits it, small enough that a long-running, unattended demo
#: process cannot accumulate unbounded temp-file state.
_MAX_ENTRIES = 200


@dataclass
class UploadEntry:
    """One pending/completed upload's server-side state, keyed by
    `upload_token`. `table` is set only once a mapping has resolved (the
    structural-question branch has no table yet); `tmp_path` is set only
    while the structural-question branch still needs to re-parse the
    original file (the mapping-success branch clears it to `None` once the
    file is unlinked, P2).

    `provenance` (WR-04, audit integrity) is set to the REAL
    `"fresh-claude"`/`"auto-applied-from-profile"` value the mapping
    actually resolved through, at the exact moment `table` is set -- the
    API already knows which branch it took (`service.resolve_or_map`'s own
    `MapResult.provenance`), so this is never inferred or trusted from a
    client. `/api/confirm` reads this (never `body.provenance`) when
    writing the audit manifest, so a client cannot mislabel a fresh-Claude
    mapping as an auto-applied one (or vice versa) in the persisted
    record.

    `map_envelope`/`target_schema_name`/`vendor` (08-02) are retained ONLY
    while a reconcile question is pending (mirroring how `tmp_path` is
    retained for a structural question): a map-file upload that surfaces a
    conflict keeps the parsed map envelope + target Schema name + vendor here
    so `/api/reconcile/resolve` can re-augment and re-map WITHOUT trusting the
    client to re-send them (T-08-08). All three default to `None` (a plain
    upload never sets them); the retained DATA file is still owned by
    `tmp_path`, so no eviction/unlink change is needed for these.

    `proposal`/`schema_name`/`strictness`/`escalation` (D-10-07, Phase 10
    Plan 05) are retained ONLY while a date question is pending -- a THIRD
    retention shape, distinct from the structural/reconcile ones above:
    `table` (already a field here) + `proposal` are ENOUGH for
    `/api/date-format/resolve` to re-run `service.resolve_date_formats` +
    `validate()` with the human's per-column order, WITHOUT re-parsing the
    file and WITHOUT trusting the client to re-send anything (the T-08-08
    discipline, applied to a third question type). On this branch
    `tmp_path` is ALREADY `None` by the time this entry is built -- the data
    file left disk at parse time (mirroring the mapping-success branch's own
    cleanup), so there is nothing to clean up and nothing left to re-read.
    `schema_name` lets a future caller re-resolve which governed Schema (if
    any) the upload targeted; `strictness` preserves the validation mode the
    original mapping ran under (today always `"strict"` -- no route yet lets
    a client vary it, but the field exists so a future one can without a
    second retention mechanism). `escalation` carries forward the EXACT
    Python-vs-Claude split the original resolution already computed (D-10-03)
    -- never recomputed at resolve time, since nothing about the crosswalk
    coverage changes between the date question and its answer.

    `date_answers` (D-10-08, Phase 10 Plan 08) is the ONE thing the server
    genuinely cannot re-derive: the human's per-column date ORDER
    (`day_first`/`month_first`), keyed by target field name -- set ONLY by
    `/api/date-format/resolve` onto the fresh entry it re-puts once a date
    question is answered. It is NEVER a strptime format string (T-10-21's
    invariant, carried one hop further): `/api/confirm` reads it and calls
    `service.resolve_date_formats(..., answers=date_answers)` itself, against
    the RETAINED table and its OWN freshly-rebuilt proposal, to derive the
    concrete format server-side -- it never trusts a format the client
    supplies. Defaulted `None` so every existing construction site (a plain
    upload, a structural/reconcile question, or a date question that was
    never answered) is untouched, and `resolve_date_formats(answers=None)`
    still resolves whatever it can from the column's own evidence alone."""

    field_set: FieldSet | None
    headers_only: bool
    tmp_path: str | None
    table: RawTable | None = None
    provenance: str | None = None
    map_envelope: dict | None = None
    target_schema_name: str | None = None
    vendor: str | None = None
    proposal: MappingProposal | None = None
    schema_name: str | None = None
    strictness: str = "strict"
    escalation: Escalation | None = None
    date_answers: dict[str, DateOrder] | None = None


class UploadRegistry:
    """The `upload_token -> UploadEntry` map every route shares via the
    module-level `registry` instance below."""

    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._entries: OrderedDict[str, UploadEntry] = OrderedDict()
        self._max_entries = max_entries

    def put(self, entry: UploadEntry) -> str:
        """Mint a fresh `upload_token` and store `entry` under it, evicting
        the oldest entry first if this push would exceed capacity."""
        token = str(uuid.uuid4())
        self._entries[token] = entry
        self._evict_oldest_if_over_capacity()
        return token

    def get(self, token: str) -> UploadEntry | None:
        """IN-02: a hit refreshes recency by moving the entry to the end of
        the eviction order -- without this, an upload a curator is still
        reviewing (repeatedly `get()`-ed by `/api/confirm` or read-only
        lookups) could still be evicted purely because it was CREATED
        before a later burst of uploads, even though it is the most
        recently ACCESSED entry of them all."""
        entry = self._entries.get(token)
        if entry is not None:
            self._entries.move_to_end(token)
        return entry

    def pop(self, token: str) -> UploadEntry | None:
        return self._entries.pop(token, None)

    def _evict_oldest_if_over_capacity(self) -> None:
        while len(self._entries) > self._max_entries:
            _, evicted = self._entries.popitem(last=False)
            self._unlink_if_retained(evicted)

    @staticmethod
    def _unlink_if_retained(entry: UploadEntry) -> None:
        """WR-01/P2: an evicted entry's retained temp file (holding
        uploaded cell values) must not survive on disk with no remaining
        reference. Guarded on both counts: a mapping-resolved entry's
        `tmp_path` is already `None` (nothing to unlink), and a raced or
        already-unlinked file is not itself a bug worth surfacing here."""
        if entry.tmp_path is None:
            return
        try:
            os.unlink(entry.tmp_path)
        except FileNotFoundError:
            pass


#: The single registry instance every route imports and shares -- a
#: single-user local demo (CONTEXT.md) needs no per-request/per-session
#: isolation, so a module-level singleton is sufficient (Open Question 1).
registry = UploadRegistry()
