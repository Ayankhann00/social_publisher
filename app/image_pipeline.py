import os
from PIL import Image, ImageDraw, ImageFont

PLATFORM_SPECS = {
    "instagram": (1080, 1080),
    "x": (1600, 900),
}


def generate_placeholder_source_image(path: str, label: str = "FlyRank Demo") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (1200, 1200), color=(40, 90, 160))
    draw = ImageDraw.Draw(img)
    draw.rectangle([300, 300, 900, 900], fill=(230, 150, 40))
    try:
        font = ImageFont.load_default()
        draw.text((320, 590), label, fill="white", font=font)
    except Exception:
        pass
    img.save(path)
    return path


def _cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / src_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def generate_variant(source_path: str, platform: str, output_dir: str) -> str:
    if platform not in PLATFORM_SPECS:
        raise ValueError(f"No image spec defined for platform '{platform}'")

    target_w, target_h = PLATFORM_SPECS[platform]

    with Image.open(source_path) as img:
        img = img.convert("RGB")
        variant = _cover_resize(img, target_w, target_h)

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{platform}.jpg")
        variant.save(out_path, quality=90)

    with Image.open(out_path) as check:
        assert check.size == (target_w, target_h)

    return out_path


def generate_all_variants(source_path: str, platforms: list, output_dir: str) -> dict:
    return {p: generate_variant(source_path, p, output_dir) for p in platforms}
