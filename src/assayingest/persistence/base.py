"""The single declarative `Base` -- and therefore the single `MetaData`.

One MetaData means Alembic's `--autogenerate` has exactly one target and can
never miss a table. Every ORM entity in `models.py` inherits from this class.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """The declarative base for all six persisted tables."""
