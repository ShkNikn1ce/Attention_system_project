"""Хэширование паролей."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from attention_system.markup import стереотип


@стереотип("служба")
class ХэшПароля:
    """Хранит пароль в виде «соль$хэш» (PBKDF2-HMAC-SHA256)."""

    ИТЕРАЦИИ = 100_000

    @staticmethod
    def создать(пароль: str, соль: Optional[bytes] = None) -> str:
        соль = соль or os.urandom(16)
        хэш = hashlib.pbkdf2_hmac("sha256", пароль.encode("utf-8"), соль, ХэшПароля.ИТЕРАЦИИ)
        return соль.hex() + "$" + хэш.hex()

    @staticmethod
    def проверить(пароль: str, значение: str) -> bool:
        try:
            соль, хэш = значение.split("$")
            ожидаемый = hashlib.pbkdf2_hmac("sha256", пароль.encode("utf-8"),
                                            bytes.fromhex(соль), ХэшПароля.ИТЕРАЦИИ)
            return hmac.compare_digest(ожидаемый.hex(), хэш)
        except ValueError:
            return False
