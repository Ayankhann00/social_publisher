# Build log

Honest log of where AI helped, where it was wrong, and what I changed. Built solo over about two days.

## Where AI (Claude) helped
- Scaffolding the whole file/folder layout in one go instead of me typing it out file by file — saved a lot of time on boilerplate (Pydantic schemas, SQLAlchemy models).
- The idempotency-cache logic in fake_platform/server.py — I knew I needed something like this conceptually but wasn't sure exactly where in the request flow the check should happen (before or after the rate limiter). AI put it before, which makes sense: a retried request that's already been done shouldn't get rate-limited.
- The "cover resize" crop math in image_pipeline.py. I understood *what* I wanted (centre-crop to fill the target box) but wouldn't have gotten the ratio comparison right on the first try.

## Where I had to fix/rework things
- First version had the SocialPost status flip to "published" directly inside scheduler.py right after publish() returned successfully. That's wrong per the brief — status should only change once the webhook confirms delivery. Had to move that logic into the webhook handler instead and leave the scheduler just setting "publishing".
- Original idempotency key was a random UUID generated at publish time, which defeats the whole point (a retry would get a *new* key). Changed it to be deterministic — built from campaign_id + platform — so retries always send the same key.
- Had to add the `misfire_grace_time` param to APScheduler manually after testing what happens if the app is down when a scheduled time passes — without it, missed jobs just get dropped instead of catching up.

## What I'd do differently with more time
- Right now the idempotency cache in fake_platform/server.py is just an in-memory dict — it resets if that process restarts. A real implementation would put it in the database.
- Only one retry policy (429 backoff). Didn't get to handle connection timeouts/dropped connections as their own case.
- No real auth on the main app's own API (anyone can hit POST /campaigns). Out of scope for a sandboxed capstone but would matter in a real product.

## Hardening pass (after first submission draft)

Went back through against the Definition of Done checklist properly and found the crash recovery story was basically fake — the scheduler could leave a post stuck in "publishing" forever if the process died mid-job, and there was no code anywhere that tried to fix that. Also realized my original rate-limit and idempotency tests were only testing the fake platform server directly through TestClient, never actually going through my own publisher's retry code — so a bug in the retry loop itself wouldn't have been caught.

Fixed both:
- Added `processing_started_at` to SocialPost as a simple lease timestamp, and a new `app/recovery.py` that finds posts stuck in "publishing" past a threshold, resets them to "queued", and reschedules them. Runs automatically on startup so a restarted worker fixes itself without a manual trigger.
- Rewrote the tests so the fake platform server actually runs as a live HTTP server in the background during the test session (using uvicorn programmatically, no new dependency needed since uvicorn was already required). That let me write a test that really does: publish -> simulate a crash by backdating the lease -> call the real recovery function -> wait for the scheduler to pick it back up -> confirm the same external post ID comes back (proving no duplicate) -> send a real webhook and confirm it reaches "published".
- Same idea for the 429 test — instead of just checking that the fake server returns 429, I forced my own publisher through a live 429 and asserted it slept for exactly the Retry-After value before succeeding.
- Also added direct tests against the /webhooks/social-delivery endpoint itself (valid, forged, duplicate, and a late webhook against an already-published post), since the old tests only checked the signature-checking function in isolation, not the actual route.

Caught one real thing while writing the 429 test: my first version of the assertion failed because the fake platform's own webhook-delivery delay (`time.sleep(2)` in a background thread) and my publisher's retry backoff both go through the same `time.sleep` since everything runs in one process during tests — monkeypatching one monkeypatches both. Not an actual bug in the retry logic, just something to filter out in the test.

Caught a second real thing in the crash recovery test itself: right after calling `recover_stale_publishing_posts()`, I asserted the post's status was back to `"queued"`. That assertion was flaky — sometimes passed, sometimes failed — because recovery reschedules the post for immediate republishing before returning, and the background scheduler can grab it and move it to `"publishing"` again before my very next line even runs. Fixed by polling for the final settled state instead of asserting a specific in-between snapshot. Ran it 10 times in a row after the fix with no failures.

Also added: a LICENSE file (was missing), removed the one leftover `print()` in the fake platform server in favor of logging, and a lightweight "safe zone" test that checks the subject's pixel color survives the crop for both platforms.
