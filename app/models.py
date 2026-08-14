import datetime
import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    blog_post_title = Column(String, nullable=False)
    blog_post_body = Column(Text, nullable=False)
    blog_post_url = Column(String, nullable=False)
    source_image_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    posts = relationship(
        "SocialPost", back_populates="campaign", cascade="all, delete-orphan"
    )


class SocialPost(Base):
    __tablename__ = "social_posts"

    id = Column(String, primary_key=True, default=_uuid)
    campaign_id = Column(String, ForeignKey("campaigns.id"), nullable=False)

    platform = Column(String, nullable=False)
    caption = Column(Text, nullable=False)
    image_path = Column(String, nullable=False)

    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String, default="queued")
    status_reason = Column(String, nullable=True)

    idempotency_key = Column(String, nullable=False)
    external_post_id = Column(String, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    campaign = relationship("Campaign", back_populates="posts")


class SocialToken(Base):
    __tablename__ = "social_tokens"

    id = Column(String, primary_key=True, default=_uuid)
    platform = Column(String, unique=True, nullable=False)
    encrypted_token = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, unique=True, nullable=False)
    platform = Column(String, nullable=False)
    post_id = Column(String, nullable=False)
    received_at = Column(DateTime, default=datetime.datetime.utcnow)
