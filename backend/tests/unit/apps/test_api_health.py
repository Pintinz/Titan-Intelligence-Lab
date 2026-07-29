from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_endpoint_does_not_require_a_database():
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ok"
    assert body["error"] is None
