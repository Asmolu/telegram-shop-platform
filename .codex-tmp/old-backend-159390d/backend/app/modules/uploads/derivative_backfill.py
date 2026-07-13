import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProductImage
from app.modules.uploads.image_derivatives import (
    PRODUCT_IMAGE_DERIVATIVE_PROFILES,
    generate_product_image_derivatives,
)
from app.modules.uploads.storage import LocalStorageService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductImageBackfillReport:
    processed: int
    skipped: int
    failed: int
    would_process: int
    last_seen_id: int | None


async def backfill_product_image_derivatives(
    session: AsyncSession,
    *,
    storage: LocalStorageService | None = None,
    limit: int = 100,
    after_id: int = 0,
    dry_run: bool = True,
) -> ProductImageBackfillReport:
    storage = storage or LocalStorageService()
    safe_limit = min(max(limit, 1), 500)
    result = await session.execute(
        select(ProductImage)
        .where(ProductImage.id > after_id)
        .order_by(ProductImage.id)
        .limit(safe_limit)
    )
    images = list(result.scalars().all())
    processed = 0
    skipped = 0
    failed = 0
    would_process = 0
    last_seen_id = images[-1].id if images else None

    for image in images:
        if _has_all_derivatives(image):
            skipped += 1
            continue
        would_process += 1
        if dry_run:
            continue

        created_paths: list[str] = []
        try:
            original = storage.read_bytes(image.file_path)
            derivatives = generate_product_image_derivatives(original)
            image.thumbnail_path = _save_derivative(
                storage,
                derivatives["thumbnail"].content,
                "thumbnail",
                created_paths,
            )
            image.card_path = _save_derivative(
                storage,
                derivatives["card"].content,
                "card",
                created_paths,
            )
            image.detail_path = _save_derivative(
                storage,
                derivatives["detail"].content,
                "detail",
                created_paths,
            )
            await session.commit()
            processed += 1
        except Exception:
            await session.rollback()
            failed += 1
            _cleanup_created_paths(storage, created_paths, stage="product_derivative_backfill")
            logger.warning(
                "Product image derivative backfill failed for product_image_id=%s",
                image.id,
                exc_info=True,
            )

    return ProductImageBackfillReport(
        processed=processed,
        skipped=skipped,
        failed=failed,
        would_process=would_process,
        last_seen_id=last_seen_id,
    )


def _has_all_derivatives(image: ProductImage) -> bool:
    return bool(image.thumbnail_path and image.card_path and image.detail_path)


def _save_derivative(
    storage: LocalStorageService,
    content: bytes,
    name: str,
    created_paths: list[str],
) -> str:
    path = storage.save_bytes(
        content,
        folder="products",
        suffix=PRODUCT_IMAGE_DERIVATIVE_PROFILES[name].suffix,
    )
    created_paths.append(path)
    return path


def _cleanup_created_paths(
    storage: LocalStorageService,
    paths: list[str],
    *,
    stage: str,
) -> None:
    for path in paths:
        try:
            storage.delete(path)
        except OSError:
            logger.warning("Failed to delete upload during %s: %s", stage, path)
