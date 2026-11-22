"""Cryptographic hashing and token verification utilities."""

import hashlib
import hmac
import secrets
from typing import Tuple

SALT_SIZE = 16
DEFAULT_ITERATIONS = 100000

def hash_password(password: str, salt: bytes = None) -> Tuple[str, str]:
    """Hash a plaintext password with PBKDF2-HMAC-SHA256."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = salt or secrets.token_bytes(SALT_SIZE)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, DEFAULT_ITERATIONS)
    return key.hex(), salt.hex()

def verify_password(password: str, key_hex: str, salt_hex: str) -> bool:
    """Verify whether a candidate password matches the hashed key."""
    salt = bytes.fromhex(salt_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, DEFAULT_ITERATIONS)
    return hmac.compare_digest(candidate.hex(), key_hex)

def generate_token(prefix: str = 'cm') -> str:
    """Generate a random cryptographic bearer token."""
    return f"{prefix}_{secrets.token_urlsafe(32)}"
