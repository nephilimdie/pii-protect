import uuid
import pytest
import httpx
import os

BASE_URL = "http://localhost:15500"
UI_URL = "http://localhost:15501"
ADMIN_KEY = os.getenv("E2E_ADMIN_KEY", "pii-admin-local-dev-key")
INTERNAL_KEY = os.getenv("E2E_INTERNAL_API_KEY") or os.getenv("PII_INTERNAL_API_KEY")


def _with_internal(headers: dict[str, str]) -> dict[str, str]:
    if not INTERNAL_KEY:
        return headers
    out = dict(headers)
    out["X-Internal-Api-Key"] = INTERNAL_KEY
    return out


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers() -> dict:
    return _with_internal({"X-Api-Key": ADMIN_KEY})


@pytest.fixture(scope="session")
def service_key(client: httpx.Client, admin_headers: dict) -> str:
    name = f"e2e-service-{uuid.uuid4().hex[:8]}"
    r = client.post("/v1/auth/api-keys", json={"name": name, "role": "service"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    yield r.json()["key"]


@pytest.fixture(scope="session")
def service_headers(service_key: str) -> dict:
    return _with_internal({"X-Api-Key": service_key})


@pytest.fixture
def ctx_id() -> str:
    return f"e2e-{uuid.uuid4()}"
