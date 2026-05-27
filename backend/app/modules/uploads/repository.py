from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Banner, ProductImage


class UploadsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_product_image(self, image: ProductImage) -> None:
        self.session.add(image)

    def add_banner(self, banner: Banner) -> None:
        self.session.add(banner)

    async def next_product_image_position(self, product_id: int) -> int:
        result = await self.session.execute(
            select(func.max(ProductImage.position)).where(ProductImage.product_id == product_id)
        )
        current_max = result.scalar_one_or_none()
        if current_max is None:
            return 0
        return current_max + 1

    async def clear_primary_product_images(self, product_id: int) -> None:
        await self.session.execute(
            update(ProductImage)
            .where(ProductImage.product_id == product_id)
            .values(is_primary=False)
        )
