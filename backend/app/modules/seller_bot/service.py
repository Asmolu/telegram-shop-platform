import html
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from secrets import token_hex

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.labels import (
    MISSING_VALUE,
    delivery_method_label,
    format_datetime_moscow,
    format_rubles,
    order_status_label,
    payment_status_label,
)
from app.core.config import join_public_url, settings
from app.core.errors import AppError
from app.db.models import (
    NotificationChannel,
    OrderStatus,
    ProductImageBadgeColor,
    ProductImageBadgePosition,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductStatus,
    UserRole,
)
from app.modules.audit.service import AuditService
from app.modules.categories.repository import CategoriesRepository
from app.modules.notifications.schemas import NotificationList
from app.modules.notifications.service import NotificationsService
from app.modules.orders.schemas import OrderStatusUpdate
from app.modules.orders.service import OrdersService
from app.modules.products.schemas import (
    ProductCategoryInput,
    ProductCreate,
    ProductImageCreate,
    ProductVariantCreate,
)
from app.modules.products.search import normalize_search_aliases
from app.modules.products.service import ProductsService
from app.modules.products.size_grids import (
    SHOES_EU_SIZES,
    SizeGridValidationError,
    format_size_for_display,
    normalize_size,
)
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
ACTIVE_ORDERS_COMMAND_LIMIT = 10
CHETAM_COMMAND_LIMIT = 20
TELEGRAM_MESSAGE_LIMIT = 4096
SELLER_GROUP_ONLY_MESSAGE = "Command is available only in the seller group."
POSTGRES_INT32_MAX = 2_147_483_647
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
    "похожие товары": "related_product_ids",
    "похожие": "related_product_ids",
    "related products": "related_product_ids",
    "related_product_ids": "related_product_ids",
    "виджет фото": "image_badge_type",
    "бейдж фото": "image_badge_type",
    "бейдж": "image_badge_type",
    "image_badge": "image_badge_type",
    "текст виджета фото": "image_badge_text",
    "текст бейджа": "image_badge_text",
    "badge_text": "image_badge_text",
    "image_badge_text": "image_badge_text",
    "цвет виджета фото": "image_badge_color",
    "цвет бейджа": "image_badge_color",
    "badge_color": "image_badge_color",
    "image_badge_color": "image_badge_color",
    "положение виджета фото": "image_badge_position",
    "положение бейджа": "image_badge_position",
    "badge_position": "image_badge_position",
    "image_badge_position": "image_badge_position",
    "приоритет поиска": "search_priority",
    "псевдонимы поиска": "search_aliases",
    "ключевые слова": "search_aliases",
    "статус": "status",
}
QUICK_PRODUCT_SIZE_GRID_ALIASES = {
    "одежда": ProductSizeGrid.CLOTHING_ALPHA,
    ProductSizeGrid.CLOTHING_ALPHA.value: ProductSizeGrid.CLOTHING_ALPHA,
    "обувь": ProductSizeGrid.SHOES_EU,
    "eu": ProductSizeGrid.SHOES_EU,
    ProductSizeGrid.SHOES_EU.value: ProductSizeGrid.SHOES_EU,
}
QUICK_PRODUCT_STATUS_ALIASES = {
    "черновик": ProductStatus.DRAFT,
    ProductStatus.DRAFT.value.lower(): ProductStatus.DRAFT,
    "активен": ProductStatus.ACTIVE,
    "активный": ProductStatus.ACTIVE,
    ProductStatus.ACTIVE.value.lower(): ProductStatus.ACTIVE,
}
QUICK_PRODUCT_BADGE_ALIASES = {
    "": ProductImageBadgeType.NONE,
    "нет": ProductImageBadgeType.NONE,
    "none": ProductImageBadgeType.NONE,
    "new": ProductImageBadgeType.NEW,
    "новинка": ProductImageBadgeType.NEW,
    "распродажа": ProductImageBadgeType.SALE,
    "sale": ProductImageBadgeType.SALE,
    "хит": ProductImageBadgeType.HIT,
    "hit": ProductImageBadgeType.HIT,
    "эксклюзив": ProductImageBadgeType.EXCLUSIVE,
    "exclusive": ProductImageBadgeType.EXCLUSIVE,
    "custom": ProductImageBadgeType.CUSTOM,
    "свой": ProductImageBadgeType.CUSTOM,
    "кастом": ProductImageBadgeType.CUSTOM,
}
QUICK_PRODUCT_BADGE_LABELS = {
    ProductImageBadgeType.NEW: "NEW",
    ProductImageBadgeType.SALE: "Распродажа",
    ProductImageBadgeType.HIT: "Хит",
    ProductImageBadgeType.EXCLUSIVE: "Эксклюзив",
}
QUICK_PRODUCT_BADGE_COLOR_ALIASES = {
    "purple": ProductImageBadgeColor.PURPLE,
    "фиолетовый": ProductImageBadgeColor.PURPLE,
    "pink": ProductImageBadgeColor.PINK,
    "розовый": ProductImageBadgeColor.PINK,
    "red": ProductImageBadgeColor.RED,
    "красный": ProductImageBadgeColor.RED,
    "orange": ProductImageBadgeColor.ORANGE,
    "оранжевый": ProductImageBadgeColor.ORANGE,
    "blue": ProductImageBadgeColor.BLUE,
    "синий": ProductImageBadgeColor.BLUE,
    "green": ProductImageBadgeColor.GREEN,
    "зеленый": ProductImageBadgeColor.GREEN,
    "зелёный": ProductImageBadgeColor.GREEN,
    "black": ProductImageBadgeColor.BLACK,
    "черный": ProductImageBadgeColor.BLACK,
    "чёрный": ProductImageBadgeColor.BLACK,
    "white": ProductImageBadgeColor.WHITE,
    "light": ProductImageBadgeColor.WHITE,
    "белый": ProductImageBadgeColor.WHITE,
    "светлый": ProductImageBadgeColor.WHITE,
}
QUICK_PRODUCT_BADGE_COLOR_LABELS = {
    ProductImageBadgeColor.PURPLE: "фиолетовый",
    ProductImageBadgeColor.PINK: "розовый",
    ProductImageBadgeColor.RED: "красный",
    ProductImageBadgeColor.ORANGE: "оранжевый",
    ProductImageBadgeColor.BLUE: "синий",
    ProductImageBadgeColor.GREEN: "зеленый",
    ProductImageBadgeColor.BLACK: "черный",
    ProductImageBadgeColor.WHITE: "белый",
}
QUICK_PRODUCT_BADGE_POSITION_ALIASES = {
    "top-left": ProductImageBadgePosition.TOP_LEFT,
    "top left": ProductImageBadgePosition.TOP_LEFT,
    "top_left": ProductImageBadgePosition.TOP_LEFT,
    "сверху слева": ProductImageBadgePosition.TOP_LEFT,
    "top-right": ProductImageBadgePosition.TOP_RIGHT,
    "top right": ProductImageBadgePosition.TOP_RIGHT,
    "top_right": ProductImageBadgePosition.TOP_RIGHT,
    "сверху справа": ProductImageBadgePosition.TOP_RIGHT,
    "bottom-left": ProductImageBadgePosition.BOTTOM_LEFT,
    "bottom left": ProductImageBadgePosition.BOTTOM_LEFT,
    "bottom_left": ProductImageBadgePosition.BOTTOM_LEFT,
    "снизу слева": ProductImageBadgePosition.BOTTOM_LEFT,
    "bottom-right": ProductImageBadgePosition.BOTTOM_RIGHT,
    "bottom right": ProductImageBadgePosition.BOTTOM_RIGHT,
    "bottom_right": ProductImageBadgePosition.BOTTOM_RIGHT,
    "снизу справа": ProductImageBadgePosition.BOTTOM_RIGHT,
}
QUICK_PRODUCT_BADGE_POSITION_LABELS = {
    ProductImageBadgePosition.TOP_LEFT: "сверху слева",
    ProductImageBadgePosition.TOP_RIGHT: "сверху справа",
    ProductImageBadgePosition.BOTTOM_LEFT: "снизу слева",
    ProductImageBadgePosition.BOTTOM_RIGHT: "снизу справа",
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
    related_product_ids: list[int]
    image_badge_type: ProductImageBadgeType
    image_badge_text: str | None
    image_badge_color: ProductImageBadgeColor | None
    image_badge_position: ProductImageBadgePosition | None
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
        seller_chat_configured = bool(settings.telegram_orders_notification_chat_id)
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

    async def format_active_orders_command(self, *, chat_id: int) -> list[str]:
        self._require_seller_group(chat_id)
        orders, total = await self.repository.list_active_orders(
            limit=ACTIVE_ORDERS_COMMAND_LIMIT
        )
        if not orders:
            return ["Активных заказов нет."]

        header = f"📋 Активные заказы: {len(orders)}"
        if total > len(orders):
            header += f" из {total}"
        blocks = [self._format_active_order(order) for order in orders]
        footer = (
            f"Показаны первые {len(orders)} из {total} заказов."
            if total > len(orders)
            else None
        )
        return self._chunk_command_message(header, blocks, footer=footer)

    def format_help_command(self, *, chat_id: int) -> str:
        self._require_seller_group(chat_id)
        return "\n".join(
            (
                "Команды Bot 2 для группы продавцов",
                "",
                "/help — показать эту справку.",
                "/active_orders — активные заказы, которые ещё не доставлены и не отменены.",
                "/chetam — оплаченные заказы, которые ещё не отправлены.",
                "/orders <ID> — детали заказа и кнопка SHIPPED. Пример: /orders 16",
                "/new_product_help — формат создания товара через Bot 2.",
                "/new_product — создать черновик товара из фото и подписи.",
                "/sellers — список продавцов и администраторов.",
                "/block_seller <Seller ID> — заблокировать продавца.",
                "/unblock_seller <Seller ID> — разблокировать продавца.",
                "",
                "Кнопки в заказах:",
                "SHIPPED — отметить заказ отправленным.",
                "CANCEL — закрыть кнопки без изменения заказа.",
            )
        )

    async def format_chetam_command(
        self,
        *,
        chat_id: int,
        actor_telegram_user_id: int | None,
    ) -> list[str]:
        self._require_seller_group(chat_id)
        await self._require_active_seller_actor(actor_telegram_user_id)
        orders, total = await self.repository.list_paid_unshipped_orders(
            limit=CHETAM_COMMAND_LIMIT
        )
        if not orders:
            return ["Оплаченных заказов до отправки нет."]

        header = f"Оплачены, но ещё не отправлены: {len(orders)}"
        if total > len(orders):
            header += f" из {total}"
        blocks = [self._format_chetam_order(order) for order in orders]
        footer = (
            f"Показаны первые {len(orders)} из {total} заказов."
            if total > len(orders)
            else None
        )
        return self._chunk_command_message(header, blocks, footer=footer, html_safe=True)

    async def format_order_detail_command(
        self,
        *,
        chat_id: int,
        order_id: int,
        actor_telegram_user_id: int | None,
    ) -> list[str]:
        self._require_seller_group(chat_id)
        await self._require_active_seller_actor(actor_telegram_user_id)
        order = await self.repository.get_order(order_id)
        if order is None:
            raise AppError("Заказ не найден.", 404)
        return self._split_command_text(self._format_order_detail(order))

    def order_action_reply_markup(self, order_id: int) -> dict[str, object]:
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "SHIPPED",
                        "callback_data": f"seller_order:ship:{order_id}",
                    },
                    {
                        "text": "CANCEL",
                        "callback_data": f"seller_order:cancel:{order_id}",
                    },
                ]
            ]
        }

    async def actor_user_id_for_telegram(self, telegram_user_id: int) -> int | None:
        actor = await self.repository.get_active_actor_user(telegram_user_id)
        return actor.id if actor is not None else None

    async def mark_order_shipped_command(
        self,
        *,
        chat_id: int,
        order_id: int,
        actor_telegram_user_id: int | None,
    ) -> list[str]:
        self._require_seller_group(chat_id)
        actor = await self._require_active_seller_actor(actor_telegram_user_id)
        order = await self.repository.get_order(order_id)
        if order is None:
            raise AppError("Заказ не найден.", 404)
        if order.status == OrderStatus.SHIPPED:
            return self._split_command_text(self._format_order_detail(order))
        if order.status in {OrderStatus.DELIVERED, OrderStatus.CANCELLED}:
            raise AppError(
                "Нельзя отметить отправленным доставленный или отменённый заказ.",
                409,
            )

        orders_service = OrdersService(self.session, audit_service=self.audit_service)
        await orders_service.update_order_status(
            order_id,
            OrderStatusUpdate(status=OrderStatus.SHIPPED),
            actor_user_id=actor.id,
        )
        updated_order = await self.repository.get_order(order_id)
        return self._split_command_text(
            self._format_order_detail(updated_order or order)
        )

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

    def _format_chetam_order(self, order) -> str:
        user = order.user
        address = self._telegram_html_text(order.delivery_address or MISSING_VALUE)
        height = self._telegram_html_text(
            self._height_label(getattr(user, "height_cm", None))
        )
        weight = self._telegram_html_text(
            self._weight_label(getattr(user, "weight_kg", None))
        )
        contact_phone = self._telegram_html_text(order.contact_phone or MISSING_VALUE)
        telegram_tag = self._telegram_html_text(self._telegram_tag(user))
        lines = [
            f"<b><i>ID заказа: {self._telegram_html_text(order.id)}</i></b>",
            "Оплата: подтверждено",
            f"Адрес: {address}",
            "Товары:",
            *self._order_item_summary_lines(order.items, html_safe=True),
            f"Рост: {height}",
            f"Вес: {weight}",
            f"Контактный номер: {contact_phone}",
            f"Телеграм тег: {telegram_tag}",
        ]
        return "\n".join(lines)

    def _format_order_detail(self, order) -> str:
        user = order.user
        payment = order.manual_payment
        payment_label = (
            payment_status_label(payment.status) if payment is not None else MISSING_VALUE
        )
        lines = [
            f"ID заказа: {order.id}",
            f"Статус заказа: {order_status_label(order.status)}",
            f"Статус оплаты: {payment_label}",
            f"Создан: {format_datetime_moscow(order.created_at)}",
            f"Telegram: {self._telegram_tag(user)}",
            f"Telegram ID: {getattr(user, 'telegram_id', None) or MISSING_VALUE}",
            f"Способ доставки: {delivery_method_label(order.delivery_method)}",
            f"Имя: {order.contact_name or MISSING_VALUE}",
            f"Телефон: {order.contact_phone or MISSING_VALUE}",
            f"Адрес: {order.delivery_address or MISSING_VALUE}",
            f"Комментарий: {order.delivery_comment or MISSING_VALUE}",
            "",
            "Товары:",
            *self._order_item_summary_lines(order.items),
        ]
        return "\n".join(lines)

    def _format_active_order(self, order) -> str:
        user = order.user
        username = f"@{user.username}" if user is not None and user.username else MISSING_VALUE
        telegram_name = (
            " ".join(
                part
                for part in (
                    getattr(user, "first_name", None),
                    getattr(user, "last_name", None),
                )
                if part
            )
            or order.contact_name
            or MISSING_VALUE
        )
        payment = order.manual_payment
        lines = [
            f"🛍 {order.order_number} (ID {order.id})",
            f"Статус заказа: {order_status_label(order.status)}",
            (
                f"Статус оплаты: {payment_status_label(payment.status)}"
                if payment is not None
                else f"Статус оплаты: {MISSING_VALUE}"
            ),
            f"Доставка: {delivery_method_label(order.delivery_method)}",
            f"Клиент: {username}, {telegram_name}",
            f"Создан: {format_datetime_moscow(order.created_at)}",
            "",
            "Товары:",
        ]
        for index, item in enumerate(order.items, start=1):
            try:
                size = format_size_for_display(item.variant_size_grid.value, item.variant_size)
            except ValueError:
                size = item.variant_size or MISSING_VALUE
            attributes = ", ".join(
                (
                    f"размер {size}",
                    f"цвет {item.variant_color or MISSING_VALUE}",
                    f"SKU {item.variant_sku or MISSING_VALUE}",
                )
            )
            lines.extend(
                (
                    f"{index}) {item.product_name}",
                    f"   {attributes}",
                    (
                        f"   {item.quantity} × {format_rubles(item.unit_price)} = "
                        f"{format_rubles(item.subtotal)}"
                    ),
                )
            )
        lines.extend(
            (
                "",
                f"Доставка: {format_rubles(getattr(order, 'delivery_price', '0.00'))}",
                f"К оплате: {format_rubles(order.total_amount)}",
                f"Панель продавца: {_seller_panel_order_url(order.id)}",
            )
        )
        return "\n".join(lines)

    def _order_item_summary_lines(
        self,
        items: object,
        *,
        html_safe: bool = False,
    ) -> list[str]:
        if not isinstance(items, list) or not items:
            return [self._message_text_value(MISSING_VALUE, html_safe=html_safe)]
        lines: list[str] = []
        multi_item = len(items) > 1
        for index, item in enumerate(items, start=1):
            prefix = f"{index}) " if multi_item else ""
            product_name = self._message_text_value(
                getattr(item, "product_name", None) or MISSING_VALUE,
                html_safe=html_safe,
            )
            color = self._message_text_value(
                getattr(item, "variant_color", None) or MISSING_VALUE,
                html_safe=html_safe,
            )
            size = self._message_text_value(
                self._display_item_size(item),
                html_safe=html_safe,
            )
            quantity = self._message_text_value(
                getattr(item, "quantity", None) or MISSING_VALUE,
                html_safe=html_safe,
            )
            lines.append(f"{prefix}Название: {product_name}")
            lines.append(f"   Цвет: {color}")
            lines.append(f"   Размер: {size}")
            lines.append(f"   Количество: {quantity}")
        return lines

    def _message_text_value(self, value: object, *, html_safe: bool = False) -> str:
        text = str(value)
        return self._telegram_html_text(text) if html_safe else text

    @staticmethod
    def _telegram_html_text(value: object) -> str:
        return html.escape(str(value), quote=False)

    def _display_item_size(self, item: object) -> str:
        size = getattr(item, "variant_size", None)
        if not size:
            return MISSING_VALUE
        size_grid = getattr(item, "variant_size_grid", None)
        size_grid_value = (
            getattr(size_grid, "value", size_grid) or ProductSizeGrid.CLOTHING_ALPHA.value
        )
        try:
            return format_size_for_display(str(size_grid_value), str(size))
        except ValueError:
            return str(size)

    def _height_label(self, value: object) -> str:
        return f"{value} см" if value else MISSING_VALUE

    def _weight_label(self, value: object) -> str:
        if not value:
            return MISSING_VALUE
        return f"{str(value).rstrip('0').rstrip('.')} кг"

    def _telegram_tag(self, user: object | None) -> str:
        if user is None:
            return MISSING_VALUE
        for field in ("telegram_username", "username"):
            value = getattr(user, field, None)
            if value:
                return f"@{str(value).lstrip('@')}"
        return MISSING_VALUE

    def _chunk_command_message(
        self,
        header: str,
        blocks: list[str],
        *,
        footer: str | None = None,
        html_safe: bool = False,
    ) -> list[str]:
        messages: list[str] = []
        current = header
        for block in blocks:
            candidate = f"{current}\n\n{block}"
            if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
                current = candidate
                continue
            messages.append(current)
            current = block
            while len(current) > TELEGRAM_MESSAGE_LIMIT:
                split_at = self._message_split_at(
                    current,
                    TELEGRAM_MESSAGE_LIMIT,
                    html_safe=html_safe,
                )
                messages.append(current[:split_at].rstrip())
                current = current[split_at:].lstrip()
        if footer:
            candidate = f"{current}\n\n{footer}"
            if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
                current = candidate
            else:
                messages.append(current)
                current = footer
        if current:
            messages.append(current)
        return messages

    def _message_split_at(self, text: str, limit: int, *, html_safe: bool = False) -> int:
        split_at = text.rfind("\n", 0, limit)
        if split_at > 0:
            return split_at
        if not html_safe:
            return limit

        split_at = limit
        ampersand_at = text.rfind("&", 0, split_at)
        semicolon_at = text.rfind(";", 0, split_at)
        if ampersand_at > semicolon_at:
            split_at = ampersand_at

        tag_open_at = text.rfind("<", 0, split_at)
        tag_close_at = text.rfind(">", 0, split_at)
        if tag_open_at > tag_close_at:
            split_at = min(split_at, tag_open_at)

        return split_at if split_at > 0 else limit

    def _split_command_text(
        self,
        text: str,
        *,
        limit: int = TELEGRAM_MESSAGE_LIMIT,
    ) -> list[str]:
        if len(text) <= limit:
            return [text]

        parts: list[str] = []
        current = ""
        for line in text.splitlines(keepends=True):
            if len(line) > limit:
                if current:
                    parts.append(current.rstrip())
                    current = ""
                parts.extend(line[index : index + limit] for index in range(0, len(line), limit))
                continue
            if len(current) + len(line) > limit:
                parts.append(current.rstrip())
                current = line
            else:
                current += line
        if current:
            parts.append(current.rstrip())
        return [part for part in parts if part]

    async def _require_active_seller_actor(self, telegram_user_id: int | None):
        if telegram_user_id is None:
            raise AppError(
                "Команда доступна только активным продавцам и администраторам.",
                403,
            )
        actor = await self.repository.get_active_actor_user(telegram_user_id)
        if actor is None:
            raise AppError(
                "Команда доступна только активным продавцам и администраторам.",
                403,
            )
        return actor

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
                image_badge_type=draft.image_badge_type,
                image_badge_text=draft.image_badge_text,
                image_badge_color=draft.image_badge_color,
                image_badge_position=draft.image_badge_position,
                status=draft.status,
                categories=categories,
                tag_ids=[tag.id for tag in tags],
                images=[image.payload],
                related_product_ids=draft.related_product_ids,
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
                    "image_badge_type": product.image_badge_type.value,
                    "image_badge_color": product.image_badge_color.value
                    if product.image_badge_color
                    else None,
                    "image_badge_position": product.image_badge_position.value
                    if product.image_badge_position
                    else None,
                    "related_product_ids": draft.related_product_ids,
                },
                metadata={
                    "actor_telegram_user_id": actor_telegram_user_id,
                    "actor_username": actor_username,
                    "source": "seller_bot_new_product",
                    "size_grid": draft.size_grid.value,
                    "variant_count": len(variant_payloads),
                    "image_badge_type": draft.image_badge_type.value,
                    "image_badge_color": draft.image_badge_color.value
                    if draft.image_badge_color
                    else None,
                    "image_badge_position": draft.image_badge_position.value
                    if draft.image_badge_position
                    else None,
                    "related_product_ids": draft.related_product_ids,
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
            error = self._quick_product_domain_error(exc)
            await self._audit_product_post_rejected(
                actor_telegram_user_id=actor_telegram_user_id,
                actor_username=actor_username,
                reason=error.message,
            )
            if error is exc:
                raise
            raise error from exc
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

        image_badge_type, image_badge_text = self._parse_image_badge(
            values.get("image_badge_type"),
            values.get("image_badge_text"),
        )
        image_badge_color = self._parse_image_badge_color(values.get("image_badge_color"))
        image_badge_position = self._parse_image_badge_position(
            values.get("image_badge_position")
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
            related_product_ids=self._parse_related_product_ids(
                values.get("related_product_ids")
            ),
            image_badge_type=image_badge_type,
            image_badge_text=image_badge_text,
            image_badge_color=image_badge_color,
            image_badge_position=image_badge_position,
            search_priority=search_priority,
            search_aliases=normalize_search_aliases(values.get("search_aliases")),
            status=status,
        )

    def _parse_related_product_ids(self, value: str | None) -> list[int]:
        normalized = self._optional_text(value)
        if normalized is None:
            return []

        raw_ids = [part for part in re.split(r"[,\s]+", normalized) if part]
        related_product_ids: list[int] = []
        for raw_id in raw_ids:
            if re.fullmatch(r"\d+", raw_id) is None:
                raise AppError(
                    "поле `Похожие товары` должно содержать ID через запятую, "
                    "например: `11, 12, 13`.",
                    400,
                )
            related_product_ids.append(
                self._parse_int(
                    raw_id,
                    field="Похожие товары",
                    minimum=1,
                    maximum=POSTGRES_INT32_MAX,
                )
            )

        if len(related_product_ids) != len(set(related_product_ids)):
            raise AppError("поле `Похожие товары` содержит повторяющиеся ID.", 400)
        return related_product_ids

    def _parse_image_badge(
        self,
        badge_value: str | None,
        text_value: str | None,
    ) -> tuple[ProductImageBadgeType, str | None]:
        normalized_badge = (badge_value or "").strip().casefold()
        badge_type = QUICK_PRODUCT_BADGE_ALIASES.get(normalized_badge)
        if badge_type is None:
            raise AppError(
                "поле `Виджет фото` должно быть одним из: нет, NEW, Распродажа, "
                "Хит, Эксклюзив, custom.",
                400,
            )

        badge_text = self._optional_text(text_value)
        if badge_type != ProductImageBadgeType.CUSTOM:
            return badge_type, None
        if badge_text is None:
            raise AppError(
                "для `Виджет фото: custom` добавь непустое поле "
                "`Текст виджета фото`.",
                400,
            )
        if len(badge_text) > 20:
            raise AppError("поле `Текст виджета фото` должно быть не длиннее 20 символов.", 400)
        if "<" in badge_text or ">" in badge_text:
            raise AppError("поле `Текст виджета фото` не должно содержать HTML.", 400)
        return badge_type, badge_text

    def _parse_image_badge_color(
        self,
        value: str | None,
    ) -> ProductImageBadgeColor | None:
        normalized = self._optional_text(value)
        if normalized is None:
            return None

        color = QUICK_PRODUCT_BADGE_COLOR_ALIASES.get(normalized.casefold())
        if color is None:
            raise AppError(
                "поле `Цвет виджета фото` должно быть одним из: purple, pink, red, "
                "orange, blue, green, black, white.",
                400,
            )
        return color

    def _parse_image_badge_position(
        self,
        value: str | None,
    ) -> ProductImageBadgePosition | None:
        normalized = self._optional_text(value)
        if normalized is None:
            return None

        position = QUICK_PRODUCT_BADGE_POSITION_ALIASES.get(normalized.casefold())
        if position is None:
            raise AppError(
                "поле `Положение виджета фото` должно быть одним из: сверху слева, "
                "сверху справа, снизу слева, снизу справа.",
                400,
            )
        return position

    def _parse_size_grid(self, value: str) -> ProductSizeGrid:
        size_grid = QUICK_PRODUCT_SIZE_GRID_ALIASES.get(value.strip().casefold())
        if size_grid is None:
            raise AppError(
                "поле `Тип размеров` должно быть `одежда`, `обувь`, "
                "`clothing_alpha` или `shoes_eu`.",
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
        if size_grid == ProductSizeGrid.SHOES_EU:
            prefix_match = re.fullmatch(r"(?:RU|EU|US|UK)\s*(\d+)", value, re.IGNORECASE)
            if prefix_match and prefix_match.group(1) in SHOES_EU_SIZES:
                return (
                    f"размер `{value}` недопустим для обуви. Используй европейский размер "
                    f"без префикса: `{prefix_match.group(1)}`. Разрешены размеры обуви EU: "
                    "35, 36, ..., 46."
                )
            if "." in value or "," in value:
                return (
                    f"размер `{value}` недопустим для обуви: половинные размеры не "
                    "поддерживаются. Разрешены целые размеры EU 35-46."
                )
            return (
                f"размер `{value}` недопустим для обуви. Разрешены только европейские "
                "целые размеры: 35, 36, ..., 46."
            )
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
        lines = [
            "Товар создан.",
            "",
            f"ID: {product_id}",
            f"Статус: {self._quick_product_status_label(draft.status)}",
            f"Тип размеров: {self._quick_product_size_grid_label(draft.size_grid)}",
            f"Вариантов: {len(draft.variants)}",
        ]
        if draft.image_badge_type != ProductImageBadgeType.NONE:
            lines.append(f"Виджет фото: {self._quick_product_badge_label(draft)}")
        if draft.image_badge_color is not None:
            lines.append(
                f"Цвет виджета фото: {QUICK_PRODUCT_BADGE_COLOR_LABELS[draft.image_badge_color]}"
            )
        if draft.image_badge_position is not None:
            lines.append(
                "Положение виджета фото: "
                f"{QUICK_PRODUCT_BADGE_POSITION_LABELS[draft.image_badge_position]}"
            )
        if draft.related_product_ids:
            lines.append(
                f"Похожие товары: {', '.join(str(item) for item in draft.related_product_ids)}"
            )
        lines.extend(
            (
                "",
                f"Редактировать: {_seller_panel_product_edit_url(product_id)}",
            )
        )
        return "\n".join(lines)

    def _new_product_help_text(self) -> str:
        clothing_example = """/new_product

Название: Футболка HERMES
Описание: Бюджетные футболки, весна/лето
Цена: 700
Старая цена:
Категории: Футболки
Теги: футболка, hermes
Тип размеров: одежда
Размеры:
M / Белый / 10 / HERMES-M-W
L / Белый / 8 / HERMES-L-W
XL / Черный / 5 / HERMES-XL-B
3XL / Черный / 3 / HERMES-3XL-B
Похожие товары: 11, 12, 13
Виджет фото: Распродажа
Цвет виджета фото: красный
Положение виджета фото: снизу слева
Псевдонимы поиска: футболка, фудболка, футбалка
Статус: черновик"""
        footwear_example = """/new_product

Название: Кроссовки Nike Air Max
Описание: Лёгкие кроссовки, качество люкс
Цена: 4990
Старая цена: 6990
Категории: Обувь
Теги: кроссовки, nike, premium
Тип размеров: обувь
Размеры:
39 / Белый / 3 / SKU-NIKE-39-W
40 / Белый / 2 / SKU-NIKE-40-W
41 / Черный / 4 / SKU-NIKE-41-B
Похожие товары: 11, 12, 13
Виджет фото: NEW
Цвет виджета фото: purple
Положение виджета фото: сверху слева
Псевдонимы поиска: найк, кросовки, кроссовки
Статус: черновик"""
        custom_badge_example = """Виджет фото: custom
Текст виджета фото: -30%
Цвет виджета фото: pink
Положение виджета фото: сверху справа"""
        return "\n\n".join(
            (
                "Отправь фото товара с подписью в одном из форматов ниже.",
                f"<b>Одежда:</b>\n<pre><code>{html.escape(clothing_example)}</code></pre>",
                f"<b>Обувь:</b>\n<pre><code>{html.escape(footwear_example)}</code></pre>",
                (
                    "<b>Свой виджет:</b>\n"
                    f"<pre><code>{html.escape(custom_badge_example)}</code></pre>"
                ),
                "\n".join(
                    (
                        "Формат варианта: размер / цвет / остаток / SKU.",
                        "Цвет варианта можно писать по-русски или латиницей; он сохранится "
                        "и будет показан как введён.",
                        "SKU можно оставить пустым, тогда Bot 2 создаст безопасное значение.",
                        "Размеры одежды: XS, S, M, L, XL, XXL, 3XL, ONE_SIZE.",
                        "Размеры обуви: только европейские целые размеры EU 35-46 без "
                        "RU/EU/US/UK и без половинных размеров.",
                        "Похожие товары указываются ID через запятую.",
                        "Виджет фото: нет, NEW, Распродажа, Хит, Эксклюзив, custom.",
                        "Для custom добавь: Текст виджета фото: ...",
                        "Цвет виджета фото: purple, pink, red, orange, blue, green, black, white "
                        "или по-русски: фиолетовый, розовый, красный, оранжевый, синий, "
                        "зелёный, чёрный, белый.",
                        "Положение виджета фото: сверху слева, сверху справа, "
                        "снизу слева, снизу справа.",
                        "Категории и теги должны уже существовать.",
                        "По умолчанию товар создаётся как черновик.",
                    )
                ),
            )
        )

    def _quick_product_domain_error(self, exc: AppError) -> AppError:
        unknown_prefix = "Unknown related product IDs:"
        if exc.message.startswith(unknown_prefix):
            product_ids = exc.message.removeprefix(unknown_prefix).strip()
            return AppError(
                f"похожие товары не найдены: {product_ids}. Проверь ID товаров.",
                exc.status_code,
            )
        if exc.message == "A product cannot be related to itself":
            return AppError("товар нельзя указать похожим на самого себя.", exc.status_code)
        return exc

    def _quick_product_badge_label(self, draft: QuickProductDraft) -> str:
        if draft.image_badge_type == ProductImageBadgeType.CUSTOM:
            return f"custom ({draft.image_badge_text})"
        return QUICK_PRODUCT_BADGE_LABELS[draft.image_badge_type]

    def _quick_product_status_label(self, status_value: ProductStatus) -> str:
        return "черновик" if status_value == ProductStatus.DRAFT else "активен"

    def _quick_product_size_grid_label(self, size_grid: ProductSizeGrid) -> str:
        if size_grid == ProductSizeGrid.SHOES_EU:
            return "обувь EU"
        if size_grid == ProductSizeGrid.SHOES_RU:
            return "обувь RU (legacy)"
        return "одежда"

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
            "image_badge_text": "Текст виджета фото",
            "image_badge_type": "Виджет фото",
            "image_badge_color": "Цвет виджета фото",
            "image_badge_position": "Положение виджета фото",
            "related_product_ids": "Похожие товары",
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
        configured_chat_id = settings.telegram_orders_notification_chat_id
        if not configured_chat_id or str(chat_id) != configured_chat_id.strip():
            raise AppError(SELLER_GROUP_ONLY_MESSAGE, 403)


def _seller_panel_order_url(order_id: int) -> str:
    return join_public_url(settings.public_seller_panel_base_url, f"orders?order={order_id}")


def _seller_panel_product_edit_url(product_id: int) -> str:
    return join_public_url(
        settings.public_seller_panel_base_url,
        f"products/{product_id}/edit",
    )
