"""One confirmed group's N export directories as a single zip (11-08,
SHEET-01/D-11-10): one directory per sheet, each holding that member's
`export.csv` / `export.xlsx` / `export.json` / `manifest.json` -- the four
fixed filenames `service.export` writes, safe there because every member
owns its own run directory.

Stdlib `zipfile`, deliberately (RESEARCH Don't-Hand-Roll): no third-party
archive dependency, no hand-rolled writer.

ZIP-SLIP (T-11-28, Pitfall 7): a worksheet title is arbitrary user text, and
inside an archive it becomes a PATH COMPONENT the extracting tool will
honour -- `../../evil` written verbatim would place a member's files OUTSIDE
the directory the curator extracts into. Entry names are therefore sanitized
through an ALLOWLIST (`[A-Za-z0-9._ -]`), never a denylist, with a
`sheet_<index>` fallback for a title the allowlist empties and an index
suffix when two titles sanitize to the same name -- validated BEFORE any
name reaches the archive, exactly the discipline `api/routes/export.py`'s
`_RUN_ID_PATTERN` applies to `run_id` before it becomes a filesystem path.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

#: The four fixed files `service.export` writes into every run's directory.
#: A member directory missing one of them (a partially-served run) costs the
#: archive that one file, never the other members' files.
_MEMBER_FILES = ("export.csv", "export.xlsx", "export.json", "manifest.json")

#: The ALLOWLIST, inverted for `re.sub`: every character NOT in
#: `[A-Za-z0-9._ -]` is dropped. An allowlist, never a denylist -- a denylist
#: is a bet that the author enumerated every hostile character, and that bet
#: loses (T-11-28).
_DISALLOWED = re.compile(r"[^A-Za-z0-9._ -]")

#: `.` alone is allowlisted (real titles carry them), but a RUN of dots is a
#: traversal fragment waiting to be reassembled -- `../../evil` survives the
#: allowlist as `....evil`. Runs collapse to a single dot before the strip.
_DOT_RUNS = re.compile(r"\.{2,}")


def build_group_archive(run_dirs_by_sheet: dict[str, Path], out_path: Path) -> Path:
    """Write every member's export files into one zip at `out_path`.

    `run_dirs_by_sheet` maps a member's sheet name (the archive directory it
    will appear under, after sanitization) to its `EXPORT_BASE_DIR/{run_id}`
    directory; iteration order is preserved, so the caller controls whether
    the archive reads in workbook order. Returns `out_path`.

    Raises `ValueError` for an empty group -- an archive with no members is
    nothing a caller ever legitimately wants, and writing an empty zip would
    hand the curator a "successful" download containing none of their data.
    """
    if not run_dirs_by_sheet:
        raise ValueError(
            "The archive was not written: there are no member export "
            "directories to include."
        )
    used: set[str] = set()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, (sheet_name, run_dir) in enumerate(run_dirs_by_sheet.items()):
            entry_dir = _safe_entry_name(sheet_name, index)
            # Two titles may legitimately sanitize to one name (`Data/2025`
            # and `Data\\2025`) -- an index suffix keeps both, because a
            # silent overwrite would ship one member's numbers under the
            # other's name.
            while entry_dir in used:
                entry_dir = f"{entry_dir}_{index}"
            used.add(entry_dir)
            for filename in _MEMBER_FILES:
                source = Path(run_dir) / filename
                if source.is_file():
                    archive.write(source, arcname=f"{entry_dir}/{filename}")
    return out_path


def _safe_entry_name(sheet_name: str, index: int) -> str:
    """`sheet_name` reduced to a single safe path component (T-11-28).

    Allowlist first, then dot-run collapse (so no `..` fragment survives),
    then an edge strip (a leading dot hides the directory on extraction; a
    trailing one is Windows-hostile). A title the allowlist empties falls
    back to `sheet_<index>` -- every member gets a directory, whatever its
    title was made of."""
    cleaned = _DISALLOWED.sub("", sheet_name)
    cleaned = _DOT_RUNS.sub(".", cleaned)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return f"sheet_{index}"
    return cleaned
