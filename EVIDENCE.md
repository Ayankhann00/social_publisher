# Evidence

Every item below was actually run. Command and result are real output from this codebase, captured during the hardening pass that added crash recovery, live-HTTP reliability tests, and webhook endpoint tests.

## Full test suite

```
$ pytest -v
tests/test_crash_recovery.py::test_worker_crash_mid_publish_recovers_without_duplicate PASSED
tests/test_idempotency.py::test_duplicate_publish_returns_same_external_id PASSED
tests/test_idempotency.py::test_missing_idempotency_key_is_rejected PASSED
tests/test_idempotency.py::test_rate_limit_eventually_triggers PASSED
tests/test_image_pipeline.py::test_instagram_variant_is_square_1080 PASSED
tests/test_image_pipeline.py::test_x_variant_is_1600x900 PASSED
tests/test_image_pipeline.py::test_unknown_platform_raises PASSED
tests/test_image_pipeline.py::test_subject_stays_in_safe_zone_after_crop PASSED
tests/test_publisher_reliability.py::test_publisher_retries_after_429_and_succeeds PASSED
tests/test_publisher_reliability.py::test_repeated_publish_call_does_not_duplicate_on_platform PASSED
tests/test_webhook_endpoint.py::test_valid_webhook_updates_status PASSED
tests/test_webhook_endpoint.py::test_forged_webhook_is_rejected PASSED
tests/test_webhook_endpoint.py::test_duplicate_webhook_event_is_ignored PASSED
tests/test_webhook_endpoint.py::test_webhook_does_not_flip_terminal_state_backward PASSED
tests/test_webhook_signature.py::test_valid_signature_is_accepted PASSED
tests/test_webhook_signature.py::test_forged_signature_is_rejected PASSED
tests/test_webhook_signature.py::test_wrong_secret_is_rejected PASSED

17 passed in 1.41s
```

## 1. Image generation / platform formatting

`tests/test_image_pipeline.py::test_instagram_variant_is_square_1080` and `::test_x_variant_is_1600x900` open the actual generated JPEG files with Pillow and assert `.size == (1080, 1080)` and `.size == (1600, 900)`. Both PASSED.

`::test_subject_stays_in_safe_zone_after_crop` checks the pixel color at the exact center of each generated variant matches the placeholder's "subject" rectangle color, for both platforms. This is the simple, testable proxy for "the main subject stays inside the frame" — proven by the cover-crop always keeping the image center, never the edges. PASSED.

Captions: `app/captions.py::compose_caption` produces a longer, emoji/hashtag-bearing string for Instagram and a shorter plain string for X from the same input. Verified by direct inspection of `GET /campaigns/{id}` output during manual runs — the two caption fields are never equal for the same post.

## 2. Social publishing architecture

`app/publishers/base.py` defines `SocialPublisher` as an abstract class with one method, `publish()`. `FakeInstagramPublisher` and `FakeXPublisher` both subclass `FakePlatformPublisher`, which implements the interface. `app/scheduler.py` only references `PUBLISHERS[post.platform]` — it never branches on the platform string to decide which HTTP call to make.

## 3. Token security

Tokens are encrypted with Fernet before being written to `social_tokens.encrypted_token` (`common/security.py`, `app/token_store.py`). Verified directly against the SQLite file:

```
$ python3 -c "
import sqlite3
conn = sqlite3.connect('data/app.db')
rows = conn.execute('select platform, encrypted_token from social_tokens').fetchall()
for r in rows: print(r[0], '->', r[1][:30], '...')
"
x -> gAAAAABqeNbTrk7LuHGokKi2jvoWNR ...
instagram -> gAAAAABqeNbTbHvDhyNaVjQWKE--2q ...
```

`SocialToken` is never referenced in `app/schemas.py` or any route in `app/main.py`, so it cannot be returned by any API response. `.env` is git-ignored (see `.gitignore`); `.env.example` exists with placeholder values and no real secret.

## 4. Idempotency

Two levels are tested:

- `tests/test_publisher_reliability.py::test_repeated_publish_call_does_not_duplicate_on_platform` calls `FakeInstagramPublisher().publish()` twice with the same post object (same idempotency key) directly, over real HTTP to the live fake platform server, and asserts both calls return the same `external_post_id`, the second call reports `replayed=True`, and only one entry exists in the fake platform's idempotency store afterward. PASSED.
- `tests/test_crash_recovery.py` (see section 6 below) proves idempotency survives a worker restart, not just a same-process retry — the deeper case the brief asks for.

## 5. Rate limiting / 429

`tests/test_publisher_reliability.py::test_publisher_retries_after_429_and_succeeds` forces the live fake platform's internal request counter so the very next `/publish` call returns `429` with `Retry-After: 2`. `time.sleep` is monkeypatched to record its arguments instead of actually waiting. The test asserts:

- the publisher's own retry-backoff sleep call was `2.0` seconds — the exact value from the response header, not a hardcoded guess
- the call eventually returned a successful `external_post_id`
- only one entry was created in the platform's idempotency store (the failed 429 attempt did not get counted as a real post)

This exercises `app/publishers/fake_platform_publisher.py`'s actual retry loop, not the fake server in isolation. PASSED.

## 6. Durable scheduling & crash recovery (previously missing, now implemented and tested)

**What was added:** `SocialPost.processing_started_at` (a lease timestamp, set when a post moves to `"publishing"`) and `app/recovery.py::recover_stale_publishing_posts()`, which finds posts stuck in `"publishing"` whose lease is older than a threshold, resets them to `"queued"`, and reschedules them for immediate republishing. This runs automatically on app startup (`app/main.py::on_startup`), which is what makes a restarted worker self-heal instead of needing a manual recovery endpoint.

**Real test, not a hardcoded result:** `tests/test_crash_recovery.py::test_worker_crash_mid_publish_recovers_without_duplicate`:

1. Creates a real `Campaign` + `SocialPost` row directly in the database.
2. Calls `publish_due_post()` for real — this hits the live fake platform over HTTP and gets a real `external_post_id`. The post is left in `"publishing"` (matching the app's actual design: status only becomes terminal once a webhook confirms it).
3. Manually backdates `processing_started_at` by 10 minutes to simulate a worker that died and never followed up.
4. Calls `recover_stale_publishing_posts(stale_after_seconds=60)` — the real recovery function, not a test-only shortcut. Asserts the post's ID is in the returned recovered list, proving the stale-lease detection query actually found it.
5. Waits (polling, up to 5 seconds) for the real `BackgroundScheduler` to pick the rescheduled job back up and run `publish_due_post()` again to completion.
6. Asserts the `external_post_id` after this second run is **identical** to the one from step 2 — proving the platform-level idempotency key stopped a second post from being created, even though the publish path ran twice.
7. Confirms the fake platform's idempotency cache holds exactly one entry for this post's key, mapped to that one `external_post_id`.
8. Builds and sends a real signed webhook (`common.security.sign_payload`) through the actual `/webhooks/social-delivery` endpoint via `TestClient`, and confirms the database status becomes `"published"`.

PASSED (verified stable across 10 consecutive runs, since it involves real background threads). This is the complete PROBE 3 scenario from the brief: crash mid-publish, restart/recovery, resumes automatically, exactly one platform post, database reaches a terminal published state, no duplicate.

One race condition surfaced and was fixed during this: `recover_stale_publishing_posts()` reschedules the post for immediate republishing before returning, so the background scheduler can pick it up and move it out of `"queued"` again before the very next line of the test even runs. The test now polls for the final settled state instead of asserting a specific intermediate snapshot that isn't guaranteed to be observable.

## 7. Webhooks

`tests/test_webhook_endpoint.py` (all against the real `/webhooks/social-delivery` route via `TestClient`, not against `common/security.py` in isolation):

- `test_valid_webhook_updates_status` — correctly signed payload leads to `200`, database status and `external_post_id` updated. PASSED.
- `test_forged_webhook_is_rejected` — payload with a garbage signature leads to `400`, database completely unchanged. PASSED.
- `test_duplicate_webhook_event_is_ignored` — the same valid event sent twice — second call returns `200` with `{"status": "ignored_duplicate"}`, no error, no double-processing. PASSED.
- `test_webhook_does_not_flip_terminal_state_backward` — a valid, differently-signed webhook arriving for a post already `"published"` is accepted (`200`) but does not change the stored status or `external_post_id`. PASSED.

## 8. Database / state management

States are `queued -> publishing -> published | failed`. The webhook handler now refuses to move a post out of a terminal state (`published`/`failed`) even if a later webhook arrives for it — see `app/main.py::handle_delivery_webhook`. Combined with the recovery mechanism in section 6, a post can no longer get permanently stuck in `"publishing"`.

## 9. Fake social platform

`fake_platform/server.py` is this project's own implementation of what the brief specifies (OAuth-style bearer check, idempotency-key handling, rate limiting with `Retry-After`, asynchronous signed delivery webhooks). It is not a FlyRank-authored starter file, since none was provided alongside the brief PDF. It is used consistently as the only publishing target throughout the app and the tests.

## Known limitation

`datetime.datetime.utcnow()` is used throughout (models, scheduler, recovery) and raises a `DeprecationWarning` on Python 3.12+. It still behaves correctly. Switching every timestamp to timezone-aware `datetime.now(datetime.UTC)` would touch the SQLAlchemy column definitions too and wasn't done in this pass to avoid widening the change for no functional benefit.
