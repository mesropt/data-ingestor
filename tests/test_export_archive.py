"""`export.archive.build_group_archive` (11-08, SHEET-01/D-11-10) -- one
confirmed group's N export directories become ONE zip, one directory per
sheet, each holding that member's `export.csv` / `export.xlsx` /
`export.json` / `manifest.json`.

TDD RED-first. Mirrors `tests/test_export_writers.py`'s shape: a `_member_dir`
factory, per-behaviour sections, byte-level assertions against the written
artifact.

THE ZIP-SLIP TESTS ARE THE POINT (T-11-28, RESEARCH Pitfall 7): a worksheet
title is arbitrary user text, and inside an archive it becomes a PATH
COMPONENT the extracting tool will honour. A title of `../../evil` must never
produce an entry that escapes the archive root -- the sanitizer is an
ALLOWLIST (`[A-Za-z0-9._ -]`), never a denylist, exactly the
validate-before-filesystem discipline `api/routes/export.py`'s
`_RUN_ID_PATTERN` already applies to `run_id`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from assayingest.export.archive import build_group_archive

#: The four fixed files `service.export` writes into every run's directory --
#: fixed names are safe there because every member owns its own directory.
_MEMBER_FILES = ("export.csv", "export.xlsx", "export.json", "manifest.json")


def _member_dir(
    tmp_path: Path, name: str, *, files: tuple[str, ...] = _MEMBER_FILES
) -> Path:
    """One member's export directory, seeded with distinguishable content so a
    collision test can tell WHOSE file survived."""
    directory = tmp_path / name
    directory.mkdir()
    for filename in files:
        (directory / filename).write_text(f"{name}:{filename}", encoding="utf-8")
    return directory


def _entry_names(archive_path: Path) -> list[str]:
    with zipfile.ZipFile(archive_path) as archive:
        return archive.namelist()


# --- the happy path: one directory per sheet, four files each ------------------


def test_the_archive_holds_one_directory_per_sheet_with_all_four_files(tmp_path):
    dir_a = _member_dir(tmp_path, "run_a")
    dir_b = _member_dir(tmp_path, "run_b")
    out = tmp_path / "group.zip"

    result = build_group_archive({"Week 1": dir_a, "Week 2": dir_b}, out)

    assert result == out
    names = set(_entry_names(out))
    assert names == {
        f"{sheet}/{filename}"
        for sheet in ("Week 1", "Week 2")
        for filename in _MEMBER_FILES
    }


def test_each_entry_carries_its_own_members_bytes(tmp_path):
    """The zip must hold each member's OWN files -- never one member's content
    under two names."""
    dir_a = _member_dir(tmp_path, "run_a")
    dir_b = _member_dir(tmp_path, "run_b")
    out = tmp_path / "group.zip"

    build_group_archive({"Week 1": dir_a, "Week 2": dir_b}, out)

    with zipfile.ZipFile(out) as archive:
        assert archive.read("Week 1/export.csv") == b"run_a:export.csv"
        assert archive.read("Week 2/export.csv") == b"run_b:export.csv"


# --- zip-slip (T-11-28): a worksheet title cannot escape the archive root ------


def test_a_hostile_sheet_title_cannot_escape_the_archive_root(tmp_path):
    """A sheet titled `../../evil` must not produce an entry an extractor would
    write OUTSIDE the directory the archive is opened into."""
    dir_a = _member_dir(tmp_path, "run_a")
    out = tmp_path / "group.zip"

    build_group_archive({"../../evil": dir_a}, out)

    for name in _entry_names(out):
        assert ".." not in name
        assert not name.startswith("/")
        assert not name.startswith("\\")
        assert ":" not in name  # no Windows drive-letter escape either


def test_a_path_bearing_title_does_not_create_a_nested_path(tmp_path):
    """`Data/2025` (or `Data\\2025`) is a TITLE, not a directory tree -- the
    only separator in any entry name is the single one between the sheet's
    directory and its file."""
    dir_a = _member_dir(tmp_path, "run_a")
    dir_b = _member_dir(tmp_path, "run_b")
    out = tmp_path / "group.zip"

    build_group_archive({"Data/2025": dir_a, "Data\\2026": dir_b}, out)

    for name in _entry_names(out):
        directory, _, filename = name.partition("/")
        assert "/" not in directory
        assert "\\" not in directory
        assert "/" not in filename
        assert "\\" not in filename


# --- sanitizer fallbacks: nothing nameless, nothing overwritten ----------------


def test_a_title_of_only_disallowed_characters_falls_back_to_an_indexed_name(tmp_path):
    dir_a = _member_dir(tmp_path, "run_a")
    out = tmp_path / "group.zip"

    build_group_archive({"@@@": dir_a}, out)

    names = _entry_names(out)
    assert all(name.startswith("sheet_0/") for name in names)
    assert len(names) == len(_MEMBER_FILES)


def test_two_titles_that_sanitize_identically_do_not_overwrite_each_other(tmp_path):
    """`Data/2025` and `Data\\2025` both sanitize to `Data2025`. Silent
    overwrite would ship one member's numbers under the other's name -- the
    exact 'trust the numbers' violation this tool exists to prevent."""
    dir_a = _member_dir(tmp_path, "run_a")
    dir_b = _member_dir(tmp_path, "run_b")
    out = tmp_path / "group.zip"

    build_group_archive({"Data/2025": dir_a, "Data\\2025": dir_b}, out)

    names = _entry_names(out)
    assert len(names) == 2 * len(_MEMBER_FILES)  # nothing was overwritten
    directories = {name.partition("/")[0] for name in names}
    assert len(directories) == 2  # distinctly named
    with zipfile.ZipFile(out) as archive:
        contents = {archive.read(f"{d}/export.csv") for d in directories}
    assert contents == {b"run_a:export.csv", b"run_b:export.csv"}


def test_unicode_in_a_sheet_title_survives_or_transliterates_safely(tmp_path):
    """`Résultats` may survive or be safely transliterated -- what matters is
    that the zip OPENS and every member's files are extractable."""
    dir_a = _member_dir(tmp_path, "run_a")
    dir_b = _member_dir(tmp_path, "run_b")
    out = tmp_path / "group.zip"

    build_group_archive({"Résultats": dir_a, "Données": dir_b}, out)

    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == 2 * len(_MEMBER_FILES)
        for name in names:
            assert archive.read(name)  # extractable, non-empty


# --- resilience: a missing file never costs the other members their archive ----


def test_a_member_missing_a_format_file_does_not_abort_the_archive(tmp_path):
    dir_a = _member_dir(tmp_path, "run_a", files=("export.csv", "manifest.json"))
    dir_b = _member_dir(tmp_path, "run_b")
    out = tmp_path / "group.zip"

    build_group_archive({"Week 1": dir_a, "Week 2": dir_b}, out)

    names = set(_entry_names(out))
    assert names == {
        "Week 1/export.csv",
        "Week 1/manifest.json",
        *(f"Week 2/{filename}" for filename in _MEMBER_FILES),
    }


def test_an_empty_group_raises_naming_what_was_not_written(tmp_path):
    with pytest.raises(ValueError, match="archive was not written"):
        build_group_archive({}, tmp_path / "group.zip")
