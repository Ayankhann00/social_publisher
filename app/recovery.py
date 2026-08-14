import datetime
import logging

from app.database import SessionLocal
from app.models import SocialPost
from app.scheduler import schedule_post

logger = logging.getLogger("recovery")

STALE_AFTER_SECONDS = 120


def recover_stale_publishing_posts(stale_after_seconds: int = STALE_AFTER_SECONDS):
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=stale_after_seconds)
        stale_posts = (
            db.query(SocialPost)
            .filter(
                SocialPost.status == "publishing",
                SocialPost.processing_started_at.isnot(None),
                SocialPost.processing_started_at < cutoff,
            )
            .all()
        )

        recovered_ids = []
        for post in stale_posts:
            post.status = "queued"
            post.processing_started_at = None
            recovered_ids.append(post.id)

        db.commit()
    finally:
        db.close()

    for post_id in recovered_ids:
        logger.warning("Recovering stale post %s, rescheduling now", post_id)
        schedule_post(post_id, datetime.datetime.utcnow())

    return recovered_ids
