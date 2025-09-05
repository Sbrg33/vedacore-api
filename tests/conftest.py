import os
import pytest


# Ensure tests run without heavy startup/JIT overhead
os.environ.setdefault("VC_SKIP_WARMUP", "1")
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
# Provide a default JWT secret for tests that generate tokens
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from apps.api.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def openapi_spec(client):
    r = client.get("/openapi.json")
    r.raise_for_status()
    return r.json()

