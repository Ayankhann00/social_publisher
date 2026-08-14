import datetime
import time
import uuid

from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.models import Campaign, SocialPost
from app.scheduler import publish_due_post, start_scheduler
from app.recovery import recover_stale_publishing_posts
from app.config import WEBHOOK_SECRET
from common.security import sign_payload
from fake_platform.server import reset_state, idempotency_cache

Base.metadata.create_all(bind=engine)


def _make_campaign_and_post():
    db = SessionLocal()
    try:
        campaign = Campaign(
            title="crash-recovery-test",
            blog_post_title="Crash Recovery Test Post",
            blog_post_body="Testing that a stuck publishing job recovers after a crash.",
            blog_post_url="https://example.com/crash-test",
            source_image_path="generated/crash-test/source.jpg",
        )
        db.add(campaign)
        db.flush()

        post = SocialPost(
            campaign_id=campaign.id,
            platform="instagram",
            caption="crash recovery caption",
            image_path="generated/crash-test/instagram.jpg",
            scheduled_time=datetime.datetime.utcnow(),
            status="queued",
            idempotency_key=f"{campaign.id}-instagram",
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


def test_worker_crash_mid_publish_recovers_without_duplicate():
    reset_state()
    start_scheduler()

    post_id = _make_campaign_and_post()

    publish_due_post(post_id)

    post_after_first_attempt = _get_post(post_id)
    assert post_after_first_attempt.status == "publishing"
    assert post_after_first_attempt.external_post_id is not None
    original_external_id = post_after_first_attempt.external_post_id
    idempotency_key = post_after_first_attempt.idempotency_key

    db = SessionLocal()
    try:
        stuck_post = db.query(SocialPost).filter_by(id=post_id).first()
        stuck_post.processing_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
        db.commit()
    finally:
        db.close()

    recovered_ids = recover_stale_publishing_posts(stale_after_seconds=60)
    assert post_id in recovered_ids

    final_post = None
    for _ in range(50):
        final_post = _get_post(post_id)
        if final_post.status == "publishing" and final_post.external_post_id is not None:
            break
        time.sleep(0.1)

    assert final_post.status == "publishing"
    assert final_post.external_post_id == original_external_id

    assert idempotency_key in idempotency_cache
    assert idempotency_cache[idempotency_key]["external_post_id"] == original_external_id

    payload = {
        "event_id": str(uuid.uuid4()),
        "post_id": post_id,
        "platform": "instagram",
        "external_post_id": original_external_id,
        "result": "published",
        "reason": None,
    }
    signature = sign_payload(payload, WEBHOOK_SECRET)

    from app.main import app as main_app
    client = TestClient(main_app)
    response = client.post(
        "/webhooks/social-delivery", json=payload, headers={"X-Signature": signature}
    )
    assert response.status_code == 200

    published_post = _get_post(post_id)
    assert published_post.status == "published"
    assert published_post.external_post_id == original_external_id
