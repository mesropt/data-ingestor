"""Password hashing seam (D-06-03) -- the ONLY module allowed to import
`pwdlib`, keeping a single hashing seam (mirrors the "one place imports
`sqlite3`" convention in `learning/sqlite_store.py`).

Argon2id via `PasswordHash.recommended()`. This module never logs and never
returns plaintext -- its functions take/return only the values needed, so a
password value can never leak through this seam (T-06-02).
"""

from __future__ import annotations

from pwdlib import PasswordHash

# Argon2id with modern defaults; a bcrypt fallback is retained for verify-only
# so a legacy hash could be migrated without a flag day (pwdlib's raison d'être).
_password_hash = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    """Return an Argon2id hash string for `plain` -- never the plaintext."""
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """True iff `plain` matches `hashed` (constant-time, delegated to Argon2)."""
    return _password_hash.verify(plain, hashed)
