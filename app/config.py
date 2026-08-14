import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/app.db")
JOBSTORE_URL = os.environ.get("JOBSTORE_URL", "sqlite:///./data/jobs.sqlite")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dev-only-secret-change-me")

FAKE_PLATFORM_URL = os.environ.get("FAKE_PLATFORM_URL", "http://localhost:9000")
APP_WEBHOOK_URL = os.environ.get(
    "APP_WEBHOOK_URL", "http://localhost:8000/webhooks/social-delivery"
)

MAX_PUBLISH_RETRIES = int(os.environ.get("MAX_PUBLISH_RETRIES", "3"))
