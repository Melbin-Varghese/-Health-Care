"""
security.py
Password hashing only.
"""

import hashlib
import hmac
import os

_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, digest = stored_hash.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return hmac.compare_digest(check, digest)
