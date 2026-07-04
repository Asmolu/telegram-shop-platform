from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SellerPaymentSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_payment_settings(self) -> SellerPaymentSettings | None:
        result = await self.session.execute(
            select(SellerPaymentSettings).where(SellerPaymentSettings.id == 1)
        )
        return result.scalar_one_or_none()

    def add(self, instance: SellerPaymentSettings) -> None:
        self.session.add(instance)
