"""Хэширование паролей."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from attention_system.markup import stereotype


@stereotype("служба")
class PasswordHash:
    """Хранит пароль в виде «соль$хэш» (PBKDF2-HMAC-SHA256)."""

    ITERATIONS = 100_000

    @staticmethod
    def make(password: str, salt: Optional[bytes] = None) -> str:
        salt = salt or os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PasswordHash.ITERATIONS)
        return salt.hex() + "$" + digest.hex()

    @staticmethod
    def verify(password: str, stored: str) -> bool:
        try:
            salt, digest = stored.split("$")
            expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                            bytes.fromhex(salt), PasswordHash.ITERATIONS)
            return hmac.compare_digest(expected.hex(), digest)
        except ValueError:
            return False
