import types
import uuid

import app.publishers.fake_platform_publisher as fake_platform_publisher_module
from app.publishers.fake_instagram import FakeInstagramPublisher
from fake_platform.server import reset_state, request_counter, idempotency_cache


def make_post(platform="instagram"):
    return types.SimpleNamespace(
        id=str(uuid.uuid4()),
        platform=platform,
        caption="test caption",
        image_path="generated/test/instagram.jpg",
        idempotency_key=f"reliability-test-{uuid.uuid4()}",
    )


def test_publisher_retries_after_429_and_succeeds(monkeypatch):
    reset_state()
    request_counter["count"] = 3

    sleep_calls = []
    monkeypatch.setattr(
        fake_platform_publisher_module.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    post = make_post()
    publisher = FakeInstagramPublisher()
    result = publisher.publish(post)

    assert result.external_post_id.startswith("ext-")
    retry_backoff_sleeps = [s for s in sleep_calls if isinstance(s, float)]
    assert retry_backoff_sleeps == [2.0]
    assert len(idempotency_cache) == 1


def test_repeated_publish_call_does_not_duplicate_on_platform():
    reset_state()

    post = make_post()
    publisher = FakeInstagramPublisher()

    first = publisher.publish(post)
    second = publisher.publish(post)

    assert first.external_post_id == second.external_post_id
    assert second.replayed is True
    assert len(idempotency_cache) == 1
