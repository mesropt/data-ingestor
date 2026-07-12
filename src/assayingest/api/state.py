"""Upload correlation registry (P2, RESEARCH.md Open Question 1).

Maps `upload_token` (a UUID minted on `/api/upload`) to the server-side
state a later `/api/confirm` or `/api/structural-hint/resolve` call (Plan
03) needs to re-find without trusting anything the client sends back: the
originally parsed `RawTable` (mapping-success branch), the `FieldSet` the
upload was resolved against, the `headers_only` flag, and the temp file
path -- kept alive ONLY for the still-pending structural-question branch
(the mapping-success branch unlinks its temp file immediately, Task 2).

REVIEW-READY ENTRIES SURVIVE A RESTART (quick 260712). Memory alone lost a
curator's mid-review work to every `--reload` cycle, deploy, LRU eviction,
and worker switch -- Confirm then 404ed and threw the review away. So `put`
now writes THROUGH to the `pending_uploads` Postgres table for exactly the
entries a Review screen depends on (mapping resolved: `table` +
`field_set`, no pending question, no temp file), and `get`/`pop` fall back
to that table on a memory miss, rehydrating as if the restart never
happened -- including `date_answers`, the one thing the server cannot
re-derive. Question-branch entries (a retained per-process temp file, a
half-answered date question) stay memory-only: their lifecycle is a modal
interaction, and a temp path is meaningless to any other process.

THE PRIVACY DECISION, made deliberately: persisting an entry puts the
uploaded file's CELL VALUES at rest in the database. That is tolerable only
because a pending upload is transient BY CONSTRUCTION here -- every
persisted row carries a TTL (`_PENDING_TTL_SECONDS`; expired rows are
deleted on the lookup that finds them and swept on every persist), and a
successful `/api/confirm` purges the row immediately (the route pops it).
The rows never outlive the review they exist for. `headers_only` keeps its
exact meaning -- it restricts what CLAUDE sees, never what the server reads
or retains: confirm validates real cell values either way, so a
headers-only entry persists identically.

In-memory behaviour is unchanged: max-count eviction (`_MAX_ENTRIES`) keeps
a long session from accumulating unbounded state (T-04-06); the LEAST
RECENTLY USED entry is dropped first (`OrderedDict.popitem(last=False)`,
combined with `get()` moving a touched entry to the end, IN-02). Evicting a
persisted entry from memory is now harmless -- it rehydrates from the table
on the next lookup. An evicted entry's retained temp file (if any) is still
unlinked as it is dropped (WR-01, P2) -- the registry remains the one place
a temp file's lifecycle is fully owned, so no route needs its own
eviction-cleanup logic.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..domain.models import MappingProposal
from ..fields.loader import from_dict as _field_set_from_dict
from ..fields.models import FieldSet
from ..parsing.structure.date_order import DateOrder
from ..parsing.table import RawTable
from ..persistence.engine import new_session
from ..service import Escalation
from .pending_store import PostgresPendingUploadStore

#: A generous cap for a demo session -- large enough that a real review
#: workflow never hits it, small enough that a long-running, unattended demo
#: process cannot accumulate unbounded temp-file state.
_MAX_ENTRIES = 200

#: How long a persisted pending upload may sit unconfirmed before its rows
#: leave the database. A review is a same-session activity; a full day
#: absorbs any realistic deploy/restart/lunch gap without letting uploaded
#: cell values quietly become a permanent archive nobody asked for.
_PENDING_TTL_SECONDS = 24 * 60 * 60


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
    #: The CLIENT's original filename (quick 260712), retained so a resolve
    #: route's `MappingResponse` can name the source file back to the human
    #: instead of the raw upload token. Never a path -- only ever the display
    #: label. `table.source_name` cannot serve here: the parser saw a
    #: tempfile-generated name, not the file the curator actually chose.
    source_file_name: str | None = None


class UploadRegistry:
    """The `upload_token -> UploadEntry` map every route shares via the
    module-level `registry` instance below -- an in-memory LRU in front of
    the `pending_uploads` table, which holds the review-ready entries a
    restart must not destroy (module docstring)."""

    def __init__(
        self, max_entries: int = _MAX_ENTRIES, ttl_seconds: int = _PENDING_TTL_SECONDS
    ) -> None:
        self._entries: OrderedDict[str, UploadEntry] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def put(self, entry: UploadEntry) -> str:
        """Mint a fresh `upload_token` and store `entry` under it, evicting
        the oldest entry first if this push would exceed capacity. A
        review-ready entry is also written through to `pending_uploads`, so
        the review it backs survives this process."""
        token = str(uuid.uuid4())
        self._entries[token] = entry
        self._evict_oldest_if_over_capacity()
        if _is_review_ready(entry):
            self._persist(token, entry)
        return token

    def get(self, token: str) -> UploadEntry | None:
        """IN-02: a hit refreshes recency by moving the entry to the end of
        the eviction order -- without this, an upload a curator is still
        reviewing (repeatedly `get()`-ed by `/api/confirm` or read-only
        lookups) could still be evicted purely because it was CREATED
        before a later burst of uploads, even though it is the most
        recently ACCESSED entry of them all.

        A memory miss falls back to `pending_uploads`: a token this process
        never saw (restart, other worker, LRU-evicted) rehydrates and is
        re-adopted into memory, so every later same-process lookup behaves
        exactly as if the restart never happened."""
        entry = self._entries.get(token)
        if entry is not None:
            self._entries.move_to_end(token)
            return entry
        entry = self._load_persisted(token)
        if entry is not None:
            self._entries[token] = entry
            self._evict_oldest_if_over_capacity()
        return entry

    def pop(self, token: str) -> UploadEntry | None:
        """Remove and return the entry -- from memory, or rehydrated from
        `pending_uploads` after a restart. A review-ready entry's persisted
        row is deleted with it: pop is how `/api/confirm` purges a
        successfully confirmed upload, and the uploaded cell values must
        not outlive the review (module docstring). Question-branch entries
        were never persisted, so their pop touches no database at all."""
        entry = self._entries.pop(token, None)
        if entry is None:
            entry = self._load_persisted(token)
        if entry is not None and _is_review_ready(entry):
            self._delete_persisted(token)
        return entry

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

    # --- the pending_uploads write-through (quick 260712) --------------------

    def _persist(self, token: str, entry: UploadEntry) -> None:
        """Write one review-ready entry through to `pending_uploads`,
        sweeping every already-expired row first -- the TTL must not depend
        on someone eventually asking for a dead token."""
        now = _utc_now()
        expires = now + timedelta(seconds=self._ttl_seconds)
        with new_session() as session:
            store = PostgresPendingUploadStore(session)
            store.delete_expired(_to_iso(now))
            store.save(token, _entry_to_json(entry), _to_iso(now), _to_iso(expires))

    def _load_persisted(self, token: str) -> UploadEntry | None:
        """The persisted entry for `token`, or `None` -- deleting, rather
        than returning, a row whose TTL has passed: an expired review is
        gone, and its cell values leave the database on the very lookup
        that discovers them."""
        with new_session() as session:
            store = PostgresPendingUploadStore(session)
            row = store.load(token)
            if row is None:
                return None
            entry_json, expires_at = row
            if expires_at <= _to_iso(_utc_now()):
                store.delete(token)
                return None
        return _entry_from_json(entry_json)

    def _delete_persisted(self, token: str) -> None:
        with new_session() as session:
            PostgresPendingUploadStore(session).delete(token)


def _is_review_ready(entry: UploadEntry) -> bool:
    """True for the one retention shape a Review screen (and therefore
    `/api/confirm`) depends on: mapping resolved (`table` + `field_set`),
    no pending structural/reconcile/date question, no per-process temp file.
    Only these entries persist -- a retained `tmp_path` is meaningless to
    any other process, and a half-answered question is a modal interaction
    whose lifecycle deliberately stays in memory (module docstring)."""
    return (
        entry.table is not None
        and entry.field_set is not None
        and entry.tmp_path is None
        and entry.proposal is None
        and entry.map_envelope is None
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(moment: datetime) -> str:
    """Fixed-width UTC ISO-8601, so lexicographic order IS chronological
    order and the store's SQL string comparison on `expires_at` is sound.
    Never `datetime.isoformat()`, which drops the microsecond field when it
    happens to be zero and would silently break that width guarantee."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _entry_to_json(entry: UploadEntry) -> str:
    """The `UploadEntry -> pending_uploads.entry_json` boundary serializer.

    Persists exactly what a post-restart `/api/confirm` needs to rebuild
    the gate's inputs, and nothing that only a pending QUESTION needs:
    `proposal`/`map_envelope`/`target_schema_name`/`vendor`/`escalation`
    are all `None` on a review-ready entry by `_is_review_ready`'s own
    definition, and `tmp_path` is likewise always `None` -- so a rehydrated
    entry can never resurrect a temp-file reference this process does not
    own. `date_answers` serializes as plain order strings (`day_first`/
    `month_first`), preserving T-10-21's invariant that a strptime format
    is derived server-side at confirm time, never stored or transported."""
    return json.dumps(
        {
            "field_set": entry.field_set.to_dict(),
            "headers_only": entry.headers_only,
            "table": {
                "headers": entry.table.headers,
                "rows": entry.table.rows,
                "source_name": entry.table.source_name,
                "sheet_name": entry.table.sheet_name,
                "column_locales": entry.table.column_locales,
            },
            "provenance": entry.provenance,
            "schema_name": entry.schema_name,
            "strictness": entry.strictness,
            "source_file_name": entry.source_file_name,
            "date_answers": (
                {field: order.value for field, order in entry.date_answers.items()}
                if entry.date_answers is not None
                else None
            ),
        },
        ensure_ascii=False,
    )


def _entry_from_json(payload: str) -> UploadEntry:
    """The `pending_uploads.entry_json -> UploadEntry` boundary translator
    (the `_entity_to_profile` analog for this table).

    `allow_empty=True` on the field-set rebuild is NOT a weakening of the
    upload-time guard: this payload was serialized by the server from a
    `FieldSet` that already passed `from_dict`'s validation at its original
    boundary. Re-raising here would turn a legitimately retained review
    into a 500 on the unlucky edge (an empty governed Schema) instead of
    letting the confirm gate refuse it honestly."""
    raw = json.loads(payload)
    table = raw["table"]
    date_answers = raw["date_answers"]
    return UploadEntry(
        field_set=_field_set_from_dict(raw["field_set"], allow_empty=True),
        headers_only=raw["headers_only"],
        tmp_path=None,
        table=RawTable(
            headers=table["headers"],
            rows=table["rows"],
            source_name=table["source_name"],
            sheet_name=table["sheet_name"],
            column_locales=table["column_locales"],
        ),
        provenance=raw["provenance"],
        schema_name=raw["schema_name"],
        strictness=raw["strictness"],
        # `.get`, not `[...]`: rows persisted before this key existed have
        # nothing truthful to offer here, and a display label is the one
        # field an old row may honestly lack.
        source_file_name=raw.get("source_file_name"),
        date_answers=(
            {field: DateOrder(order) for field, order in date_answers.items()}
            if date_answers is not None
            else None
        ),
    )


#: The single registry instance every route imports and shares -- a
#: single-user local demo (CONTEXT.md) needs no per-request/per-session
#: isolation, so a module-level singleton is sufficient (Open Question 1).
registry = UploadRegistry()
