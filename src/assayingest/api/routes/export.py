"""GET /api/export/{run_id}/{fmt} (EXPORT-02/03/04) -- serves the files
`/api/confirm` (Task 2) already wrote via `service.export` into
`EXPORT_BASE_DIR/{run_id}/`. No new writer logic here at all (PATTERNS.md
forbids reimplementing `export/writers.py`) -- this route's only job is
picking the right file and `Content-Type` for one of four fixed formats.

`run_id` is never trusted as a client-controlled path (T-04-13): it is
validated against the exact shape `uuid.uuid4()` (the only thing that ever
mints one, in `confirm.py`) produces before ever touching the filesystem --
a percent-encoded traversal string like `..%2F..%2Fetc%2Fpasswd` fails this
check and never reaches `EXPORT_BASE_DIR / run_id`.

`GET /api/export/group/{group_id}/archive` (11-08, SHEET-01/D-11-10) serves
one confirmed group as a single zip, one directory per sheet. It is a LOOKUP
over runs `/api/confirm` already recorded, never a gate of its own (T-11-31):
a `run_id` exists only because `service.confirm`'s `NotReadyError` gate
passed for that member, and a group with any member still unrecorded is
refused outright -- the archive is a convenience OVER the per-member gates,
never a bypass of any of them. `group_id` gets `_RUN_ID_PATTERN`'s exact
validate-before-filesystem treatment (T-11-29), and unlike the per-run route
above it is `require_user`-gated (D-10-13/T-11-30): one URL here downloads a
whole workbook's confirmed cell values at once.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ...auth.models import User
from ...export.archive import build_group_archive
from ..deps import require_user
from ..state import groups
from .confirm import EXPORT_BASE_DIR

router = APIRouter()

#: fmt -> (filename inside the run's export dir, Content-Type). A fixed
#: allowlist (T-04-13) -- `fmt` never becomes a filename or path component.
_FORMATS: dict[str, tuple[str, str]] = {
    "csv": ("export.csv", "text/csv"),
    "xlsx": (
        "export.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "json": ("export.json", "application/json"),
    "manifest": ("manifest.json", "application/json"),
}

#: `run_id` is always a `str(uuid.uuid4())` minted by `confirm.py` -- no
#: other value is ever a legitimate run_id, so a request that doesn't match
#: this shape (e.g. a path-traversal attempt) is rejected before any
#: filesystem access (T-04-13).
_RUN_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@router.get("/api/export/{run_id}/{fmt}")
def download_export(run_id: str, fmt: str) -> FileResponse:
    if fmt not in _FORMATS:
        raise HTTPException(status_code=404, detail=f"unknown export format '{fmt}'")
    if not _RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=404, detail=f"no export run '{run_id}'")

    filename, content_type = _FORMATS[fmt]
    path = EXPORT_BASE_DIR / run_id / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"no '{fmt}' export for run '{run_id}'"
        )
    return FileResponse(path, media_type=content_type, filename=filename)


#: A zip filename is derived from the CLIENT's original workbook name -- the
#: same allowlist discipline `export.archive._safe_entry_name` applies to a
#: worksheet title, because a filename in a Content-Disposition header is
#: every bit as client-influenced as an entry name inside the zip.
_FILENAME_DISALLOWED = re.compile(r"[^A-Za-z0-9._ -]")


@router.get("/api/export/group/{group_id}/archive")
def download_group_archive(
    group_id: str,
    # D-10-13/T-11-30: a gate only, not a value this route reads -- the
    # dependency's sole job is to raise 401 for a signed-out request. The
    # per-run route above predates the gate; this one downloads a whole
    # workbook's confirmed cell values in one URL and is not served anonymously.
    user: User = Depends(require_user),
) -> FileResponse:
    # T-11-29: `group_id` is only ever a `str(uuid.uuid4())` minted by
    # `GroupRegistry.put` -- anything else is rejected BEFORE any lookup,
    # path join, or archive build, exactly as `_RUN_ID_PATTERN` guards the
    # per-run route above.
    if not _RUN_ID_PATTERN.match(group_id):
        raise HTTPException(status_code=404, detail=f"no export group '{group_id}'")

    group = groups.get(group_id)
    if group is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Nothing was downloaded: this group is no longer available on "
                "the server — group bookkeeping is kept in memory only. Each "
                "confirmed dataset's own export can still be downloaded from "
                "its Review tab."
            ),
        )

    # T-11-31: a LOOKUP, not a gate. A member has a recorded run ONLY because
    # `service.confirm`'s existing `NotReadyError` gate passed for it and its
    # export was written -- so "every member has a run" is the per-member
    # gates' verdict, read back. No readiness is re-derived or aggregated
    # here, and an unconfirmed member is never silently omitted: the refusal
    # names how many datasets are still outstanding.
    unconfirmed = [sheet for sheet in group.members if sheet not in group.runs]
    if unconfirmed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"The archive was not built: {len(unconfirmed)} of "
                f"{len(group.members)} datasets in this group are still "
                "unconfirmed. Confirm and export every sheet's dataset, then "
                "download the archive again."
            ),
        )

    # Workbook order, not confirm order: `group.members` preserves the sheet
    # order the resolve route recorded, so the archive reads like the workbook.
    run_dirs = {sheet: EXPORT_BASE_DIR / group.runs[sheet] for sheet in group.members}
    handle, tmp_name = tempfile.mkstemp(suffix=".zip")
    os.close(handle)
    build_group_archive(run_dirs, Path(tmp_name))
    return FileResponse(
        tmp_name,
        media_type="application/zip",
        filename=_archive_filename(group.source_file_name),
        # The zip is a per-request temp file; it leaves disk as soon as the
        # response is sent, so no download ever accumulates server state.
        background=BackgroundTask(_unlink_quietly, tmp_name),
    )


def _archive_filename(source_file_name: str | None) -> str:
    """The download's `Content-Disposition` filename, from the client's
    original workbook name -- allowlist-sanitized (T-11-28's discipline) with
    a neutral fallback when nothing safe survives."""
    stem = Path(source_file_name).stem if source_file_name else ""
    cleaned = _FILENAME_DISALLOWED.sub("", stem).strip(" .")
    return f"{cleaned or 'group-export'}.zip"


def _unlink_quietly(path: str) -> None:
    """Remove the served temp zip, tolerating one already gone -- a missing
    file at unlink time is not itself a bug worth surfacing; a file left
    behind is."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
