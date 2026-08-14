import datetime
import requests

APP_URL = "http://localhost:8000"

payload = {
    "title": "fox-post-demo",
    "blog_post_title": "Why Red Foxes Are Smarter Than You Think",
    "blog_post_body": (
        "Red foxes are one of the most adaptable animals on the planet, "
        "thriving everywhere from remote forests to busy city parks. Their "
        "problem-solving skills rival those of some primates."
    ),
    "blog_post_url": "https://example.com/blog/red-foxes",
    "platforms": ["instagram", "x"],
    "scheduled_time": (
        datetime.datetime.utcnow() + datetime.timedelta(seconds=10)
    ).isoformat(),
}

response = requests.post(f"{APP_URL}/campaigns", json=payload)
response.raise_for_status()
campaign = response.json()

print("Created campaign:", campaign["id"])
print("Check its status with:")
print(f"  curl {APP_URL}/campaigns/{campaign['id']}")
