import time
import requests

from app.config import FAKE_PLATFORM_URL, APP_WEBHOOK_URL, MAX_PUBLISH_RETRIES
from app.publishers.base import SocialPublisher, PublishResult, PublishError
from app.token_store import get_or_create_token


class FakePlatformPublisher(SocialPublisher):
    platform_name = None

    def publish(self, post) -> PublishResult:
        token = get_or_create_token(self.platform_name)
        idempotency_key = post.idempotency_key

        body = {
            "platform": self.platform_name,
            "caption": post.caption,
            "image_path": post.image_path,
            "post_id": post.id,
            "webhook_url": APP_WEBHOOK_URL,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": idempotency_key,
        }

        attempt = 0
        while True:
            attempt += 1
            response = requests.post(
                f"{FAKE_PLATFORM_URL}/publish", json=body, headers=headers, timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                return PublishResult(
                    external_post_id=data["external_post_id"],
                    replayed=data.get("replayed", False),
                )

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                if attempt > MAX_PUBLISH_RETRIES:
                    raise PublishError(
                        f"Rate limited by {self.platform_name} after {attempt} attempts"
                    )
                time.sleep(retry_after)
                continue

            raise PublishError(
                f"{self.platform_name} publish failed: {response.status_code} {response.text}"
            )
