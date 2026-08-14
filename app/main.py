import datetime
import logging

from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app import models, schemas
from app.image_pipeline import generate_all_variants, generate_placeholder_source_image
from app.captions import compose_caption
from app.scheduler import start_scheduler, schedule_post
from app.recovery import recover_stale_publishing_posts
from app.config import WEBHOOK_SECRET
from common.security import verify_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Multi-Platform Social Campaign Publisher")


@app.on_event("startup")
def on_startup():
    start_scheduler()
    recover_stale_publishing_posts()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/campaigns", response_model=schemas.CampaignOut, status_code=201)
def create_campaign(payload: schemas.CampaignCreateRequest, db: Session = Depends(get_db)):
    source_path = f"generated/{payload.title.replace(' ', '_')}_source.jpg"
    generate_placeholder_source_image(source_path, label=payload.blog_post_title[:24])

    campaign = models.Campaign(
        title=payload.title,
        blog_post_title=payload.blog_post_title,
        blog_post_body=payload.blog_post_body,
        blog_post_url=payload.blog_post_url,
        source_image_path=source_path,
    )
    db.add(campaign)
    db.flush()

    variants = generate_all_variants(
        source_path, payload.platforms, output_dir=f"generated/{campaign.id}"
    )

    scheduled_time = payload.scheduled_time or datetime.datetime.utcnow()

    for platform in payload.platforms:
        caption = compose_caption(
            platform, payload.blog_post_title, payload.blog_post_body, payload.blog_post_url
        )
        post = models.SocialPost(
            campaign_id=campaign.id,
            platform=platform,
            caption=caption,
            image_path=variants[platform],
            scheduled_time=scheduled_time,
            status="queued",
            idempotency_key=f"{campaign.id}-{platform}",
        )
        db.add(post)
        db.flush()
        schedule_post(post.id, scheduled_time)

    db.commit()
    db.refresh(campaign)
    return campaign


@app.get("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter_by(id=campaign_id).first()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@app.get("/campaigns", response_model=list[schemas.CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(models.Campaign).order_by(models.Campaign.created_at.desc()).all()


@app.post("/webhooks/social-delivery")
async def handle_delivery_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.json()
    signature = request.headers.get("X-Signature")

    if not signature or not verify_signature(raw_body, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = schemas.DeliveryWebhookPayload(**raw_body)

    already_seen = (
        db.query(models.WebhookEvent).filter_by(event_id=event.event_id).first()
    )
    if already_seen:
        logger.info("Ignoring duplicate webhook event %s", event.event_id)
        return {"status": "ignored_duplicate"}

    post = db.query(models.SocialPost).filter_by(id=event.post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status not in ("published", "failed"):
        post.status = event.result
        post.status_reason = event.reason
        post.external_post_id = event.external_post_id

    db.add(
        models.WebhookEvent(
            event_id=event.event_id, platform=event.platform, post_id=post.id
        )
    )
    db.commit()

    return {"status": "ok"}
