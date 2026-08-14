from PIL import Image
from app.image_pipeline import generate_placeholder_source_image, generate_variant


def test_instagram_variant_is_square_1080(tmp_path):
    source = generate_placeholder_source_image(str(tmp_path / "source.jpg"))
    out = generate_variant(source, "instagram", str(tmp_path / "out"))

    with Image.open(out) as img:
        assert img.size == (1080, 1080)


def test_x_variant_is_1600x900(tmp_path):
    source = generate_placeholder_source_image(str(tmp_path / "source.jpg"))
    out = generate_variant(source, "x", str(tmp_path / "out"))

    with Image.open(out) as img:
        assert img.size == (1600, 900)


def test_unknown_platform_raises(tmp_path):
    source = generate_placeholder_source_image(str(tmp_path / "source.jpg"))
    try:
        generate_variant(source, "tiktok", str(tmp_path / "out"))
        assert False
    except ValueError:
        pass


def test_subject_stays_in_safe_zone_after_crop(tmp_path):
    source = generate_placeholder_source_image(str(tmp_path / "source.jpg"))

    for platform in ("instagram", "x"):
        out = generate_variant(source, platform, str(tmp_path / "out"))
        with Image.open(out) as img:
            w, h = img.size
            center_pixel = img.getpixel((w // 2, h // 2))
            r, g, b = center_pixel[:3]
            assert abs(r - 230) < 20
            assert abs(g - 150) < 20
            assert abs(b - 40) < 20
