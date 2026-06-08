import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from secrets import token_hex

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    NotificationChannel,
    Product,
    ProductImage,
    ProductStatus,
    ProductVariant,
    UserRole,
)
from app.modules.audit.service import AuditService
from app.modules.categories.repository import CategoriesRepository
from app.modules.notifications.schemas import NotificationList
from app.modules.notifications.service import NotificationsService
from app.modules.products.repository import ProductsRepository, ProductVariantsRepository
from app.modules.products.search import normalize_search_aliases
from app.modules.seller_bot.repository import SellerBotRepository
from app.modules.seller_bot.schemas import (
    SellerBotActionResponse,
    SellerBotBroadcastRequest,
    SellerBotMessageRequest,
    SellerBotStatusResponse,
)
from app.modules.tags.repository import TagsRepository
from app.modules.telegram.schemas import TelegramMessage, TelegramPhotoSize
from app.modules.telegram.service import TelegramDeliveryError, TelegramService
from app.modules.uploads.storage import LocalStorageService

SELLER_BOT_TEST_MESSAGE = "seller_bot.test_message"
SELLER_BOT_BROADCAST = "seller_bot.broadcast"
SELLER_BOT_BLOCK_SELLER = "seller_bot.block_seller"
SELLER_BOT_UNBLOCK_SELLER = "seller_unblocked"
SELLER_BOT_PRODUCT_DRAFT_CREATED = "bot_product_draft_created"
SELLER_BOT_PRODUCT_POST_REJECTED = "bot_product_post_rejected"
SELLER_BOT_COMMAND_LIMIT = 20
SELLER_GROUP_ONLY_MESSAGE = "Command is available only in the seller group."
POSTGRES_INT32_MAX = 2_147_483_647
SELLER_PANEL_PRODUCT_EDIT_URL = "https://seller.tsplatform.ru/products/{product_id}/edit"
QUICK_PRODUCT_SIZE_DEFAULT = "ONE_SIZE"
QUICK_PRODUCT_ALLOWED_FIELDS = {
    "Название": "title",
    "Цена": "price",
    "Старая цена": "old_price",
    "Описание": "description",
    "Категория": "category",
    "Теги": "tags",
    "Размеры": "sizes",
    "Цвет": "color",
    "SKU": "sku",
    "Остаток": "stock",
    "Приоритет поиска": "search_priority",
    "Ключевые слова": "search_aliases",
    "Статус": "status",
}


@dataclass(frozen=True)
class QuickProductDraft:
    title: str
    price: Decimal
    old_price: Decimal | None
    description: str | None
    category: str | None
    tags: list[str]
    sizes: list[str]
    color: str | None
    sku: str | None
    stock: int | None
    search_priority: int
    search_aliases: str | None
    status: ProductStatus


class SellerBotService:
    """Seller bot status, test message, and seller-chat broadcast logic."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram_service: TelegramService | None = None,
        notifications_service: NotificationsService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.session = session
        self.repository = SellerBotRepository(session)
        self.products_repository = ProductsRepository(session)
        self.variants_repository = ProductVariantsRepository(session)
        self.categories_repository = CategoriesRepository(session)
        self.tags_repository = TagsRepository(session)
        self.telegram_service = telegram_service or TelegramService()
        self.storage = LocalStorageService()
        self.notifications_service = notifications_service or NotificationsService(
            session,
            telegram_service=self.telegram_service,
        )
        self.audit_service = audit_service or AuditService(session)

    async def get_status(self) -> SellerBotStatusResponse:
        configured = bool(settings.telegram_bot_token)
        seller_chat_configured = bool(settings.telegram_seller_chat_id)
        if not configured:
            return SellerBotStatusResponse(
                configured=False,
                seller_chat_configured=seller_chat_configured,
                ok=False,
                error="Telegram bot token is not configured",
            )

        try:
            bot = await self.telegram_service.get_me()
        except TelegramDeliveryError as exc:
            return SellerBotStatusResponse(
                configured=True,
                seller_chat_configured=seller_chat_configured,
                ok=False,
                error=str(exc),
            )

        return SellerBotStatusResponse(
            configured=True,
            seller_chat_configured=seller_chat_configured,
            ok=True,
            bot=bot,
        )

    async def send_test_message(
        self,
        *,
        payload: SellerBotMessageRequest,
        actor_user_id: int,
    ) -> SellerBotActionResponse:
        notification = await self.notifications_service.send_seller_telegram_message(
            type=SELLER_BOT_TEST_MESSAGE,
            title="Seller bot test message",
            message=payload.message,
            payload={"target": "seller_notification_chat"},
        )
        await self._audit(
            actor_user_id=actor_user_id,
            action=SELLER_BOT_TEST_MESSAGE,
            notification_id=notification.id,
            message_length=len(payload.message),
        )
        return SellerBotActionResponse(
            notification_id=notification.id,
            status=notification.status.value,
            message=notification.message,
        )

    async def broadcast(
        self,
        *,
        payload: SellerBotBroadcastRequest,
        actor_user_id: int,
    ) -> SellerBotActionResponse:
        notification = await self.notifications_service.send_seller_telegram_message(
            type=SELLER_BOT_BROADCAST,
            title="Seller notification chat broadcast",
            message=payload.message,
            payload={"target": "seller_notification_chat"},
        )
        await self._audit(
            actor_user_id=actor_user_id,
            action=SELLER_BOT_BROADCAST,
            notification_id=notification.id,
            message_length=len(payload.message),
        )
        return SellerBotActionResponse(
            notification_id=notification.id,
            status=notification.status.value,
            message=notification.message,
        )

    async def list_messages(self, *, limit: int, offset: int) -> NotificationList:
        return await self.notifications_service.list_notifications(
            limit=limit,
            offset=offset,
            channel=NotificationChannel.TELEGRAM,
        )

    async def format_sellers_command(self, *, chat_id: int) -> str:
        self._require_seller_group(chat_id)
        sellers, total = await self.repository.list_sellers(limit=SELLER_BOT_COMMAND_LIMIT)
        if not sellers:
            return "No sellers found."

        lines = [f"Sellers ({len(sellers)} of {total}):"]
        for user, credential in sellers:
            username = f"@{credential.telegram_username}" if credential.telegram_username else "-"
            telegram_user_id = (
                str(credential.telegram_user_id)
                if credential.telegram_user_id is not None
                else "-"
            )
            telegram_chat_id = (
                str(credential.telegram_chat_id)
                if credential.telegram_chat_id is not None
                else "-"
            )
            active_status = "active" if user.is_active else "blocked"
            lines.append(
                "\n".join(
                    (
                        f"Seller ID for commands: {user.id}",
                        f"Email: {credential.email}",
                        f"Telegram: {username}",
                        f"Telegram user/chat: {telegram_user_id} / {telegram_chat_id}",
                        f"Role: {user.role.value}",
                        f"Status: {active_status}",
                        f"Created at: {user.created_at.isoformat()}",
                    )
                )
            )
        if total > len(sellers):
            lines.append(f"Showing first {len(sellers)} sellers. Use the API for full history.")
        lines.append(
            "\n".join(
                (
                    "Use /block_seller <Seller ID>, for example: /block_seller 5",
                    "Do not use Telegram user id/chat id.",
                )
            )
        )
        return "\n\n".join(lines)

    async def block_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        return await self._set_seller_active_state(
            chat_id=chat_id,
            target_user_id=target_user_id,
            is_active=False,
            actor_telegram_user_id=actor_telegram_user_id,
            actor_username=actor_username,
        )

    async def unblock_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        return await self._set_seller_active_state(
            chat_id=chat_id,
            target_user_id=target_user_id,
            is_active=True,
            actor_telegram_user_id=actor_telegram_user_id,
            actor_username=actor_username,
        )

    async def create_quick_product_draft_command(
        self,
        *,
        chat_id: int,
        message: TelegramMessage,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self._require_seller_group(chat_id)
        try:
            draft = self._parse_quick_product_message(message)
            photo = self._select_largest_photo(message.photo)
            if message.media_group_id:
                raise AppError(
                    "Media groups are not supported yet. Send one photo with /new_product in "
                    "the caption.",
                    400,
                )
            if photo is None:
                raise AppError(
                    "Attach one product photo and put /new_product fields in the caption.",
                    400,
                )
        except AppError as exc:
            await self._audit_product_post_rejected(
                actor_telegram_user_id=actor_telegram_user_id,
                actor_username=actor_username,
                reason=exc.message,
            )
            raise

        saved_paths: list[str] = []
        warnings: list[str] = []
        try:
            category_id = await self._resolve_quick_product_category(draft, warnings)
            tags = await self._resolve_quick_product_tags(draft, warnings)
            image = await self._store_quick_product_photo(photo, title=draft.title)
            saved_paths.append(image.file_path)
            product = Product(
                name=draft.title,
                slug=self._quick_product_slug(draft.title),
                description=draft.description,
                base_price=draft.price,
                old_price=draft.old_price,
                search_priority=draft.search_priority,
                search_aliases=draft.search_aliases,
                status=ProductStatus.DRAFT,
                category_id=category_id,
                tags=tags,
                images=[image],
            )
            self.products_repository.add(product)
            await self.session.flush()
            for variant in self._build_quick_product_variants(product.id, draft):
                self.variants_repository.add(variant)

            await self.audit_service.record_action(
                actor_user_id=None,
                action=SELLER_BOT_PRODUCT_DRAFT_CREATED,
                entity_type="product",
                entity_id=product.id,
                after_data={
                    "id": product.id,
                    "name": product.name,
                    "status": product.status.value,
                    "image_count": len(product.images),
                },
                metadata={
                    "actor_telegram_user_id": actor_telegram_user_id,
                    "actor_username": actor_username,
                    "source": "seller_bot_new_product",
                    "warnings": warnings,
                },
                commit=False,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            for file_path in saved_paths:
                self.storage.delete(file_path)
            await self._audit_product_post_rejected(
                actor_telegram_user_id=actor_telegram_user_id,
                actor_username=actor_username,
                reason="Product slug or variant SKU already exists",
            )
            raise AppError("Product slug or variant SKU already exists", 409) from exc
        except Exception:
            await self.session.rollback()
            for file_path in saved_paths:
                self.storage.delete(file_path)
            raise

        return self._quick_product_confirmation(
            product_id=product.id,
            draft=draft,
            warnings=warnings,
        )

    def _parse_quick_product_message(self, message: TelegramMessage) -> QuickProductDraft:
        text = (message.text or message.caption or "").strip()
        if not text:
            raise AppError("Use /new_product with strict field lines in the message caption.", 400)
        lines = text.splitlines()
        if not lines or not lines[0].strip().lower().startswith("/new_product"):
            raise AppError("Product draft message must start with /new_product.", 400)

        values: dict[str, str] = {}
        for raw_line in lines[1:]:
            line = raw_line.strip()
            if not line:
                continue
            if ":" not in line:
                raise AppError(f"Invalid product field line: {line}", 400)
            raw_label, raw_value = line.split(":", 1)
            label = raw_label.strip()
            value = raw_value.strip()
            field = QUICK_PRODUCT_ALLOWED_FIELDS.get(label)
            if field is None:
                allowed = ", ".join(QUICK_PRODUCT_ALLOWED_FIELDS)
                raise AppError(f"Unknown field: {label}. Allowed fields: {allowed}.", 400)
            if field in values:
                raise AppError(f"Duplicate field: {label}", 400)
            values[field] = value

        title = self._required_text(values, "title", "Название")
        price = self._parse_money(self._required_text(values, "price", "Цена"), field="Цена")
        old_price = self._parse_optional_money(values.get("old_price"), field="Старая цена")
        if old_price is not None and old_price <= price:
            raise AppError("Старая цена must be greater than Цена.", 400)

        search_priority = self._parse_int(
            values.get("search_priority") or "2",
            field="Приоритет поиска",
            minimum=1,
            maximum=3,
        )
        stock = None
        if values.get("stock"):
            stock = self._parse_int(values["stock"], field="Остаток", minimum=0)

        status_value = (values.get("status") or ProductStatus.DRAFT.value).strip().upper()
        if status_value != ProductStatus.DRAFT.value:
            raise AppError("Статус can only be DRAFT for Bot 2 quick product posts.", 400)

        return QuickProductDraft(
            title=title,
            price=price,
            old_price=old_price,
            description=self._optional_text(values.get("description")),
            category=self._optional_text(values.get("category")),
            tags=self._split_csv(values.get("tags")),
            sizes=self._split_csv(values.get("sizes")),
            color=self._optional_text(values.get("color")),
            sku=self._optional_text(values.get("sku")),
            stock=stock,
            search_priority=search_priority,
            search_aliases=normalize_search_aliases(values.get("search_aliases")),
            status=ProductStatus.DRAFT,
        )

    async def _resolve_quick_product_category(
        self,
        draft: QuickProductDraft,
        warnings: list[str],
    ) -> int | None:
        if draft.category is None:
            return None
        category = await self.categories_repository.get_by_name_or_slug(draft.category)
        if category is None:
            warnings.append(f"Category ignored: {draft.category}")
            return None
        return category.id

    async def _resolve_quick_product_tags(
        self,
        draft: QuickProductDraft,
        warnings: list[str],
    ) -> list:
        if not draft.tags:
            return []
        tags = await self.tags_repository.list_by_names_or_slugs(draft.tags)
        found_names = {tag.name.strip().lower() for tag in tags}
        found_slugs = {tag.slug.strip().lower() for tag in tags}
        missing = [
            tag
            for tag in draft.tags
            if tag.strip().lower() not in found_names and tag.strip().lower() not in found_slugs
        ]
        if missing:
            warnings.append(f"Tags ignored: {', '.join(missing)}")
        return tags

    async def _store_quick_product_photo(
        self,
        photo: TelegramPhotoSize,
        *,
        title: str,
    ) -> ProductImage:
        downloaded = await self.telegram_service.download_file(photo.file_id)
        file_path = self.storage.save_bytes(
            downloaded.content,
            folder="products",
            suffix=downloaded.extension,
        )
        return ProductImage(
            file_path=file_path,
            original_filename=downloaded.original_filename,
            mime_type=downloaded.mime_type,
            size_bytes=len(downloaded.content),
            alt_text=title[:255],
            position=0,
            is_primary=True,
        )

    def _build_quick_product_variants(
        self,
        product_id: int,
        draft: QuickProductDraft,
    ) -> list[ProductVariant]:
        has_variant_data = bool(draft.sizes or draft.color or draft.sku or draft.stock is not None)
        if not has_variant_data:
            return []

        sizes = draft.sizes or [QUICK_PRODUCT_SIZE_DEFAULT]
        stock = draft.stock if draft.stock is not None else 0
        return [
            ProductVariant(
                product_id=product_id,
                size=size,
                color=draft.color,
                sku=self._variant_sku(draft, size=size, index=index, multiple=len(sizes) > 1),
                stock_quantity=stock,
                reserved_quantity=0,
                is_active=True,
            )
            for index, size in enumerate(sizes, start=1)
        ]

    def _variant_sku(
        self,
        draft: QuickProductDraft,
        *,
        size: str,
        index: int,
        multiple: bool,
    ) -> str:
        if draft.sku:
            return f"{draft.sku}-{self._sku_part(size)}"[:100] if multiple else draft.sku[:100]
        base = self._sku_part(draft.title) or "BOT"
        suffix = self._sku_part(size) if multiple else str(index)
        return f"BOT-{base[:40]}-{suffix}-{token_hex(3).upper()}"[:100]

    def _quick_product_confirmation(
        self,
        *,
        product_id: int,
        draft: QuickProductDraft,
        warnings: list[str],
    ) -> str:
        lines = [
            "Product draft created.",
            f"Product ID: {product_id}",
            f"Title: {draft.title}",
            f"Status: {draft.status.value}",
            f"Seller Panel: {SELLER_PANEL_PRODUCT_EDIT_URL.format(product_id=product_id)}",
        ]
        if warnings:
            lines.append(f"Warnings: {'; '.join(warnings)}")
        return "\n".join(lines)

    async def _audit_product_post_rejected(
        self,
        *,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
        reason: str,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=None,
            action=SELLER_BOT_PRODUCT_POST_REJECTED,
            entity_type="seller_bot",
            before_data=None,
            after_data={"accepted": False},
            metadata={
                "actor_telegram_user_id": actor_telegram_user_id,
                "actor_username": actor_username,
                "reason": reason,
                "source": "seller_bot_new_product",
            },
            commit=True,
        )

    def _select_largest_photo(
        self,
        photos: list[TelegramPhotoSize] | None,
    ) -> TelegramPhotoSize | None:
        if not photos:
            return None
        return max(photos, key=lambda photo: (photo.file_size or 0, photo.width * photo.height))

    def _required_text(self, values: dict[str, str], field: str, label: str) -> str:
        value = self._optional_text(values.get(field))
        if value is None:
            raise AppError(f"Missing required field: {label}", 400)
        return value

    def _optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = " ".join(value.split())
        return stripped or None

    def _parse_money(self, value: str, *, field: str) -> Decimal:
        try:
            money = Decimal(value.replace(",", "."))
        except InvalidOperation as exc:
            raise AppError(f"{field} must be a valid price.", 400) from exc
        if money <= 0:
            raise AppError(f"{field} must be greater than 0.", 400)
        return money.quantize(Decimal("0.01"))

    def _parse_optional_money(self, value: str | None, *, field: str) -> Decimal | None:
        value = self._optional_text(value)
        if value is None:
            return None
        return self._parse_money(value, field=field)

    def _parse_int(
        self,
        value: str,
        *,
        field: str,
        minimum: int,
        maximum: int | None = None,
    ) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise AppError(f"{field} must be an integer.", 400) from exc
        if parsed < minimum:
            raise AppError(f"{field} must be at least {minimum}.", 400)
        if maximum is not None and parsed > maximum:
            raise AppError(f"{field} must be between {minimum} and {maximum}.", 400)
        return parsed

    def _split_csv(self, value: str | None) -> list[str]:
        if value is None:
            return []
        return [part for part in (self._optional_text(part) for part in value.split(",")) if part]

    def _quick_product_slug(self, title: str) -> str:
        ascii_title = (
            unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
        )
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
        return f"{slug or 'telegram-product'}-{token_hex(4)}"[:255]

    def _sku_part(self, value: str) -> str:
        ascii_value = (
            unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        )
        return re.sub(r"[^A-Z0-9]+", "-", ascii_value.upper()).strip("-")

    async def _audit(
        self,
        *,
        actor_user_id: int,
        action: str,
        notification_id: int,
        message_length: int,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action=action,
            entity_type="seller_bot",
            entity_id=notification_id,
            after_data={
                "notification_id": notification_id,
                "target": "seller_notification_chat",
                "message_length": message_length,
            },
            commit=True,
        )

    async def _set_seller_active_state(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        is_active: bool,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self._require_seller_group(chat_id)
        if not 1 <= target_user_id <= POSTGRES_INT32_MAX:
            raise AppError(
                "Seller ID is outside the supported range. Get Seller ID with /sellers.",
                400,
            )
        user = await self.repository.get_seller_user(target_user_id)
        if user is None:
            raise AppError("Seller not found. Check Seller ID with /sellers.", 404)
        if user.role == UserRole.ADMIN and not is_active:
            raise AppError("ADMIN users cannot be blocked from Bot 2", 400)
        if user.is_active == is_active:
            state = "active" if is_active else "blocked"
            return f"Seller #{user.id} is already {state}."

        before_data = {
            "id": user.id,
            "role": user.role.value,
            "is_active": user.is_active,
        }
        user.is_active = is_active
        action = SELLER_BOT_UNBLOCK_SELLER if is_active else SELLER_BOT_BLOCK_SELLER
        await self.audit_service.record_action(
            actor_user_id=None,
            action=action,
            entity_type="user",
            entity_id=user.id,
            before_data=before_data,
            after_data={
                "id": user.id,
                "role": user.role.value,
                "is_active": user.is_active,
            },
            metadata={
                "actor_telegram_user_id": actor_telegram_user_id,
                "actor_username": actor_username,
                "source": "seller_bot_command",
            },
            commit=False,
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Seller active state update failed", 409) from exc

        state = "unblocked" if is_active else "blocked"
        return f"Seller #{user.id} has been {state}."

    def _require_seller_group(self, chat_id: int) -> None:
        configured_chat_id = settings.telegram_seller_chat_id
        if not configured_chat_id or str(chat_id) != configured_chat_id.strip():
            raise AppError(SELLER_GROUP_ONLY_MESSAGE, 403)
