from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def check_database_connection() -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def dispose_database_engine() -> None:
    await engine.dispose()
