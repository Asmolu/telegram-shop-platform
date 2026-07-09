from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import SellerPaymentSettings
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schemas import (
    PaymentSuccessBannerSettingsRead,
    PaymentSuccessBannerSettingsUpdate,
    SellerContactSettingsRead,
    SellerContactSettingsUpdate,
)


class SettingsService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        audit_service: AuditService | NoopAuditService | None = None,
    ) -> None:
        self.session = session
        self.repository = SettingsRepository(session)
        self.audit_service = audit_service or NoopAuditService()

    async def get_payment_success_banner_settings(self) -> PaymentSuccessBannerSettingsRead:
        payment_settings = await self.repository.get_payment_settings()
        return self._payment_success_banner_response(payment_settings)

    async def get_seller_contact_settings(self) -> SellerContactSettingsRead:
        payment_settings = await self.repository.get_payment_settings()
        return self._seller_contact_response(payment_settings)

    async def update_seller_contact_settings(
        self,
        payload: SellerContactSettingsUpdate,
        *,
        actor_user_id: int,
    ) -> SellerContactSettingsRead:
        payment_settings = await self.repository.get_payment_settings()
        before_data = self._seller_contact_audit_data(payment_settings)
        if payment_settings is None:
            payment_settings = SellerPaymentSettings(id=1)
            self.repository.add(payment_settings)

        payment_settings.seller_contact_telegram_url = payload.telegram_url
        payment_settings.seller_contact_whatsapp_url = payload.whatsapp_url
        payment_settings.seller_contact_instagram_url = payload.instagram_url
        payment_settings.updated_by_user_id = actor_user_id

        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action="seller_contact.settings_updated",
            entity_type="seller_payment_settings",
            entity_id=1,
            before_data=before_data,
            after_data=self._seller_contact_audit_data(payment_settings),
        )
        await self._commit("Seller contact settings update failed")
        await self._refresh_if_supported(payment_settings)
        return self._seller_contact_response(payment_settings)

    async def update_payment_success_banner_settings(
        self,
        payload: PaymentSuccessBannerSettingsUpdate,
        *,
        actor_user_id: int,
    ) -> PaymentSuccessBannerSettingsRead:
        payment_settings = await self.repository.get_payment_settings()
        before_data = self._payment_success_banner_audit_data(payment_settings)

        image_path = payload.image_path
        if payload.enabled and not image_path:
            raise AppError(
                "Payment success banner image is required before enabling",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        if payment_settings is None:
            payment_settings = SellerPaymentSettings(id=1)
            self.repository.add(payment_settings)

        payment_settings.payment_success_banner_enabled = payload.enabled
        payment_settings.payment_success_banner_image_path = image_path
        payment_settings.updated_by_user_id = actor_user_id

        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action="payment_success_banner.settings_updated",
            entity_type="seller_payment_settings",
            entity_id=1,
            before_data=before_data,
            after_data=self._payment_success_banner_audit_data(payment_settings),
        )
        await self._commit("Payment success banner settings update failed")
        await self._refresh_if_supported(payment_settings)
        return self._payment_success_banner_response(payment_settings)

    async def delete_payment_success_banner_settings(
        self,
        *,
        actor_user_id: int,
    ) -> PaymentSuccessBannerSettingsRead:
        payment_settings = await self.repository.get_payment_settings()
        before_data = self._payment_success_banner_audit_data(payment_settings)
        if payment_settings is None:
            payment_settings = SellerPaymentSettings(id=1)
            self.repository.add(payment_settings)

        payment_settings.payment_success_banner_enabled = False
        payment_settings.payment_success_banner_image_path = None
        payment_settings.updated_by_user_id = actor_user_id

        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action="payment_success_banner.settings_deleted",
            entity_type="seller_payment_settings",
            entity_id=1,
            before_data=before_data,
            after_data=self._payment_success_banner_audit_data(payment_settings),
        )
        await self._commit("Payment success banner settings delete failed")
        await self._refresh_if_supported(payment_settings)
        return self._payment_success_banner_response(payment_settings)

    async def _commit(self, message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(message, status.HTTP_409_CONFLICT) from exc

    async def _refresh_if_supported(self, instance: SellerPaymentSettings) -> None:
        refresh = getattr(self.session, "refresh", None)
        if refresh is not None:
            await refresh(instance)

    def _payment_success_banner_audit_data(
        self,
        payment_settings: SellerPaymentSettings | None,
    ) -> dict[str, object] | None:
        if payment_settings is None:
            return None
        return {
            "payment_success_banner_enabled": (
                payment_settings.payment_success_banner_enabled
            ),
            "payment_success_banner_image_path": (
                payment_settings.payment_success_banner_image_path
            ),
        }

    def _payment_success_banner_response(
        self,
        payment_settings: SellerPaymentSettings | None,
    ) -> PaymentSuccessBannerSettingsRead:
        if payment_settings is None:
            return PaymentSuccessBannerSettingsRead(
                enabled=False,
                image_path=None,
                image_url=None,
                updated_at=None,
            )

        image_path = payment_settings.payment_success_banner_image_path
        return PaymentSuccessBannerSettingsRead(
            enabled=payment_settings.payment_success_banner_enabled,
            image_path=image_path,
            image_url=settings.public_upload_url_for(image_path) if image_path else None,
            updated_at=payment_settings.updated_at,
        )

    def _seller_contact_audit_data(
        self,
        payment_settings: SellerPaymentSettings | None,
    ) -> dict[str, object] | None:
        if payment_settings is None:
            return None
        return {
            "seller_contact_telegram_url": payment_settings.seller_contact_telegram_url,
            "seller_contact_whatsapp_url": payment_settings.seller_contact_whatsapp_url,
            "seller_contact_instagram_url": payment_settings.seller_contact_instagram_url,
        }

    def _seller_contact_response(
        self,
        payment_settings: SellerPaymentSettings | None,
    ) -> SellerContactSettingsRead:
        if payment_settings is None:
            return SellerContactSettingsRead(updated_at=None)
        return SellerContactSettingsRead(
            telegram_url=payment_settings.seller_contact_telegram_url,
            whatsapp_url=payment_settings.seller_contact_whatsapp_url,
            instagram_url=payment_settings.seller_contact_instagram_url,
            updated_at=payment_settings.updated_at,
        )
