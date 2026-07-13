"""Resolve the shipped starter presets directory (FIELD-05, quick 260712-e0e).

The presets ship as plain YAML in two possible locations depending on how
the app is running: a repo checkout (`presets/` at repo root, the same
files `tests/test_presets.py` loads by literal path) or an installed wheel
(`assayingest/presets/`, via `pyproject.toml`'s
`[tool.hatch.build.targets.wheel.force-include]`). Resolution never assumes
the process CWD is the repo root -- uvicorn may be started from anywhere.

Loading itself goes through the ONE existing `fields.loader` entry point
(D-03, T-e0e-01) -- this module resolves paths and never opens a YAML parser
of its own. `load_preset_aliases` below reads the `aliases:` block through
`loader._parse` for exactly that reason: `yaml.safe_load` stays the single
YAML door in the codebase (the full loader is a remote-code path in a tool
built to ingest files from strangers), and a second `yaml.*` call here would
be the first crack in that.
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


def load_preset_aliases() -> dict[str, dict[str, tuple[str, ...]]]:
    """The starter header spellings each shipped preset declares (D-11-18),
    as `{preset_name: {field_name: (spelling, ...)}}`.

    Reads the per-field `aliases:` key that `fields/loader.py::_build_field`
    deliberately IGNORES -- the loader reads only the keys it knows, so an
    `aliases:` block is inert to `FieldSet` loading and no `Field` ever gains
    an alias attribute. Presets stay editable data the loader does not
    interpret; the crosswalk seeder (`learning/seed.py`) is the only reader.

    A field declaring no `aliases:` is simply absent from its preset's
    mapping. A malformed `aliases:` block raises `ValueError` naming the
    consequence: the crosswalk would silently ship without those spellings,
    and the Schema scorer would score that field 0 on every sheet.
    """
    return {
        _preset_name(path, raw): _field_aliases(path, raw)
        for path, raw in ((path, _read_preset(path)) for path in preset_paths())
    }


def _read_preset(path: Path) -> dict:
    """The preset's raw document, through `loader`'s own `yaml.safe_load`
    seam -- never a second YAML entry point (D-03)."""
    raw = loader._parse(path, path.suffix.lower())
    if not isinstance(raw, dict):
        raise ValueError(
            f"Cannot read starter aliases from {path.name}: the file's top "
            f"level must be a mapping, but it holds {type(raw).__name__}."
        )
    return raw


def _preset_name(path: Path, raw: dict) -> str:
    """The same name `load_presets` reports, so both mappings key alike --
    the seeder looks a Schema up by exactly this name."""
    name = raw.get("name")
    return name if isinstance(name, str) and name else path.stem


def _field_aliases(path: Path, raw: dict) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, tuple[str, ...]] = {}
    for spec in raw.get("fields") or []:
        if not isinstance(spec, dict) or "aliases" not in spec:
            continue
        field_name = spec.get("name")
        declared = spec.get("aliases")
        if not isinstance(field_name, str) or not isinstance(declared, list):
            raise ValueError(
                f"Cannot read starter aliases from {path.name}: field "
                f"{field_name!r} declares 'aliases' as "
                f"{type(declared).__name__}, not a list of column names."
            )
        spellings = tuple(
            spelling.strip()
            for spelling in declared
            if isinstance(spelling, str) and spelling.strip()
        )
        if len(spellings) != len(declared):
            raise ValueError(
                f"Cannot read starter aliases from {path.name}: field "
                f"{field_name!r} declares an alias that is not a column name "
                f"-- quote it, or remove it."
            )
        if spellings:
            aliases[field_name] = spellings
    return aliases
