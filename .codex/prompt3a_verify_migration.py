import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        columns = (
            await conn.execute(
                text(
                    """
                    select column_name
                    from information_schema.columns
                    where table_name = 'product_images'
                      and column_name in ('thumbnail_path', 'card_path', 'detail_path')
                    order by column_name
                    """
                )
            )
        ).scalars().all()
        print("columns=" + ",".join(columns))

        product_id = (
            await conn.execute(
                text(
                    """
                    insert into products (name, slug, base_price, status)
                    values ('Migration Product', 'migration-product', 100.00, 'ACTIVE')
                    returning id
                    """
                )
            )
        ).scalar_one()

        image_id = (
            await conn.execute(
                text(
                    """
                    insert into product_images (
                      product_id,
                      file_path,
                      thumbnail_path,
                      card_path,
                      detail_path,
                      position,
                      is_primary
                    )
                    values (
                      :product_id,
                      'products/source.jpg',
                      'products/source.thumbnail.webp',
                      'products/source.card.webp',
                      'products/source.detail.webp',
                      0,
                      true
                    )
                    returning id
                    """
                ),
                {"product_id": product_id},
            )
        ).scalar_one()

        row = (
            await conn.execute(
                text(
                    """
                    select file_path, thumbnail_path, card_path, detail_path
                    from product_images
                    where id = :image_id
                    """
                ),
                {"image_id": image_id},
            )
        ).one()
        print("product_image=" + "|".join(row))
    await engine.dispose()


asyncio.run(main())
