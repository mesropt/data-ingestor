"""The one place this project reads a `.env` file off disk.

Both real entrypoints -- the FastAPI app (`api/app.py`, imported directly by
`uvicorn assayingest.api.app:app`, which has no `main()`) and the CLI
(`cli.py::main`) -- call `load_project_env()` at their own composition root so
the README's documented commands work with no extra flags (no `--env-file`,
no manual `export`).

The non-negotiable rule: a real environment variable ALWAYS wins over a
`.env` value. `.env` exists for local convenience only; it must never be able
to shadow a credential a CI pipeline, a real deployment, or an operator's own
shell `export` already injected into the process. `load_dotenv(...,
override=False)` enforces exactly that -- see the sentinel check in this
plan's Task 2 verification.

This module never prints, logs, or returns any variable's VALUE -- only
whether a file was found and loaded, as a boolean. It touches only the
process environment and the filesystem (an infrastructure/composition-root
concern), never the domain.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv


def load_project_env() -> bool:
    """Load `.env` from the project root into `os.environ`, without ever
    overriding a variable already present there.

    Returns whether a `.env` file was actually found and loaded.

    `find_dotenv(usecwd=True)` walks UP from the process's current working
    directory -- both documented commands (`uvicorn ...`, `assayingest ...`)
    are run from the repo root, so this finds the root `.env` regardless of
    where the `assayingest` package itself happens to be installed.

    PITFALL: `find_dotenv` returns `""` (not `None`) when nothing is found,
    and `load_dotenv("")` does NOT no-op -- an empty string is falsy, so
    python-dotenv silently falls back to its own frame-based search instead
    of just doing nothing. Guard on the empty result explicitly so a missing
    `.env` is a clean, predictable no-op.
    """
    dotenv_path = find_dotenv(usecwd=True)
    if not dotenv_path:
        return False
    return load_dotenv(dotenv_path, override=False)
