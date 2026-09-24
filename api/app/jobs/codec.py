from __future__ import annotations

import json

from app.config import settings
from app.mapping.encryptor import FieldEncryptor


class JobPayloadCodec:
    def __init__(self) -> None:
        self._encryptor = FieldEncryptor(settings.encryption_key)

    def encode(self, payload: dict) -> str:
        return self._encryptor.encrypt(json.dumps(payload, separators=(",", ":")))

    def decode(self, value: str) -> dict:
        payload = json.loads(self._encryptor.decrypt(value))
        if not isinstance(payload, dict):
            raise ValueError("invalid_job_payload")
        return payload
