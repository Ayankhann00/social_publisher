import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from app.config import JOBSTORE_URL
from app.database import SessionLocal
from app.models import SocialPost
from app.publishers.fake_instagram import FakeInstagramPublisher
from app.publishers.fake_x import FakeXPublisher
from app.publishers.base import PublishError

logger = logging.getLogger("scheduler")

PUBLISHERS = {
    "instagram": FakeInstagramPublisher(),
    "x": FakeXPublisher(),
}

jobstores = {"default": SQLAlchemyJobStore(url=JOBSTORE_URL)}
scheduler = BackgroundScheduler(jobstores=jobstores, timezone=datetime.timezone.utc)


def publish_due_post(post_id: str):
    db = SessionLocal()
    try:
        post = db.query(SocialPost).filter_by(id=post_id).first()
        if post is None:
            logger.warning("Scheduled post %s no longer exists", post_id)
            return

        if post.status != "queued":
            logger.info("Post %s is already %s, skipping", post_id, post.status)
            return

        post.status = "publishing"
        post.processing_started_at = datetime.datetime.utcnow()
        db.commit()

        publisher = PUBLISHERS.get(post.platform)
        if publisher is None:
            post.status = "failed"
            post.status_reason = f"No publisher registered for '{post.platform}'"
            db.commit()
            return

        try:
            result = publisher.publish(post)
            post.external_post_id = result.external_post_id
            db.commit()
        except PublishError as exc:
            post.status = "failed"
            post.status_reason = str(exc)
            db.commit()
            logger.error("Failed to publish post %s: %s", post_id, exc)

    finally:
        db.close()


def schedule_post(post_id: str, run_at):
    scheduler.add_job(
        publish_due_post,
        "date",
        run_date=run_at,
        args=[post_id],
        id=f"publish-{post_id}",
        misfire_grace_time=3600,
        replace_existing=True,
    )


def start_scheduler():
    if not scheduler.running:
        scheduler.start()