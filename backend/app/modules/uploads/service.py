from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, product_cache_patterns
from app.core.errors import AppError
from app.db.models import ProductImage
from app.modules.products.repository import ProductsRepository
from app.modules.uploads.image_profiles import (
    BANNER_IMAGE_PROFILES,
    PRODUCT_IMAGE_PROFILE,
    ImageUploadKind,
    ImageUploadProfile,
)
from app.modules.uploads.repository import UploadsRepository
from app.modules.uploads.schemas import BannerImageUploadRead
from app.modules.uploads.storage import LocalStorageService

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
PIL_IMAGE_MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


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

        upload = await self._validate_and_read_image(file, profile=PRODUCT_IMAGE_PROFILE)
        file_path = self.storage.save_bytes(
            upload.content,
            folder="products",
            suffix=upload.extension,
        )
        image = ProductImage(
            product_id=product_id,
            file_path=file_path,
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
            self.storage.delete(file_path)
            raise AppError("Could not persist product image", status.HTTP_409_CONFLICT) from exc

        await self._invalidate_product_cache()
        return image

    async def upload_banner_image(
        self,
        *,
        file: UploadFile,
        alt_text: str | None = None,
        image_kind: ImageUploadKind = ImageUploadKind.NATIVE_BANNER,
    ) -> BannerImageUploadRead:
        upload = await self._validate_and_read_image(
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

    async def _validate_and_read_image(
        self,
        file: UploadFile,
        *,
        profile: ImageUploadProfile,
    ) -> "_ValidatedUpload":
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

        return _ValidatedUpload(
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
        profile: ImageUploadProfile,
    ) -> None:
        try:
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                detected_mime_type = PIL_IMAGE_MIME_TYPES.get(image.format or "")
                if detected_mime_type != mime_type:
                    raise AppError("Invalid MIME type", status.HTTP_400_BAD_REQUEST)
                image.verify()
        except AppError:
            raise
        except (OSError, UnidentifiedImageError) as exc:
            raise AppError("Invalid image content", status.HTTP_400_BAD_REQUEST) from exc

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

class _ValidatedUpload:
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
