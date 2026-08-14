import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CampaignCreateRequest(BaseModel):
    title: str
    blog_post_title: str
    blog_post_body: str
    blog_post_url: str
    platforms: List[str] = Field(default_factory=lambda: ["instagram", "x"])
    scheduled_time: Optional[datetime.datetime] = None


class SocialPostOut(BaseModel):
    id: str
    platform: str
    caption: str
    image_path: str
    status: str
    status_reason: Optional[str] = None
    scheduled_time: datetime.datetime
    external_post_id: Optional[str] = None

    class Config:
        from_attributes = True


class CampaignOut(BaseModel):
    id: str
    title: str
    blog_post_title: str
    created_at: datetime.datetime
    posts: List[SocialPostOut]

    class Config:
        from_attributes = True


class DeliveryWebhookPayload(BaseModel):
    event_id: str
    post_id: str
    platform: str
    external_post_id: str
    result: str
    reason: Optional[str] = None
