BRAND_VOICE = "Friendly, clear, a little bit excited about what we build."

PLATFORM_RULES = {
    "instagram": {
        "tone": "casual, uses 1-2 emojis, ends with a short call to action",
        "max_hashtags": 5,
    },
    "x": {
        "tone": "punchy and short, no more than ~250 characters, at most 1 emoji",
        "max_hashtags": 2,
    },
}


def _summarise(body: str, max_len: int = 160) -> str:
    cleaned = " ".join(body.split())
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len].rsplit(" ", 1)[0]
    return cut + "..."


def compose_caption(platform: str, blog_post_title: str, blog_post_body: str,
                     blog_post_url: str) -> str:
    if platform not in PLATFORM_RULES:
        raise ValueError(f"No caption rules defined for platform '{platform}'")

    summary = _summarise(blog_post_body)

    if platform == "instagram":
        caption = (
            f"{blog_post_title} \u2728\n\n"
            f"{summary}\n\n"
            f"Read the full post -> {blog_post_url}\n"
            f"#backend #buildinpublic #flyrank"
        )
    else:
        short_summary = _summarise(blog_post_body, max_len=100)
        caption = f"{blog_post_title}: {short_summary} {blog_post_url}"

    return caption
