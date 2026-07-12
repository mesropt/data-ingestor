"""Resolve the shipped starter presets directory (FIELD-05, quick 260712-e0e).

The presets ship as plain YAML in two possible locations depending on how
the app is running: a repo checkout (`presets/` at repo root, the same
files `tests/test_presets.py` loads by literal path) or an installed wheel
(`assayingest/presets/`, via `pyproject.toml`'s
`[tool.hatch.build.targets.wheel.force-include]`). Resolution never assumes
the process CWD is the repo root -- uvicorn may be started from anywhere.

Loading itself goes through the ONE existing `fields.loader.load` entry
point (D-03, T-e0e-01) -- this module resolves paths, it does not parse
YAML.
"""

from __future__ import annotations

from pathlib import Path

from . import loader
from .models import FieldSet


def _packaged_presets_dir() -> Path:
    """`assayingest/presets/` -- exists inside an installed wheel via the
    `force-include` mapping in `pyproject.toml`."""
    return Path(__file__).resolve().parent.parent / "presets"


def _repo_root_presets_dir() -> Path:
    """`presets/` at the repo root -- exists in a source checkout.
    `fields/presets.py` sits at `src/assayingest/fields/`, so the repo root
    is three parents up from this file."""
    return Path(__file__).resolve().parents[3] / "presets"


def presets_dir() -> Path | None:
    """The first existing presets directory, packaged location checked
    first, or `None` if neither exists."""
    for candidate in (_packaged_presets_dir(), _repo_root_presets_dir()):
        if candidate.is_dir():
            return candidate
    return None


def preset_paths() -> list[Path]:
    """Every shipped preset YAML file, sorted for deterministic order.
    Empty if no presets directory exists (a stripped-down install, or a
    checkout with the `presets/` directory removed)."""
    directory = presets_dir()
    if directory is None:
        return []
    return sorted(directory.glob("*.yaml"))


def _load_one(path: Path) -> tuple[str, FieldSet]:
    field_set = loader.load(path)
    return field_set.name or path.stem, field_set


def load_presets() -> list[tuple[str, FieldSet]]:
    """Load every shipped preset through `fields.loader.load` -- the exact
    same YAML entry point a user's `--fields` file uses. Returns `(name,
    field_set)` pairs where `name` is `field_set.name`, falling back to the
    file stem for a preset that (against convention) declares no top-level
    `name:`."""
    return [_load_one(path) for path in preset_paths()]
