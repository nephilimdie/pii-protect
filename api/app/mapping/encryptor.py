from cryptography.fernet import Fernet, InvalidToken


class FieldEncryptor:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except (InvalidToken, Exception):
            raise ValueError("decryption_failed")
