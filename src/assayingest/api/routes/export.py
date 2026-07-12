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
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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
