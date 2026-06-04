import uuid
import pytest
import httpx

BASE_URL = "http://localhost:15500"
UI_URL = "http://localhost:15501"
ADMIN_KEY = "pii-admin-local-dev-key"


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers() -> dict:
    return {"X-Api-Key": ADMIN_KEY}


@pytest.fixture(scope="session")
def service_key(client: httpx.Client, admin_headers: dict) -> str:
    name = f"e2e-service-{uuid.uuid4().hex[:8]}"
    r = client.post("/v1/auth/api-keys", json={"name": name, "role": "service"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    yield r.json()["key"]


@pytest.fixture(scope="session")
def service_headers(service_key: str) -> dict:
    return {"X-Api-Key": service_key}


@pytest.fixture
def ctx_id() -> str:
    return f"e2e-{uuid.uuid4()}"
