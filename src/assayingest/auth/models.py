"""The `User` domain model -- pure Python, no dependency on pandas, the
Anthropic SDK, or any wire/API format (mirrors `domain/models.py`'s frozen
dataclass convention). Infrastructure layers map their own rows/wire shapes
onto this at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """A signed-up or OAuth-provisioned user.

    `password_hash` is None for a Google-OAuth-only account (D-06-05): an OAuth
    user never sets a local password. `auth_provider` is "password" | "google".
    `is_verified` gates governed actions (D-06-04): a signed-in-but-unverified
    user is authenticated yet still blocked from confirming a mapping.
    """

    id: str
    email: str
    password_hash: str | None
    is_verified: bool
    auth_provider: str
    created_at: str
