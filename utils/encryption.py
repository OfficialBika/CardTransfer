from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionService:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "SESSION_ENCRYPTION_KEY is invalid. Use a valid Fernet key."
            ) from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(
                "Could not decrypt stored session. Check SESSION_ENCRYPTION_KEY."
            ) from exc
