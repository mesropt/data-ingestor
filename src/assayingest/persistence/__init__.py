"""The PostgreSQL persistence layer (quick 260712-ghn).

Infrastructure only. The domain never imports from here: dependencies point
INWARD, so `domain/`, `fields/`, and the four store INTERFACES
(`learning/store.py`, `learning/field_set_store.py`, `learning/schema_store.py`,
`auth/store.py`) still contain zero SQL. That is what made swapping SQLite for
Postgres an infrastructure change rather than a domain rewrite.
"""
