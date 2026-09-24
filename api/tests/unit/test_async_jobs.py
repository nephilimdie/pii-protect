from __future__ import annotations

from app.config import settings
from app.jobs.codec import JobPayloadCodec
from app.routers.jobs import _allowed_webhook


def test_webhook_requires_https_and_exactly_allowed_hostname(monkeypatch):
    monkeypatch.setattr(settings, "async_job_webhook_hosts", "hooks.example.com,events.example.net")

    assert _allowed_webhook(None)
    assert _allowed_webhook("https://hooks.example.com/callback")
    assert _allowed_webhook("https://events.example.net/v1/jobs")
    assert not _allowed_webhook("http://hooks.example.com/callback")
    assert not _allowed_webhook("https://hooks.example.com.attacker.test/callback")
    assert not _allowed_webhook("https://unknown.example.com/callback")


def test_job_payload_codec_round_trips_payload():
    payload = {"text": "Mario Rossi", "api_key": "secret-key", "mode": "tag"}
    encoded = JobPayloadCodec().encode(payload)

    assert JobPayloadCodec().decode(encoded) == payload
    assert encoded != str(payload)
