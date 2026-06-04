"""
E2E API tests — run against the live Docker service at localhost:15500.

Usage:
    pytest tests/e2e/test_api.py -v
"""

import uuid
import httpx
import pytest


# ─── health ──────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self, client: httpx.Client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "models_loaded" in body

    def test_no_auth_required(self, client: httpx.Client):
        r = client.get("/health")
        assert r.status_code == 200


# ─── auth ────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_missing_key_returns_401(self, client: httpx.Client):
        r = client.post("/v1/anonymize", json={"text": "test", "context_id": "x", "context_type": "y"})
        assert r.status_code == 401

    def test_wrong_key_returns_401(self, client: httpx.Client):
        r = client.post(
            "/v1/anonymize",
            json={"text": "test", "context_id": "x", "context_type": "y"},
            headers={"X-Api-Key": "invalid-key-xyz"},
        )
        assert r.status_code == 401

    def test_admin_key_accepted(self, client: httpx.Client, admin_headers: dict):
        r = client.post(
            "/v1/anonymize",
            json={"text": "test", "context_id": "auth-test", "context_type": "test"},
            headers=admin_headers,
        )
        assert r.status_code == 200

    def test_service_key_accepted(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={"text": "test", "context_id": ctx_id, "context_type": "test"},
            headers=service_headers,
        )
        assert r.status_code == 200


# ─── anonymize ───────────────────────────────────────────────────────────────

class TestAnonymize:
    def test_fiscal_code_detected(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={"text": "Il codice fiscale è RSSMRA80A01H501U", "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "FISCAL_CODE" in body["pii_types_found"]
        assert "RSSMRA80A01H501U" not in body["anonymized_text"]
        assert "[FISCAL_CODE_" in body["anonymized_text"]

    def test_iban_detected(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={"text": "Bonifico su IT60X0542811101000001234567", "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "IBAN" in body["pii_types_found"]
        assert "IT60X0542811101000001234567" not in body["anonymized_text"]

    def test_email_detected(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={"text": "Scrivimi a mario.rossi@example.com", "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "EMAIL" in body["pii_types_found"]
        assert "mario.rossi@example.com" not in body["anonymized_text"]

    def test_phone_detected(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={"text": "Chiamami al +39 333 1234567", "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "PHONE" in body["pii_types_found"]

    def test_targa_detected(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={"text": "Il veicolo è targato AB123CD", "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "TARGA" in body["pii_types_found"]
        assert "AB123CD" not in body["anonymized_text"]

    def test_no_pii_returns_unchanged_text(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        text = "Il cielo è azzurro oggi."
        r = client.post(
            "/v1/anonymize",
            json={"text": text, "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["anonymized_text"] == text
        assert body["entity_count"] == 0

    def test_multiple_pii_types_in_same_text(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        r = client.post(
            "/v1/anonymize",
            json={
                "text": "CF RSSMRA80A01H501U, email mario@test.com, targa AB123CD",
                "context_id": ctx_id,
                "context_type": "case_file",
            },
            headers=service_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["entity_count"] >= 3
        assert "RSSMRA80A01H501U" not in body["anonymized_text"]
        assert "mario@test.com" not in body["anonymized_text"]
        assert "AB123CD" not in body["anonymized_text"]
        assert isinstance(body["entities"], list)
        assert len(body["entities"]) == body["entity_count"]
        entity_types = {e["type"] for e in body["entities"]}
        assert "FISCAL_CODE" in entity_types
        assert "EMAIL" in entity_types
        for e in body["entities"]:
            assert "start" in e and "end" in e and "confidence" in e and "replacement" in e

    def test_same_entity_same_token_across_calls(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        payload = {"text": "CF RSSMRA80A01H501U", "context_id": ctx_id, "context_type": "case_file"}
        r1 = client.post("/v1/anonymize", json=payload, headers=service_headers)
        r2 = client.post("/v1/anonymize", json=payload, headers=service_headers)
        assert r1.json()["anonymized_text"] == r2.json()["anonymized_text"]

    def test_missing_fields_returns_422(self, client: httpx.Client, service_headers: dict):
        r = client.post("/v1/anonymize", json={"text": "ciao"}, headers=service_headers)
        assert r.status_code == 422


# ─── deanonymize ─────────────────────────────────────────────────────────────

class TestDeanonymize:
    def test_roundtrip_fiscal_code(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        original = "Il codice fiscale è RSSMRA80A01H501U"
        anon = client.post(
            "/v1/anonymize",
            json={"text": original, "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        ).json()["anonymized_text"]

        r = client.post(
            "/v1/deanonymize",
            json={"text": anon, "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        assert r.json()["restored_text"] == original

    def test_roundtrip_multiple_pii(self, client: httpx.Client, service_headers: dict, ctx_id: str):
        original = "CF RSSMRA80A01H501U email mario@test.com targa AB123CD"
        anon = client.post(
            "/v1/anonymize",
            json={"text": original, "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        ).json()["anonymized_text"]

        r = client.post(
            "/v1/deanonymize",
            json={"text": anon, "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        assert r.json()["restored_text"] == original

    def test_unknown_context_returns_text_unchanged(self, client: httpx.Client, service_headers: dict):
        text = "Il CF è [FISCAL_CODE_1]"
        r = client.post(
            "/v1/deanonymize",
            json={"text": text, "context_id": f"nonexistent-{uuid.uuid4()}", "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        assert r.json()["restored_text"] == text

    def test_context_isolation(self, client: httpx.Client, service_headers: dict):
        ctx_a = f"e2e-ctx-a-{uuid.uuid4()}"
        ctx_b = f"e2e-ctx-b-{uuid.uuid4()}"

        anon = client.post(
            "/v1/anonymize",
            json={"text": "CF RSSMRA80A01H501U", "context_id": ctx_a, "context_type": "case_file"},
            headers=service_headers,
        ).json()["anonymized_text"]

        # Restore with wrong context — should not restore
        r = client.post(
            "/v1/deanonymize",
            json={"text": anon, "context_id": ctx_b, "context_type": "case_file"},
            headers=service_headers,
        )
        assert r.status_code == 200
        assert "RSSMRA80A01H501U" not in r.json()["restored_text"]


# ─── api key management ───────────────────────────────────────────────────────

class TestApiKeys:
    def test_list_keys(self, client: httpx.Client, admin_headers: dict):
        r = client.get("/v1/auth/api-keys", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert any(k["role"] == "admin" for k in r.json())

    def test_create_service_key(self, client: httpx.Client, admin_headers: dict):
        name = f"e2e-create-{uuid.uuid4().hex[:8]}"
        r = client.post("/v1/auth/api-keys", json={"name": name, "role": "service"}, headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "service"
        assert "key" in body
        assert body["key"] != ""

    def test_create_auditor_key(self, client: httpx.Client, admin_headers: dict):
        name = f"e2e-auditor-{uuid.uuid4().hex[:8]}"
        r = client.post("/v1/auth/api-keys", json={"name": name, "role": "auditor"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["role"] == "auditor"

    def test_invalid_role_returns_422(self, client: httpx.Client, admin_headers: dict):
        r = client.post(
            "/v1/auth/api-keys",
            json={"name": "bad", "role": "superuser"},
            headers=admin_headers,
        )
        assert r.status_code == 422

    def test_revoke_key(self, client: httpx.Client, admin_headers: dict):
        name = f"e2e-revoke-{uuid.uuid4().hex[:8]}"
        created = client.post(
            "/v1/auth/api-keys", json={"name": name, "role": "service"}, headers=admin_headers
        ).json()
        key_id = created["id"]
        plain_key = created["key"]

        # Key works before revoke
        r = client.post(
            "/v1/anonymize",
            json={"text": "test", "context_id": "x", "context_type": "y"},
            headers={"X-Api-Key": plain_key},
        )
        assert r.status_code == 200

        # Revoke
        r = client.delete(f"/v1/auth/api-keys/{key_id}", headers=admin_headers)
        assert r.status_code == 204

        # Key no longer works
        r = client.post(
            "/v1/anonymize",
            json={"text": "test", "context_id": "x", "context_type": "y"},
            headers={"X-Api-Key": plain_key},
        )
        assert r.status_code == 401

    def test_service_key_cannot_manage_keys(self, client: httpx.Client, service_headers: dict):
        r = client.get("/v1/auth/api-keys", headers=service_headers)
        assert r.status_code == 403


# ─── reporting ───────────────────────────────────────────────────────────────

class TestReporting:
    def test_stats_requires_auth(self, client: httpx.Client):
        r = client.get("/v1/admin/stats")
        assert r.status_code == 401

    def test_stats_returns_summary(self, client: httpx.Client, admin_headers: dict, service_headers: dict, ctx_id: str):
        # Produce some data first
        client.post(
            "/v1/anonymize",
            json={"text": "CF RSSMRA80A01H501U", "context_id": ctx_id, "context_type": "case_file"},
            headers=service_headers,
        )
        r = client.get("/v1/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "total_anonymizations" in body
        assert "total_tokens_created" in body

    def test_audit_log_paginated(self, client: httpx.Client, admin_headers: dict):
        r = client.get("/v1/admin/audit-log?page=1&per_page=5", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert body["page"] == 1
        assert len(body["items"]) <= 5

    def test_audit_log_filter_by_action(self, client: httpx.Client, admin_headers: dict):
        r = client.get("/v1/admin/audit-log?action=anonymize", headers=admin_headers)
        assert r.status_code == 200
        for entry in r.json()["items"]:
            assert entry["action"] == "anonymize"

    def test_cleanup_runs(self, client: httpx.Client, admin_headers: dict):
        r = client.post("/v1/admin/cleanup", json={"ttl_days": 9999}, headers=admin_headers)
        assert r.status_code == 200
        assert "deleted_count" in r.json()

    def test_service_key_cannot_access_stats(self, client: httpx.Client, service_headers: dict):
        r = client.get("/v1/admin/stats", headers=service_headers)
        assert r.status_code == 403
