import datetime
import uuid

from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.models import Campaign, SocialPost
from app.config import WEBHOOK_SECRET
from common.security import sign_payload
from app.main import app as main_app

Base.metadata.create_all(bind=engine)

client = TestClient(main_app)


def _make_post(status="publishing"):
    db = SessionLocal()
    try:
        campaign = Campaign(
            title="webhook-endpoint-test",
            blog_post_title="Webhook Endpoint Test",
            blog_post_body="Testing the webhook endpoint directly.",
            blog_post_url="https://example.com/webhook-test",
            source_image_path="generated/webhook-test/source.jpg",
        )
        db.add(campaign)
        db.flush()

        post = SocialPost(
            campaign_id=campaign.id,
            platform="x",
            caption="webhook test caption",
            image_path="generated/webhook-test/x.jpg",
            scheduled_time=datetime.datetime.utcnow(),
            status=status,
            idempotency_key=f"{campaign.id}-x",
            external_post_id="ext-placeholder",
        )
        db.add(post)
        db.commit()
        return post.id
    finally:
        db.close()


def _get_post(post_id):
    db = SessionLocal()
    try:
        return db.query(SocialPost).filter_by(id=post_id).first()
    finally:
        db.expunge_all()
        db.close()


def test_valid_webhook_updates_status():
    post_id = _make_post()

    payload = {
        "event_id": str(uuid.uuid4()),
        "post_id": post_id,
        "platform": "x",
        "external_post_id": "ext-real-one",
        "result": "published",
        "reason": None,
    }
    signature = sign_payload(payload, WEBHOOK_SECRET)

    response = client.post(
        "/webhooks/social-delivery", json=payload, headers={"X-Signature": signature}
    )

    assert response.status_code == 200
    updated = _get_post(post_id)
    assert updated.status == "published"
    assert updated.external_post_id == "ext-real-one"


def test_forged_webhook_is_rejected():
    post_id = _make_post()

    payload = {
        "event_id": str(uuid.uuid4()),
        "post_id": post_id,
        "platform": "x",
        "external_post_id": "ext-forged",
        "result": "published",
        "reason": None,
    }

    response = client.post(
        "/webhooks/social-delivery",
        json=payload,
        headers={"X-Signature": "0" * 64},
    )

    assert response.status_code == 400
    unchanged = _get_post(post_id)
    assert unchanged.status == "publishing"
    assert unchanged.external_post_id == "ext-placeholder"


def test_duplicate_webhook_event_is_ignored():
    post_id = _make_post()

    payload = {
        "event_id": str(uuid.uuid4()),
        "post_id": post_id,
        "platform": "x",
        "external_post_id": "ext-first-delivery",
        "result": "published",
        "reason": None,
    }
    signature = sign_payload(payload, WEBHOOK_SECRET)

    first = client.post(
        "/webhooks/social-delivery", json=payload, headers={"X-Signature": signature}
    )
    assert first.status_code == 200

    second = client.post(
        "/webhooks/social-delivery", json=payload, headers={"X-Signature": signature}
    )
    assert second.status_code == 200
    assert second.json()["status"] == "ignored_duplicate"


def test_webhook_does_not_flip_terminal_state_backward():
    post_id = _make_post(status="published")

    db = SessionLocal()
    try:
        p = db.query(SocialPost).filter_by(id=post_id).first()
        p.external_post_id = "ext-already-published"
        db.commit()
    finally:
        db.close()

    payload = {
        "event_id": str(uuid.uuid4()),
        "post_id": post_id,
        "platform": "x",
        "external_post_id": "ext-late-failure",
        "result": "failed",
        "reason": "late duplicate event",
    }
    signature = sign_payload(payload, WEBHOOK_SECRET)

    response = client.post(
        "/webhooks/social-delivery", json=payload, headers={"X-Signature": signature}
    )
    assert response.status_code == 200

    unchanged = _get_post(post_id)
    assert unchanged.status == "published"
    assert unchanged.external_post_id == "ext-already-published"
