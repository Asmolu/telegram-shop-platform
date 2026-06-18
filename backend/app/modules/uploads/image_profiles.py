from dataclasses import dataclass
from enum import StrEnum


class ImageUploadKind(StrEnum):
    NATIVE_BANNER = "native_banner"
    VERTICAL_BANNER = "vertical_banner"
    POPUP_BANNER = "popup_banner"
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

TAG_IMAGE_PROFILE = ImageUploadProfile(
    display_name="tag",
    aspect_label="4:3",
    aspect_ratio=4 / 3,
    recommended_width=1200,
    recommended_height=900,
    min_width=600,
    min_height=450,
    max_width=1600,
    max_height=1200,
    max_pixels=1_920_000,
)

CATEGORY_IMAGE_PROFILE = ImageUploadProfile(
    display_name="category",
    aspect_label="4:3",
    aspect_ratio=4 / 3,
    recommended_width=1200,
    recommended_height=900,
    min_width=600,
    min_height=450,
    max_width=1600,
    max_height=1200,
    max_pixels=1_920_000,
)

NATIVE_BANNER_IMAGE_PROFILE = ImageUploadProfile(
    display_name="баннера",
    aspect_label="60:23",
    aspect_ratio=60 / 23,
    recommended_width=1800,
    recommended_height=690,
    min_width=900,
    min_height=345,
    max_width=2400,
    max_height=920,
    max_pixels=2_208_000,
)

VERTICAL_BANNER_IMAGE_PROFILE = ImageUploadProfile(
    display_name="banner",
    aspect_label="9:16",
    aspect_ratio=9 / 16,
    recommended_width=900,
    recommended_height=1600,
    min_width=450,
    min_height=800,
    max_width=1350,
    max_height=2400,
    max_pixels=3_240_000,
)

POPUP_BANNER_IMAGE_PROFILE = ImageUploadProfile(
    display_name="banner",
    aspect_label="3:4",
    aspect_ratio=3 / 4,
    recommended_width=900,
    recommended_height=1200,
    min_width=450,
    min_height=600,
    max_width=1350,
    max_height=1800,
    max_pixels=2_430_000,
)

AGGRESSIVE_BANNER_IMAGE_PROFILE = ImageUploadProfile(
    display_name="баннера",
    aspect_label="9:16",
    aspect_ratio=9 / 16,
    recommended_width=900,
    recommended_height=1600,
    min_width=450,
    min_height=800,
    max_width=1350,
    max_height=2400,
    max_pixels=3_240_000,
)

BANNER_IMAGE_PROFILES = {
    ImageUploadKind.NATIVE_BANNER: NATIVE_BANNER_IMAGE_PROFILE,
    ImageUploadKind.VERTICAL_BANNER: VERTICAL_BANNER_IMAGE_PROFILE,
    ImageUploadKind.POPUP_BANNER: POPUP_BANNER_IMAGE_PROFILE,
    ImageUploadKind.AGGRESSIVE_BANNER: AGGRESSIVE_BANNER_IMAGE_PROFILE,
}
