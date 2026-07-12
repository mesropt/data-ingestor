"""Password hashing seam (D-06-03) -- Argon2 via pwdlib, one narrow import
site. Never stores or returns plaintext.
"""

from __future__ import annotations

from assayingest.auth.passwords import hash_password, verify_password


def test_hash_is_not_plaintext():
    hashed = hash_password("longenough")
    assert hashed != "longenough"
    assert "longenough" not in hashed


def test_verify_accepts_correct_password():
    hashed = hash_password("longenough")
    assert verify_password("longenough", hashed) is True


def test_verify_rejects_wrong_password():
    hashed = hash_password("longenough")
    assert verify_password("wrong", hashed) is False
