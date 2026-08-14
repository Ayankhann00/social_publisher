# Multi-Platform Social Campaign Publisher

FlyRank Internship — Backend Track capstone. Turns one blog post into a scheduled, multi-platform social campaign: platform-sized images, platform-tailored captions, published through an adapter layer against a fake social platform, with idempotency, rate-limit handling, durable scheduling, and signature-verified delivery webhooks.

No real Instagram/X account is ever touched — everything runs against a local fake platform server included in this repo.

## Architecture

```
Blog post
  |
  |-- caption composer (shared voice + platform rules) --> per-platform captions
  |-- image pipeline (Pillow cover-crop)                --> per-platform images

Campaign created --> one SocialPost row per platform, scheduled_time set
  |
  v
APScheduler (SQLite-backed job store, survives restarts)
  |
  v
SocialPublisher interface
  |-- FakeInstagramPublisher
  |-- FakeXPublisher
  (idempotency key, 429/Retry-After backoff, encrypted token)
  |
  v
Fake Social Platform (fake_platform/server.py)
  |
  v
signed delivery webhook --> POST /webhooks/social-delivery
  |-- signature invalid --> 400, nothing changes
  |-- signature valid   --> status: queued -> published | failed

App startup
  |
  v
recover_stale_publishing_posts() --> any post stuck in "publishing"
                                      past its lease window is reset
                                      to "queued" and rescheduled now
```

Two processes: the main app (`app/main.py`) and the fake platform (`fake_platform/server.py`). They only talk to each other over plain HTTP, same as the main app would talk to a real Instagram/X API.

`fake_platform/server.py` is this project's own implementation of what the capstone brief describes (OAuth-style bearer check, idempotency keys, `429`/`Retry-After`, signed async delivery webhooks) — no FlyRank-provided starter server was supplied with the brief, so this is a from-scratch reimplementation of that spec, not a copy of anything FlyRank shipped.

## Design decisions (and honest limitations)

- **SQLite instead of Docker Postgres.** The brief suggests Postgres in Docker; this uses SQLite through SQLAlchemy instead, since it needs zero setup and gives the same relational guarantees (foreign keys, transactions, unique constraints) at this scale. Swapping to Postgres later is a one-line change to `DATABASE_URL` — nothing in `models.py` or the query code would need to change.
- **Fernet instead of raw AES-GCM.** Tokens are encrypted with `cryptography`'s `Fernet`, which uses AES-128-CBC with a random IV plus an HMAC for integrity under the hood — same real guarantees (random IV, authenticated, never plaintext at rest) as hand-rolled AES-GCM, with far less code to get wrong.
- **In-memory idempotency cache on the fake platform.** `fake_platform/server.py` keeps its idempotency cache and rate-limit counter in a plain Python dict, so it resets if that process restarts. Fine for a sandboxed demo; a real platform obviously persists this.
- **Only two platforms, one dummy source image.** Matches the brief's "realistic scope" — Instagram (1:1) and X (16:9), source image is a generated placeholder rather than a real photo. The graded part is the variant pipeline producing correct dimensions, not artwork.
- **No auth on the main app's own API.** Anyone who can reach `POST /campaigns` can create one. Out of scope for this capstone, would matter in a real product.
- **Crash recovery uses a lease timestamp, not a task queue.** A post moving to `"publishing"` gets a `processing_started_at` timestamp. On startup, anything still `"publishing"` after a threshold is assumed to have been abandoned by a dead worker, gets reset to `"queued"`, and is rescheduled immediately. No Celery, no Redis, no distributed lock — just one column and one query, which is enough at this scale.
- **Captions are template-based, not AI-generated.** The brief says composition is what's graded, not writing quality, so `app/captions.py` combines shared + platform-specific string fragments instead of calling an LLM. Swapping in a real model call later only means changing the inside of `_summarise()`.

## Project layout

```
app/
  main.py                  FastAPI app: campaigns, webhook handler
  config.py                env var loading
  database.py               SQLAlchemy engine/session
  models.py                 Campaign, SocialPost, SocialToken, WebhookEvent
  schemas.py                Pydantic request/response models
  image_pipeline.py         Pillow cover-crop resize per platform spec
  captions.py                caption composition per platform
  token_store.py             fake OAuth token creation + encrypted storage
  scheduler.py                APScheduler durable job scheduling
  recovery.py                 finds and reschedules posts stuck mid-publish
  publishers/
    base.py                  SocialPublisher interface
    fake_platform_publisher.py   shared HTTP + idempotency + backoff logic
    fake_instagram.py
    fake_x.py
fake_platform/
  server.py                 mock social platform: OAuth check, idempotency,
                             rate limiting, async delivery webhook
common/
  security.py                HMAC signing/verification + Fernet encrypt/decrypt
                              (shared by both app/ and fake_platform/)
tests/
seed.py                      creates one demo campaign against a running app
```

## Running it

Requires Python 3.10+.

```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the output into TOKEN_ENCRYPTION_KEY in .env
```

Start both servers, each in its own terminal:

```bash
uvicorn fake_platform.server:app --port 9000
uvicorn app.main:app --port 8000
```

Seed a demo campaign:

```bash
python seed.py
```

Check progress (run a few times — status moves from `queued` to `publishing` to `published`/`failed` as the scheduler and webhook fire):

```bash
curl http://localhost:8000/campaigns/<id-printed-by-seed.py>
```

Run tests:

```bash
pytest -v
```

The tests start their own instance of the fake platform server on `127.0.0.1:9091` in a background thread for the duration of the test session (see `tests/conftest.py`) — you don't need to have it running separately first.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/campaigns` | Create a campaign — generates images, captions, schedules posts |
| GET | `/campaigns/{id}` | Full campaign + per-platform post status |
| GET | `/campaigns` | List all campaigns |
| POST | `/webhooks/social-delivery` | Signed delivery event from the fake platform (not meant to be called by hand except to test rejection) |

## Demo script (~6 minutes)

1. Start both servers, run `python seed.py` — a campaign is created scheduled 10 seconds out.
2. `curl` the campaign immediately — both posts are `queued`, images already generated at the right sizes, captions differ per platform.
3. Wait ~15 seconds, `curl` again — status has moved to `published` (or `failed`, since the fake platform randomly fails ~10% of deliveries on purpose) via the scheduler + webhook, with no manual trigger.
4. Hammer the same campaign's publish request twice (same idempotency key, e.g. by re-running the scheduler job manually or resending the same `/publish` call to the fake platform) — prove one external post ID, not two.
5. Send a forged webhook with a garbage `X-Signature` header — `400`, status unchanged. Send a real one — status updates.
6. `pytest -v tests/test_crash_recovery.py -v` — walks through a full crash: a post gets published, its lease is backdated to simulate a dead worker, `recover_stale_publishing_posts()` resets and reschedules it, the scheduler republishes it, and the platform's idempotency key proves no duplicate was created.
7. Close on the full pinned test suite passing (`pytest -v`, 17/17 green) as the correctness backstop.

## What's not built (by design — see "Realistic scope" in the brief)

- Real platform publishing (opt-in stretch, not attempted here)
- Brand template overlays / logos
- Approval workflow beyond raw status
- Analytics loopback from the fake platform
