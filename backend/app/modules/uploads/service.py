from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, banner_cache_patterns, product_cache_patterns
from app.core.errors import AppError
from app.db.models import Banner, ProductImage
from app.modules.products.repository import ProductsRepository
from app.modules.uploads.repository import UploadsRepository
from app.modules.uploads.storage import LocalStorageService

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


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

        upload = await self._validate_and_read_image(file)
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
    ) -> Banner:
        upload = await self._validate_and_read_image(file)
        file_path = self.storage.save_bytes(
            upload.content,
            folder="banners",
            suffix=upload.extension,
        )
        banner = Banner(
            title=alt_text or upload.original_filename,
            file_path=file_path,
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            alt_text=alt_text,
        )

        try:
            self.repository.add_banner(banner)
            await self.session.commit()
            await self.session.refresh(banner)
        except IntegrityError as exc:
            await self.session.rollback()
            self.storage.delete(file_path)
            raise AppError("Could not persist banner image", status.HTTP_409_CONFLICT) from exc

        await self._invalidate_banner_cache()
        return banner

    async def _validate_and_read_image(self, file: UploadFile) -> "_ValidatedUpload":
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

        return _ValidatedUpload(
            content=content,
            extension=extension,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=len(content),
        )

    async def _invalidate_product_cache(self) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*product_cache_patterns())

    async def _invalidate_banner_cache(self) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*banner_cache_patterns())


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
