import logging
import random
import threading
import time
import uuid

import requests
from fastapi import FastAPI, Header, HTTPException, Request, Response

from common.security import sign_payload
from app.config import WEBHOOK_SECRET

logger = logging.getLogger("fake_platform")

app = FastAPI(title="Fake Social Platform")

idempotency_cache: dict[str, dict] = {}
request_counter = {"count": 0}

RATE_LIMIT_EVERY_N = 4


def reset_state():
    idempotency_cache.clear()
    request_counter["count"] = 0


@app.get("/health")
def health():
    return {"status": "ok"}


def _simulate_async_delivery(post_id: str, platform: str, external_post_id: str,
                              webhook_url: str):
    time.sleep(2)

    delivered = random.random() > 0.1

    payload = {
        "event_id": str(uuid.uuid4()),
        "post_id": post_id,
        "platform": platform,
        "external_post_id": external_post_id,
        "result": "published" if delivered else "failed",
        "reason": None if delivered else "Simulated platform delivery failure",
    }
    signature = sign_payload(payload, WEBHOOK_SECRET)

    try:
        requests.post(
            webhook_url, json=payload, headers={"X-Signature": signature}, timeout=5
        )
    except requests.RequestException as exc:
        logger.error("failed to deliver webhook: %s", exc)


@app.post("/publish")
async def publish(
    request: Request,
    authorization: str = Header(None),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    if idempotency_key in idempotency_cache:
        cached = dict(idempotency_cache[idempotency_key])
        cached["replayed"] = True
        return cached

    request_counter["count"] += 1
    if request_counter["count"] % RATE_LIMIT_EVERY_N == 0:
        return Response(
            status_code=429,
            headers={"Retry-After": "2"},
            content='{"detail": "Rate limited, try again shortly."}',
            media_type="application/json",
        )

    body = await request.json()
    external_post_id = f"ext-{uuid.uuid4().hex[:10]}"

    result = {"external_post_id": external_post_id, "replayed": False}
    idempotency_cache[idempotency_key] = result

    webhook_url = body.get("webhook_url")
    if webhook_url:
        threading.Thread(
            target=_simulate_async_delivery,
            args=(body["post_id"], body["platform"], external_post_id, webhook_url),
            daemon=True,
        ).start()

    return result
