"""Image normalization helpers for stored JPEG uploads."""
from io import BytesIO

from PIL import Image, ImageOps


def normalize_jpeg(image_bytes):
    """Apply EXIF orientation, remove stale metadata, and return JPEG bytes plus orientation."""
    with Image.open(BytesIO(image_bytes)) as source:
        orientation = source.getexif().get(274, 1)
        image = ImageOps.exif_transpose(source)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality=95)
    return output.getvalue(), orientation


def rotate_jpeg(image_bytes, direction):
    """Apply a manual quarter- or half-turn and return an upright JPEG."""
    rotations = {"clockwise": -90, "counterclockwise": 90, "180": 180}
    if direction not in rotations:
        raise ValueError(f"Unsupported image rotation: {direction}")

    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source)
        image = image.rotate(rotations[direction], expand=True)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality=95)
    return output.getvalue()
