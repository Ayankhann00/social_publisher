from fastapi.testclient import TestClient
from fake_platform.server import app

client = TestClient(app)

HEADERS = {"Authorization": "Bearer fake-token", "Idempotency-Key": "post-123-instagram"}
BODY = {
    "platform": "instagram",
    "caption": "hello world",
    "image_path": "generated/x/instagram.jpg",
    "post_id": "post-123",
}


def test_duplicate_publish_returns_same_external_id():
    first = client.post("/publish", json=BODY, headers=HEADERS)
    assert first.status_code == 200
    first_id = first.json()["external_post_id"]

    second = client.post("/publish", json=BODY, headers=HEADERS)
    assert second.status_code == 200
    second_id = second.json()["external_post_id"]

    assert first_id == second_id
    assert second.json()["replayed"] is True


def test_missing_idempotency_key_is_rejected():
    response = client.post(
        "/publish", json=BODY, headers={"Authorization": "Bearer fake-token"}
    )
    assert response.status_code == 400


def test_rate_limit_eventually_triggers():
    saw_429 = False
    for i in range(10):
        headers = {
            "Authorization": "Bearer fake-token",
            "Idempotency-Key": f"rate-limit-test-{i}",
        }
        response = client.post("/publish", json=BODY, headers=headers)
        if response.status_code == 429:
            saw_429 = True
            assert "Retry-After" in response.headers
            break
    assert saw_429
