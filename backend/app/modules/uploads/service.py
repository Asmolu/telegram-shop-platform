import logging
import warnings
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, product_cache_patterns
from app.core.errors import AppError
from app.db.models import ProductImage
from app.modules.products.repository import ProductsRepository
from app.modules.uploads.image_derivatives import (
    PRODUCT_IMAGE_DERIVATIVE_PROFILES,
    generate_product_image_derivatives,
)
from app.modules.uploads.image_profiles import (
    BANNER_IMAGE_PROFILES,
    CATEGORY_IMAGE_PROFILE,
    PRODUCT_IMAGE_PROFILE,
    TAG_IMAGE_PROFILE,
    ImageUploadKind,
    ImageUploadProfile,
)
from app.modules.uploads.repository import UploadsRepository
from app.modules.uploads.schemas import (
    BannerImageUploadRead,
    CategoryImageUploadRead,
    TagImageUploadRead,
)
from app.modules.uploads.storage import LocalStorageService

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
MAX_GENERIC_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
PIL_IMAGE_MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
Image.MAX_IMAGE_PIXELS = MAX_GENERIC_IMAGE_PIXELS

logger = logging.getLogger(__name__)


class UploadsService:
    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService | None = None,
        cache: CacheService | None = None,
    ) -> None:
        self.session = session
        self.storage = storage or LocalStorageService()
        self.cache = cache
        self.repository = UploadsRepository(session)
        self.products_repository = ProductsRepository(session)

    async def upload_product_image(
        self,
        *,
        product_id: int,
        file: UploadFile,
        alt_text: str | None = None,
        position: int | None = None,
        is_primary: bool = False,
    ) -> ProductImage:
        product = await self.products_repository.get_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)

        upload = await self.validate_and_read_image(file, profile=PRODUCT_IMAGE_PROFILE)
        created_paths: list[str] = []
        file_path = self.storage.save_bytes(
            upload.content,
            folder="products",
            suffix=upload.extension,
        )
        created_paths.append(file_path)

        try:
            derivative_paths = self._save_product_derivatives(upload.content, created_paths)
        except Exception as exc:
            self._delete_created_paths(created_paths, stage="product_derivative_generation")
            logger.warning(
                "Product image derivative generation failed at stage product_derivative_generation",
                exc_info=True,
            )
            raise AppError(
                "Could not process product image",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            ) from exc

        image = ProductImage(
            product_id=product_id,
            file_path=file_path,
            thumbnail_path=derivative_paths.get("thumbnail"),
            card_path=derivative_paths.get("card"),
            detail_path=derivative_paths.get("detail"),
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            alt_text=alt_text,
            position=position
            if position is not None
            else await self.repository.next_product_image_position(product_id),
            is_primary=is_primary,
        )

        try:
            if is_primary:
                await self.repository.clear_primary_product_images(product_id)
            self.repository.add_product_image(image)
            await self.session.commit()
            await self.session.refresh(image)
        except IntegrityError as exc:
            await self.session.rollback()
            self._delete_created_paths(created_paths, stage="product_image_db_integrity")
            raise AppError("Could not persist product image", status.HTTP_409_CONFLICT) from exc
        except Exception:
            await self.session.rollback()
            self._delete_created_paths(created_paths, stage="product_image_db_failure")
            raise

        await self._invalidate_product_cache()
        return image

    async def upload_banner_image(
        self,
        *,
        file: UploadFile,
        alt_text: str | None = None,
        image_kind: ImageUploadKind = ImageUploadKind.NATIVE_BANNER,
    ) -> BannerImageUploadRead:
        upload = await self.validate_and_read_image(
            file,
            profile=BANNER_IMAGE_PROFILES[image_kind],
        )
        file_path = self.storage.save_bytes(
            upload.content,
            folder="banners",
            suffix=upload.extension,
        )
        return BannerImageUploadRead(
            file_path=file_path,
            url=f"/uploads/{file_path}",
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            alt_text=alt_text,
        )

    async def upload_tag_image(
        self,
        *,
        file: UploadFile,
        alt_text: str | None = None,
    ) -> TagImageUploadRead:
        upload = await self.validate_and_read_image(file, profile=TAG_IMAGE_PROFILE)
        file_path = self.storage.save_bytes(
            upload.content,
            folder="tags",
            suffix=upload.extension,
        )
        return TagImageUploadRead(
            file_path=file_path,
            url=f"/uploads/{file_path}",
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            alt_text=alt_text,
        )

    async def upload_category_image(
        self,
        *,
        file: UploadFile,
        alt_text: str | None = None,
    ) -> CategoryImageUploadRead:
        upload = await self.validate_and_read_image(file, profile=CATEGORY_IMAGE_PROFILE)
        file_path = self.storage.save_bytes(
            upload.content,
            folder="categories",
            suffix=upload.extension,
        )
        return CategoryImageUploadRead(
            file_path=file_path,
            url=f"/uploads/{file_path}",
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            alt_text=alt_text,
        )

    async def validate_and_read_image(
        self,
        file: UploadFile,
        *,
        profile: ImageUploadProfile | None = None,
    ) -> "ValidatedImageUpload":
        original_filename = _safe_original_filename(file.filename)
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise AppError("Invalid file extension", status.HTTP_400_BAD_REQUEST)

        mime_type = file.content_type or ""
        if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise AppError("Invalid MIME type", status.HTTP_400_BAD_REQUEST)

        content = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
        if len(content) > MAX_IMAGE_SIZE_BYTES:
            raise AppError("File size exceeds limit", status.HTTP_400_BAD_REQUEST)
        if not content:
            raise AppError("Uploaded file is empty", status.HTTP_400_BAD_REQUEST)

        self._validate_image_dimensions(content, mime_type=mime_type, profile=profile)

        return ValidatedImageUpload(
            content=content,
            extension=extension,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=len(content),
        )

    def _validate_image_dimensions(
        self,
        content: bytes,
        *,
        mime_type: str,
        profile: ImageUploadProfile | None,
    ) -> None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    detected_mime_type = PIL_IMAGE_MIME_TYPES.get(image.format or "")
                    if detected_mime_type != mime_type:
                        raise AppError("Invalid MIME type", status.HTTP_400_BAD_REQUEST)
                    image.load()
                    normalized = ImageOps.exif_transpose(image)
                    width, height = normalized.size
        except AppError:
            raise
        except (
            OSError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise AppError("Invalid image content", status.HTTP_400_BAD_REQUEST) from exc

        if profile is None:
            if width <= 0 or height <= 0 or width * height > MAX_GENERIC_IMAGE_PIXELS:
                raise AppError("Invalid image dimensions", status.HTTP_422_UNPROCESSABLE_CONTENT)
            return

        if width < profile.min_width or height < profile.min_height:
            raise AppError(
                f"Минимальный размер изображения {profile.display_name}: {profile.min_size_label}",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        pixels = width * height
        if (
            width > profile.max_width
            or height > profile.max_height
            or pixels > profile.max_pixels
        ):
            raise AppError(
                f"Максимальный размер изображения {profile.display_name}: {profile.max_size_label}",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        actual_ratio = width / height
        ratio_delta = abs(actual_ratio - profile.aspect_ratio) / profile.aspect_ratio
        if ratio_delta > profile.aspect_tolerance:
            raise AppError(
                f"Изображение {profile.display_name} должно быть {profile.aspect_label}",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    async def _invalidate_product_cache(self) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*product_cache_patterns())

    def _save_product_derivatives(self, content: bytes, created_paths: list[str]) -> dict[str, str]:
        derivatives = generate_product_image_derivatives(content)
        derivative_paths: dict[str, str] = {}
        for name, derivative in derivatives.items():
            profile = PRODUCT_IMAGE_DERIVATIVE_PROFILES[name]
            derivative_path = self.storage.save_bytes(
                derivative.content,
                folder="products",
                suffix=profile.suffix,
            )
            created_paths.append(derivative_path)
            derivative_paths[name] = derivative_path
        return derivative_paths

    def _delete_created_paths(self, paths: list[str], *, stage: str) -> None:
        for path in paths:
            try:
                self.storage.delete(path)
            except OSError:
                logger.warning("Failed to delete upload created during %s: %s", stage, path)


class ValidatedImageUpload:
    def __init__(
        self,
        *,
        content: bytes,
        extension: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
    ) -> None:
        self.content = content
        self.extension = extension
        self.original_filename = original_filename
        self.mime_type = mime_type
        self.size_bytes = size_bytes


def _safe_original_filename(filename: str | None) -> str:
    if not filename:
        return "upload"
    basename = PureWindowsPath(PurePosixPath(filename).name).name
    return basename.replace("\x00", "").strip()[:255] or "upload"
