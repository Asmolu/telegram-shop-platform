import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
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
    await engine.dispose()


asyncio.run(main())
