from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps


@dataclass(frozen=True)
class ImageDerivativeProfile:
    width: int
    quality: int
    suffix: str


@dataclass(frozen=True)
class GeneratedImageDerivative:
    content: bytes
    width: int
    height: int
    mime_type: str = "image/webp"
    extension: str = ".webp"


PRODUCT_IMAGE_DERIVATIVE_PROFILES: dict[str, ImageDerivativeProfile] = {
    "thumbnail": ImageDerivativeProfile(width=240, quality=74, suffix=".thumbnail.webp"),
    "card": ImageDerivativeProfile(width=480, quality=82, suffix=".card.webp"),
    "detail": ImageDerivativeProfile(width=1200, quality=86, suffix=".detail.webp"),
}


def generate_product_image_derivatives(content: bytes) -> dict[str, GeneratedImageDerivative]:
    with Image.open(BytesIO(content)) as image:
        image.load()
        normalized = ImageOps.exif_transpose(image)
        has_alpha = _has_alpha(normalized)
        normalized = normalized.convert("RGBA" if has_alpha else "RGB")

        return {
            name: _create_derivative(normalized, profile)
            for name, profile in PRODUCT_IMAGE_DERIVATIVE_PROFILES.items()
        }


def _create_derivative(
    image: Image.Image,
    profile: ImageDerivativeProfile,
) -> GeneratedImageDerivative:
    width, height = image.size
    target_width = min(profile.width, width)
    target_height = max(1, round(height * (target_width / width)))
    derivative = image
    if target_width != width:
        derivative = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

    output = BytesIO()
    derivative.save(
        output,
        "WEBP",
        quality=profile.quality,
        method=6,
        exact=_has_alpha(derivative),
    )
    return GeneratedImageDerivative(
        content=output.getvalue(),
        width=target_width,
        height=target_height,
    )


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        return True
    if image.mode == "P":
        return "transparency" in image.info
    return False
