import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from secrets import token_hex

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    NotificationChannel,
    ProductSizeGrid,
    ProductStatus,
    UserRole,
)
from app.modules.audit.service import AuditService
from app.modules.categories.repository import CategoriesRepository
from app.modules.notifications.schemas import NotificationList
from app.modules.notifications.service import NotificationsService
from app.modules.products.schemas import (
    ProductCategoryInput,
    ProductCreate,
    ProductImageCreate,
    ProductVariantCreate,
)
from app.modules.products.search import normalize_search_aliases
from app.modules.products.service import ProductsService
from app.modules.products.size_grids import SizeGridValidationError, normalize_size
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
QUICK_PRODUCT_ALLOWED_FIELDS = {
    "название": "title",
    "цена": "price",
    "старая цена": "old_price",
    "описание": "description",
    "категория": "categories",
    "категории": "categories",
    "теги": "tags",
    "тип размеров": "size_grid",
    "size_grid": "size_grid",
    "размеры": "variants",
    "приоритет поиска": "search_priority",
    "псевдонимы поиска": "search_aliases",
    "ключевые слова": "search_aliases",
    "статус": "status",
}
QUICK_PRODUCT_SIZE_GRID_ALIASES = {
    "одежда": ProductSizeGrid.CLOTHING_ALPHA,
    ProductSizeGrid.CLOTHING_ALPHA.value: ProductSizeGrid.CLOTHING_ALPHA,
    "обувь": ProductSizeGrid.SHOES_RU,
    ProductSizeGrid.SHOES_RU.value: ProductSizeGrid.SHOES_RU,
}
QUICK_PRODUCT_STATUS_ALIASES = {
    "черновик": ProductStatus.DRAFT,
    ProductStatus.DRAFT.value.lower(): ProductStatus.DRAFT,
    "активен": ProductStatus.ACTIVE,
    "активный": ProductStatus.ACTIVE,
    ProductStatus.ACTIVE.value.lower(): ProductStatus.ACTIVE,
}


@dataclass(frozen=True)
class QuickProductVariantDraft:
    size: str
    color: str | None
    stock: int
    sku: str | None


@dataclass(frozen=True)
class QuickProductImageDraft:
    payload: ProductImageCreate
    original_filename: str
    mime_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class QuickProductDraft:
    title: str
    price: Decimal
    old_price: Decimal | None
    description: str | None
    categories: list[str]
    tags: list[str]
    size_grid: ProductSizeGrid
    variants: list[QuickProductVariantDraft]
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
        self.categories_repository = CategoriesRepository(session)
        self.tags_repository = TagsRepository(session)
        self.telegram_service = telegram_service or TelegramService()
        self.storage = LocalStorageService()
        self.notifications_service = notifications_service or NotificationsService(
            session,
            telegram_service=self.telegram_service,
        )
        self.audit_service = audit_service or AuditService(session)
        self.products_service = ProductsService(
            session,
            audit_service=self.audit_service,
        )

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
        saved_paths: list[str] = []
        try:
            draft = self._parse_quick_product_message(message)
            photo = self._select_largest_photo(message.photo)
            if message.media_group_id:
                raise AppError(
                    "медиагруппы пока не поддерживаются. Отправь одну фотографию с подписью "
                    "/new_product.",
                    400,
                )
            if photo is None:
                raise AppError(
                    "поле `Фото` обязательно. Отправь одну фотографию товара с форматом "
                    "/new_product в подписи.",
                    400,
                )

            categories = await self._resolve_quick_product_categories(draft)
            tags = await self._resolve_quick_product_tags(draft)
            image = await self._store_quick_product_photo(photo, title=draft.title)
            saved_paths.append(image.payload.file_path)
            product_payload = ProductCreate(
                name=draft.title,
                slug=self._quick_product_slug(draft.title),
                description=draft.description,
                base_price=draft.price,
                old_price=draft.old_price,
                search_priority=draft.search_priority,
                search_aliases=draft.search_aliases,
                size_grid=draft.size_grid,
                status=draft.status,
                categories=categories,
                tag_ids=[tag.id for tag in tags],
                images=[image.payload],
            )
            variant_payloads = self._build_quick_product_variant_payloads(draft)
            product = await self.products_service.stage_product_with_variants(
                product_payload,
                variant_payloads,
            )
            product.images[0].original_filename = image.original_filename
            product.images[0].mime_type = image.mime_type
            product.images[0].size_bytes = image.size_bytes

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
                    "size_grid": draft.size_grid.value,
                    "variant_count": len(variant_payloads),
                },
                commit=False,
            )
            await self.session.commit()
        except ValidationError as exc:
            await self.session.rollback()
            for file_path in saved_paths:
                self.storage.delete(file_path)
            error = AppError(self._format_product_validation_error(exc), 400)
            await self._audit_product_post_rejected(
                actor_telegram_user_id=actor_telegram_user_id,
                actor_username=actor_username,
                reason=error.message,
            )
            raise error from exc
        except AppError as exc:
            await self.session.rollback()
            for file_path in saved_paths:
                self.storage.delete(file_path)
            await self._audit_product_post_rejected(
                actor_telegram_user_id=actor_telegram_user_id,
                actor_username=actor_username,
                reason=exc.message,
            )
            raise
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
        )

    def format_new_product_help_command(self, *, chat_id: int) -> str:
        self._require_seller_group(chat_id)
        return self._new_product_help_text()

    def _parse_quick_product_message(self, message: TelegramMessage) -> QuickProductDraft:
        text = (message.text or message.caption or "").strip()
        if not text:
            raise AppError(
                "подпись пуста. Добавь /new_product и поля товара в подпись к фото.",
                400,
            )
        lines = text.splitlines()
        command = lines[0].strip().split(maxsplit=1)[0].lower()
        if re.fullmatch(r"/new_product(?:@[a-z0-9_]+)?", command) is None:
            raise AppError("первая строка должна быть `/new_product`.", 400)

        values: dict[str, str] = {}
        variant_rows: list[str] = []
        current_block: str | None = None
        for raw_line in lines[1:]:
            line = raw_line.strip()
            if not line:
                continue
            field: str | None = None
            label = ""
            value = ""
            if ":" in line:
                raw_label, raw_value = line.split(":", 1)
                label = " ".join(raw_label.split())
                value = raw_value.strip()
                field = QUICK_PRODUCT_ALLOWED_FIELDS.get(label.casefold())

            if field is not None:
                if field in values:
                    raise AppError(f"поле `{label}` указано больше одного раза.", 400)
                values[field] = value
                current_block = field if field == "variants" else None
                if field == "variants" and value:
                    variant_rows.append(value)
                continue

            if current_block == "variants" and (":" not in line or "/" in line):
                variant_rows.append(line)
                continue

            if ":" in line:
                raise AppError(
                    f"неизвестное поле `{label}`. Открой /new_product_help для списка полей.",
                    400,
                )
            raise AppError(
                f"строка `{line}` не относится к полю. Формат поля: `Название: ...`.",
                400,
            )

        title = self._required_text(values, "title", "Название")
        price = self._parse_money(self._required_text(values, "price", "Цена"), field="Цена")
        old_price = self._parse_optional_money(values.get("old_price"), field="Старая цена")
        if old_price is not None and old_price <= price:
            raise AppError(
                "поле `Старая цена` должно быть больше поля `Цена`. "
                "Пример: `Цена: 4990`, `Старая цена: 6990`.",
                400,
            )

        size_grid = self._parse_size_grid(
            self._required_text(values, "size_grid", "Тип размеров"),
        )
        if not variant_rows:
            raise AppError(
                "поле `Размеры` обязательно. Добавь хотя бы строку "
                "`M / White / 10 / HERMES-M-W`.",
                400,
            )

        search_priority = self._parse_int(
            values.get("search_priority") or "2",
            field="Приоритет поиска",
            minimum=1,
            maximum=3,
        )
        status_value = self._optional_text(values.get("status")) or "черновик"
        status = QUICK_PRODUCT_STATUS_ALIASES.get(status_value.casefold())
        if status is None:
            raise AppError(
                "поле `Статус` должно быть `черновик` или `активен`.",
                400,
            )

        return QuickProductDraft(
            title=title,
            price=price,
            old_price=old_price,
            description=self._optional_text(values.get("description")),
            categories=self._split_csv(values.get("categories")),
            tags=self._split_csv(values.get("tags")),
            size_grid=size_grid,
            variants=self._parse_quick_product_variants(variant_rows, size_grid=size_grid),
            search_priority=search_priority,
            search_aliases=normalize_search_aliases(values.get("search_aliases")),
            status=status,
        )

    def _parse_size_grid(self, value: str) -> ProductSizeGrid:
        size_grid = QUICK_PRODUCT_SIZE_GRID_ALIASES.get(value.strip().casefold())
        if size_grid is None:
            raise AppError(
                "поле `Тип размеров` должно быть `одежда`, `обувь`, "
                "`clothing_alpha` или `shoes_ru`.",
                400,
            )
        return size_grid

    def _parse_quick_product_variants(
        self,
        rows: list[str],
        *,
        size_grid: ProductSizeGrid,
    ) -> list[QuickProductVariantDraft]:
        variants: list[QuickProductVariantDraft] = []
        combinations: set[tuple[str, str | None]] = set()
        skus: set[str] = set()
        for index, row in enumerate(rows, start=1):
            parts = [part.strip() for part in row.split("/")]
            if len(parts) not in {3, 4}:
                raise AppError(
                    f"строка {index} поля `Размеры` имеет неверный формат: `{row}`. "
                    "Используй `размер / цвет / остаток / SKU`; SKU можно оставить пустым.",
                    400,
                )
            raw_size, raw_color, raw_stock = parts[:3]
            raw_sku = parts[3] if len(parts) == 4 else ""
            if not raw_size:
                raise AppError(f"строка {index}: размер не указан.", 400)
            try:
                size = normalize_size(size_grid, raw_size)
            except SizeGridValidationError as exc:
                raise AppError(self._invalid_size_message(size_grid, raw_size), 400) from exc

            color = self._optional_text(raw_color)
            stock = self._parse_int(
                raw_stock,
                field=f"Остаток в строке {index} поля Размеры",
                minimum=0,
            )
            sku = self._optional_text(raw_sku)
            combination = (size, color.casefold() if color else None)
            if combination in combinations:
                color_label = color or "без цвета"
                raise AppError(
                    f"дубликат комбинации размера `{size}` и цвета `{color_label}`.",
                    400,
                )
            combinations.add(combination)
            if sku:
                normalized_sku = sku.casefold()
                if normalized_sku in skus:
                    raise AppError(f"SKU `{sku}` указан больше одного раза.", 400)
                skus.add(normalized_sku)
            variants.append(
                QuickProductVariantDraft(
                    size=size,
                    color=color,
                    stock=stock,
                    sku=sku,
                )
            )
        return variants

    def _invalid_size_message(self, size_grid: ProductSizeGrid, value: str) -> str:
        if size_grid == ProductSizeGrid.SHOES_RU:
            prefix_match = re.fullmatch(r"(?:RU|EU|US|UK)\s*(\d+)", value, re.IGNORECASE)
            if prefix_match and 35 <= int(prefix_match.group(1)) <= 46:
                return (
                    f"размер `{value}` недопустим для обуви. Используй российский размер без "
                    f"префикса: `{prefix_match.group(1)}`. Разрешены размеры обуви: "
                    "35, 36, ..., 46."
                )
            if "." in value or "," in value:
                return (
                    f"размер `{value}` недопустим для обуви: половинные размеры не "
                    "поддерживаются. Разрешены целые российские размеры 35-46."
                )
            return (
                f"размер `{value}` недопустим для обуви. Разрешены только российские "
                "целые размеры: 35, 36, ..., 46."
            )
        return (
            f"размер `{value}` недопустим для одежды. Разрешены размеры: "
            "XS, S, M, L, XL, XXL, 3XL, ONE_SIZE."
        )

    async def _resolve_quick_product_categories(
        self,
        draft: QuickProductDraft,
    ) -> list[ProductCategoryInput]:
        if len(draft.categories) > 3:
            raise AppError("поле `Категории` поддерживает не более трех категорий.", 400)
        assignments: list[ProductCategoryInput] = []
        category_ids: set[int] = set()
        for priority, value in enumerate(draft.categories, start=1):
            category = await self.categories_repository.get_by_name_or_slug(value)
            if category is None:
                raise AppError(
                    f"категория `{value}` не найдена. Сначала создай ее в Seller Panel "
                    "или укажи существующее название.",
                    400,
                )
            if category.id in category_ids:
                raise AppError(f"категория `{value}` указана больше одного раза.", 400)
            category_ids.add(category.id)
            assignments.append(ProductCategoryInput(category_id=category.id, priority=priority))
        return assignments

    async def _resolve_quick_product_tags(
        self,
        draft: QuickProductDraft,
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
            raise AppError(
                f"теги не найдены: {', '.join(f'`{tag}`' for tag in missing)}. "
                "Сначала создай их в Seller Panel или укажи существующие теги.",
                400,
            )
        return tags

    async def _store_quick_product_photo(
        self,
        photo: TelegramPhotoSize,
        *,
        title: str,
    ) -> QuickProductImageDraft:
        downloaded = await self.telegram_service.download_file(photo.file_id)
        file_path = self.storage.save_bytes(
            downloaded.content,
            folder="products",
            suffix=downloaded.extension,
        )
        return QuickProductImageDraft(
            payload=ProductImageCreate(
                file_path=file_path,
                alt_text=title[:255],
                position=0,
                is_primary=True,
            ),
            original_filename=downloaded.original_filename,
            mime_type=downloaded.mime_type,
            size_bytes=len(downloaded.content),
        )

    def _build_quick_product_variant_payloads(
        self,
        draft: QuickProductDraft,
    ) -> list[ProductVariantCreate]:
        return [
            ProductVariantCreate(
                size=variant.size,
                color=variant.color,
                sku=variant.sku or self._variant_sku(draft, variant=variant, index=index),
                stock_quantity=variant.stock,
                reserved_quantity=0,
                is_active=True,
            )
            for index, variant in enumerate(draft.variants, start=1)
        ]

    def _variant_sku(
        self,
        draft: QuickProductDraft,
        *,
        variant: QuickProductVariantDraft,
        index: int,
    ) -> str:
        base = self._sku_part(draft.title) or "BOT"
        size = self._sku_part(variant.size) or str(index)
        color = self._sku_part(variant.color or "")[:16]
        detail = "-".join(part for part in (size, color) if part)
        return f"BOT-{base[:40]}-{detail}-{token_hex(3).upper()}"[:100]

    def _quick_product_confirmation(
        self,
        *,
        product_id: int,
        draft: QuickProductDraft,
    ) -> str:
        return "\n".join(
            (
                "Товар создан.",
                f"ID товара: {product_id}",
                f"Название: {draft.title}",
                f"Статус: {draft.status.value}",
                f"Тип размеров: {draft.size_grid.value}",
                f"Вариантов: {len(draft.variants)}",
                f"Редактировать: {SELLER_PANEL_PRODUCT_EDIT_URL.format(product_id=product_id)}",
            )
        )

    def _new_product_help_text(self) -> str:
        return """Создание товара: отправь одну фотографию с подписью в строгом формате.

Одежда:
/new_product

Название: Футболка HERMES
Описание: Бюджетные футболки, весна/лето
Цена: 700
Старая цена:
Категории: Футболки
Теги: футболка, hermes
Тип размеров: одежда
Размеры:
M / White / 10 / HERMES-M-W
L / White / 8 / HERMES-L-W
XL / Black / 5 / HERMES-XL-B
3XL / Black / 3 / HERMES-3XL-B
Псевдонимы поиска: футболка, фудболка, футбалка
Статус: черновик

Обувь:
/new_product

Название: Кроссовки Nike Air Max
Описание: Лёгкие кроссовки, качество люкс
Цена: 4990
Старая цена: 6990
Категории: Обувь
Теги: кроссовки, nike, premium
Тип размеров: обувь
Размеры:
39 / White / 3 / SKU-NIKE-39-W
40 / White / 2 / SKU-NIKE-40-W
41 / Black / 4 / SKU-NIKE-41-B
Псевдонимы поиска: найк, кросовки, кроссовки
Статус: черновик

Формат варианта: размер / цвет / остаток / SKU.
SKU можно оставить пустым, тогда Bot 2 создаст безопасное значение.

Размеры одежды: XS, S, M, L, XL, XXL, 3XL, ONE_SIZE.
Размеры обуви: только российские целые размеры 35-46 без префикса.
RU/EU/US/UK и половинные размеры не поддерживаются.

Категории и теги должны уже существовать.
По умолчанию товар создаётся как черновик; его можно отредактировать в Seller Panel."""

    def _format_product_validation_error(self, exc: ValidationError) -> str:
        error = exc.errors(include_url=False)[0]
        field = str(error.get("loc", ("товар",))[-1])
        labels = {
            "name": "Название",
            "base_price": "Цена",
            "old_price": "Старая цена",
            "search_aliases": "Псевдонимы поиска",
            "size": "Размеры",
            "color": "Цвет",
            "sku": "SKU",
            "stock_quantity": "Остаток",
        }
        return f"поле `{labels.get(field, field)}` не прошло проверку: {error['msg']}."

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
            raise AppError(
                f"обязательное поле `{label}` не заполнено. Пример: `{label}: значение`.",
                400,
            )
        return value

    def _optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = " ".join(value.split())
        return stripped or None

    def _parse_money(self, value: str, *, field: str) -> Decimal:
        try:
            money = Decimal(value.replace(",", "."))
            if not money.is_finite() or money <= 0:
                raise InvalidOperation
            return money.quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise AppError(
                f"поле `{field}` должно быть положительным числом. Пример: `{field}: 4990`.",
                400,
            ) from exc

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
            raise AppError(f"поле `{field}` должно быть целым числом.", 400) from exc
        if parsed < minimum:
            raise AppError(f"поле `{field}` должно быть не меньше {minimum}.", 400)
        if maximum is not None and parsed > maximum:
            raise AppError(f"поле `{field}` должно быть от {minimum} до {maximum}.", 400)
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
