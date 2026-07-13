"""Authentication substrate (Phase 06): the pure-Python `User` domain model,
the `UserStore` repository seam and its PostgreSQL implementation, and the
password / session-cookie / verification-token seams.

No HTTP route lives here -- the API layer (`api/deps.py`, `api/routes/auth.py`)
consumes these. Mirrors the `learning/` package's store split (ABC + one
`Postgres*` implementation behind a `deps.py` factory), per D-06-02.
"""
