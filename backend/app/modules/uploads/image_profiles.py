from dataclasses import dataclass
from enum import StrEnum


class ImageUploadKind(StrEnum):
    NATIVE_BANNER = "native_banner"
    AGGRESSIVE_BANNER = "aggressive_banner"


@dataclass(frozen=True)
class ImageUploadProfile:
    display_name: str
    aspect_label: str
    aspect_ratio: float
    recommended_width: int
    recommended_height: int
    min_width: int
    min_height: int
    max_width: int
    max_height: int
    max_pixels: int
    aspect_tolerance: float = 0.02

    @property
    def recommended_size_label(self) -> str:
        return f"{self.recommended_width}x{self.recommended_height}"

    @property
    def min_size_label(self) -> str:
        return f"{self.min_width}x{self.min_height}"

    @property
    def max_size_label(self) -> str:
        return f"{self.max_width}x{self.max_height}"


PRODUCT_IMAGE_PROFILE = ImageUploadProfile(
    display_name="товара",
    aspect_label="4:5",
    aspect_ratio=4 / 5,
    recommended_width=1200,
    recommended_height=1500,
    min_width=600,
    min_height=750,
    max_width=1600,
    max_height=2000,
    max_pixels=3_200_000,
)

NATIVE_BANNER_IMAGE_PROFILE = ImageUploadProfile(
    display_name="баннера",
    aspect_label="16:9",
    aspect_ratio=16 / 9,
    recommended_width=1600,
    recommended_height=900,
    min_width=800,
    min_height=450,
    max_width=2400,
    max_height=1350,
    max_pixels=3_240_000,
)

AGGRESSIVE_BANNER_IMAGE_PROFILE = ImageUploadProfile(
    display_name="баннера",
    aspect_label="3:1",
    aspect_ratio=3 / 1,
    recommended_width=1800,
    recommended_height=600,
    min_width=900,
    min_height=300,
    max_width=2400,
    max_height=800,
    max_pixels=1_920_000,
)

BANNER_IMAGE_PROFILES = {
    ImageUploadKind.NATIVE_BANNER: NATIVE_BANNER_IMAGE_PROFILE,
    ImageUploadKind.AGGRESSIVE_BANNER: AGGRESSIVE_BANNER_IMAGE_PROFILE,
}
