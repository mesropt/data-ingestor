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
accumulating unbounded state (T-04-06): the OLDEST entry is dropped first
(`OrderedDict.popitem(last=False)`), never a random one, so "the upload I'm
mid-review on" is the last thing ever evicted.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass

from ..fields.models import FieldSet
from ..parsing.table import RawTable

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
    file is unlinked, P2)."""

    field_set: FieldSet | None
    headers_only: bool
    tmp_path: str | None
    table: RawTable | None = None


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
        return self._entries.get(token)

    def pop(self, token: str) -> UploadEntry | None:
        return self._entries.pop(token, None)

    def _evict_oldest_if_over_capacity(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


#: The single registry instance every route imports and shares -- a
#: single-user local demo (CONTEXT.md) needs no per-request/per-session
#: isolation, so a module-level singleton is sufficient (Open Question 1).
registry = UploadRegistry()
