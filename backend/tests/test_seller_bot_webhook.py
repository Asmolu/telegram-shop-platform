import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AppError
from app.core.log_sanitization import (
    SensitiveDataLogFilter,
    redact_sensitive_path,
    redact_sensitive_text,
)
from app.db.models import (
    ManualPaymentStatus,
    PendingSellerRegistration,
    ReturnRequestStatus,
    SellerRegistrationStatus,
)
from app.main import create_app
from app.modules.seller_auth.callbacks import build_seller_registration_callback_data
from app.modules.seller_auth.schemas import SellerRegistrationStartRequest
from app.modules.seller_auth.service import SellerAuthService
from app.modules.telegram.router import get_seller_bot_webhook_service
from app.modules.telegram.schemas import SellerBotWebhookResponse, TelegramUpdate
from app.modules.telegram.service import SellerBotWebhookService


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False
        self.added: list[object] = []

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None

    def add(self, instance: object) -> None:
        self.added.append(instance)


class FakeTelegramService:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.parse_modes: list[str | None] = []
        self.reply_markups: list[dict[str, object]] = []
        self.callback_answers: list[tuple[str, str | None]] = []
        self.edits: list[tuple[str, int, str, dict[str, object] | None]] = []
        self.caption_edits: list[tuple[str, int, str, dict[str, object] | None]] = []
        self.markup_edits: list[tuple[str, int, dict[str, object]]] = []

    async def send_message(
        self,
        chat_id: str,
        message: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        self.messages.append((chat_id, message))
        self.parse_modes.append(parse_mode)
        if reply_markup is not None:
            self.reply_markups.append(reply_markup)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
    ) -> None:
        self.callback_answers.append((callback_query_id, text))

    async def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        self.edits.append((chat_id, message_id, message, reply_markup))

    async def edit_message_caption(
        self,
        chat_id: str,
        message_id: int,
        caption: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        self.caption_edits.append((chat_id, message_id, caption, reply_markup))

    async def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        *,
        reply_markup: dict[str, object],
    ) -> None:
        self.markup_edits.append((chat_id, message_id, reply_markup))


class FakeManualPaymentsService:
    def __init__(
        self,
        *,
        actor_user_id: int | None = 9,
        terminal_status: ManualPaymentStatus | None = None,
        expected_chat_id: int = -100,
    ) -> None:
        self.actions: list[tuple[str, int, int | None, int]] = []
        self.actor_user_id = actor_user_id
        self.terminal_status = terminal_status
        self.current_status = terminal_status or ManualPaymentStatus.SUBMITTED
        self.expected_chat_id = expected_chat_id

    async def actor_user_id_for_telegram(self, telegram_id: int) -> int | None:
        assert telegram_id == 500
        return self.actor_user_id

    async def approve(
        self,
        payment_id: int,
        *,
        actor_user_id: int | None,
        source: str,
        actor_telegram_user_id: int,
        seller_chat_id: int | None = None,
        seller_message_id: int | None = None,
    ) -> SimpleNamespace:
        assert source == "seller_bot"
        assert seller_chat_id == self.expected_chat_id
        assert seller_message_id == 11
        if self.terminal_status is not None:
            raise AppError("Payment cannot be approved", status.HTTP_409_CONFLICT)
        if self.current_status != ManualPaymentStatus.APPROVED:
            self.actions.append(("approve", payment_id, actor_user_id, actor_telegram_user_id))
            self.current_status = ManualPaymentStatus.APPROVED
        return SimpleNamespace(
            id=payment_id,
            order_number="ORD-17",
            status=ManualPaymentStatus.APPROVED,
            reject_reason=None,
        )

    async def reject(
        self,
        payment_id: int,
        *,
        actor_user_id: int | None,
        reject_reason: str,
        source: str,
        actor_telegram_user_id: int,
        seller_chat_id: int | None = None,
        seller_message_id: int | None = None,
    ) -> SimpleNamespace:
        assert source == "seller_bot"
        assert reject_reason == "Деньги не поступили"
        assert seller_chat_id == self.expected_chat_id
        assert seller_message_id == 11
        if self.terminal_status is not None:
            raise AppError("Payment cannot be rejected", status.HTTP_409_CONFLICT)
        if self.current_status != ManualPaymentStatus.REJECTED:
            self.actions.append(("reject", payment_id, actor_user_id, actor_telegram_user_id))
            self.current_status = ManualPaymentStatus.REJECTED
        return SimpleNamespace(
            id=payment_id,
            order_number="ORD-17",
            status=ManualPaymentStatus.REJECTED,
            reject_reason=reject_reason,
        )

    async def get_for_seller(self, payment_id: int) -> SimpleNamespace:
        if self.terminal_status is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)
        return SimpleNamespace(
            id=payment_id,
            order_number="ORD-17",
            status=self.terminal_status,
            reject_reason=None,
        )


class FakeReturnRequestsService:
    def __init__(
        self,
        *,
        initial_status: ReturnRequestStatus = ReturnRequestStatus.PENDING,
    ) -> None:
        self.actions: list[tuple[str, int, int, str | None]] = []
        self.requests: dict[int, SimpleNamespace] = {
            7: self._request(7, initial_status=initial_status)
        }

    async def approve(
        self,
        *,
        return_request_id: int,
        actor_user_id: int,
        payload,
    ) -> SimpleNamespace:
        return await self._decide(
            "approve",
            return_request_id=return_request_id,
            actor_user_id=actor_user_id,
            decision_comment=payload.decision_comment,
            next_status=ReturnRequestStatus.APPROVED,
        )

    async def reject(
        self,
        *,
        return_request_id: int,
        actor_user_id: int,
        payload,
    ) -> SimpleNamespace:
        return await self._decide(
            "reject",
            return_request_id=return_request_id,
            actor_user_id=actor_user_id,
            decision_comment=payload.decision_comment,
            next_status=ReturnRequestStatus.REJECTED,
        )

    async def get_admin_return_request(self, return_request_id: int) -> SimpleNamespace:
        request = self.requests.get(return_request_id)
        if request is None:
            raise AppError("Return request not found", status.HTTP_404_NOT_FOUND)
        return request

    async def _decide(
        self,
        action: str,
        *,
        return_request_id: int,
        actor_user_id: int,
        decision_comment: str | None,
        next_status: ReturnRequestStatus,
    ) -> SimpleNamespace:
        request = self.requests.get(return_request_id)
        if request is None:
            raise AppError("Return request not found", status.HTTP_404_NOT_FOUND)
        if request.status != ReturnRequestStatus.PENDING:
            raise AppError("Return request is already decided", status.HTTP_409_CONFLICT)
        self.actions.append((action, return_request_id, actor_user_id, decision_comment))
        request.status = next_status
        request.decided_by_user_id = actor_user_id
        request.decision_comment = decision_comment
        request.decided_at = _now()
        return request

    def _request(
        self,
        return_request_id: int,
        *,
        initial_status: ReturnRequestStatus,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=return_request_id,
            return_number="RET-00000007",
            order_id=17,
            order_number="ORD-00000017",
            user_id=3,
            customer_name="Ada",
            customer_phone="+79999999999",
            status=initial_status,
            reason="Не подошёл размер",
            comment="Комментарий клиента",
            items=[
                SimpleNamespace(
                    id=1,
                    product_name="Hoodie",
                    product_brand="ICON",
                    sku="SKU-1",
                    size="M",
                    color="Black",
                    quantity=1,
                )
            ],
            attachments=[SimpleNamespace(id=1)],
            decided_at=None,
            decided_by_user_id=None,
            decision_comment=None,
        )


class FakeAuditService:
    async def record_action(self, **_: object) -> None:
        return None


class FakeSellerAuthRepository:
    def __init__(self) -> None:
        self.next_registration_id = 1
        self.registrations: dict[int, PendingSellerRegistration] = {}

    def add_pending_registration(self, registration: PendingSellerRegistration) -> None:
        registration.id = self.next_registration_id
        self.next_registration_id += 1
        registration.created_at = _now()
        registration.updated_at = _now()
        self.registrations[registration.id] = registration

    def add_seller_credential(self, _: object) -> None:
        return None

    def add_user(self, _: object) -> None:
        return None

    async def get_credential_by_email(self, _: str) -> None:
        return None

    async def get_active_pending_by_email(
        self,
        *,
        email: str,
        now: datetime,
    ) -> PendingSellerRegistration | None:
        for registration in self.registrations.values():
            if (
                registration.email == email
                and registration.status
                in {
                    SellerRegistrationStatus.PENDING,
                    SellerRegistrationStatus.AWAITING_APPROVAL,
                    SellerRegistrationStatus.APPROVED,
                }
                and registration.expires_at > now
            ):
                return registration
        return None

    async def get_pending_by_id(self, registration_id: int) -> PendingSellerRegistration | None:
        return self.registrations.get(registration_id)

    async def get_pending_by_start_token_hash(
        self,
        token_hash: str,
    ) -> PendingSellerRegistration | None:
        for registration in self.registrations.values():
            if registration.bot_start_token_hash == token_hash:
                return registration
        return None

    async def get_user_by_telegram_id(self, _: int) -> None:
        return None


@pytest.mark.asyncio
async def test_seller_bot_webhook_links_registration_and_requests_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, telegram = _webhook_service()
    started = await service.seller_auth_service.start_registration(_start_payload())

    response = await service.handle_update(
        TelegramUpdate.model_validate(
            {
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "text": "/start seller_start-token",
                    "chat": {"id": 100, "type": "private"},
                    "from": {
                        "id": 99,
                        "username": "sellername",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                    },
                },
            }
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.handled is True
    assert response.result == "registration_linked"
    assert registration.telegram_user_id == 99
    assert registration.telegram_chat_id == 100
    assert registration.status == SellerRegistrationStatus.AWAITING_APPROVAL
    assert registration.verification_code_hash is None
    assert telegram.messages[0][0] == "-100"
    assert "seller@example.com" in telegram.messages[0][1]
    assert telegram.reply_markups[0]["inline_keyboard"]


@pytest.mark.asyncio
async def test_seller_bot_confirm_callback_sends_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, telegram = _webhook_service()
    started = await service.seller_auth_service.start_registration(_start_payload())
    await service.handle_update(_telegram_start_update())
    telegram.messages.clear()

    response = await service.handle_update(
        _callback_update(
            build_seller_registration_callback_data(
                action="approve",
                registration_id=started.registration_id,
            )
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.handled is True
    assert response.result == "registration_approved"
    assert registration.status == SellerRegistrationStatus.APPROVED
    assert telegram.messages == [
        ("100", "Код подтверждения: 123456. Введите его в Seller Panel."),
        ("-100", "Регистрация продавца подтверждена. Код отправлен продавцу."),
    ]


@pytest.mark.asyncio
async def test_seller_bot_reject_callback_sends_failure_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, telegram = _webhook_service()
    started = await service.seller_auth_service.start_registration(_start_payload())
    await service.handle_update(_telegram_start_update())
    telegram.messages.clear()

    response = await service.handle_update(
        _callback_update(
            build_seller_registration_callback_data(
                action="reject",
                registration_id=started.registration_id,
            )
        )
    )

    registration = repository.registrations[started.registration_id]
    assert response.handled is True
    assert response.result == "registration_rejected"
    assert registration.status == SellerRegistrationStatus.REJECTED
    assert telegram.messages == [
        ("100", "Регистрация не удалась."),
        ("-100", "Регистрация продавца отклонена."),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("approve", ManualPaymentStatus.APPROVED),
        ("reject", ManualPaymentStatus.REJECTED),
    ],
)
async def test_seller_bot_manual_payment_callback_uses_shared_service(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    expected_status: ManualPaymentStatus,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    base_service, _, telegram = _webhook_service()
    payments = FakeManualPaymentsService()
    service = SellerBotWebhookService(
        seller_auth_service=base_service.seller_auth_service,
        manual_payments_service=payments,
        telegram_service=telegram,
    )

    first = await service.handle_update(
        _callback_update(f"manual_payment:{action}:17", with_photo=True)
    )
    second = await service.handle_update(
        _callback_update(f"manual_payment:{action}:17", with_photo=True)
    )

    assert first.result == f"manual_payment_{expected_status.value.lower()}"
    assert second.result == first.result
    assert payments.actions == [
        (action, 17, 9, 500),
    ]
    assert telegram.callback_answers[-1] == (
        "callback-id",
        (
            "Статус оплаты: Оплачено"
            if expected_status == ManualPaymentStatus.APPROVED
            else "Статус оплаты: Отклонено"
        ),
    )
    assert telegram.edits == []
    assert telegram.caption_edits[-1][1] == 11
    assert telegram.caption_edits[-1][3] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_seller_bot_manual_payment_callback_accepts_orders_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_orders_chat_id", "-200")
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    base_service, _, telegram = _webhook_service()
    payments = FakeManualPaymentsService(expected_chat_id=-200)
    service = SellerBotWebhookService(
        seller_auth_service=base_service.seller_auth_service,
        manual_payments_service=payments,
        telegram_service=telegram,
    )

    response = await service.handle_update(
        _callback_update("manual_payment:approve:17", chat_id=-200)
    )

    assert response.result == "manual_payment_approved"
    assert payments.actions == [("approve", 17, 9, 500)]


@pytest.mark.asyncio
async def test_seller_bot_manual_payment_callback_rejects_other_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    base_service, _, telegram = _webhook_service()
    payments = FakeManualPaymentsService()
    service = SellerBotWebhookService(
        seller_auth_service=base_service.seller_auth_service,
        manual_payments_service=payments,
        telegram_service=telegram,
    )

    response = await service.handle_update(
        _callback_update("manual_payment:approve:17", chat_id=-200)
    )

    assert response.result == "approval_rejected_outside_seller_group"
    assert payments.actions == []


@pytest.mark.asyncio
async def test_seller_bot_callback_rejects_returns_chat_when_orders_chat_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_orders_chat_id", "-200")
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    monkeypatch.setattr(settings, "telegram_backup_chat_id", "-400")
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    base_service, _, telegram = _webhook_service()
    payments = FakeManualPaymentsService(expected_chat_id=-200)
    service = SellerBotWebhookService(
        seller_auth_service=base_service.seller_auth_service,
        manual_payments_service=payments,
        telegram_service=telegram,
    )

    response = await service.handle_update(
        _callback_update("manual_payment:approve:17", chat_id=-300)
    )

    assert response.result == "approval_rejected_outside_seller_group"
    assert payments.actions == []


@pytest.mark.asyncio
async def test_seller_bot_manual_payment_callback_requires_active_seller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    base_service, _, telegram = _webhook_service()
    payments = FakeManualPaymentsService(actor_user_id=None)
    service = SellerBotWebhookService(
        seller_auth_service=base_service.seller_auth_service,
        manual_payments_service=payments,
        telegram_service=telegram,
    )

    response = await service.handle_update(_callback_update("manual_payment:approve:17"))

    assert response.result == "manual_payment_callback_unauthorized"
    assert payments.actions == []
    assert telegram.callback_answers[-1] == (
        "callback-id",
        "Only an active seller or administrator can review payments.",
    )


@pytest.mark.asyncio
async def test_seller_bot_stale_payment_callback_reports_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    base_service, _, telegram = _webhook_service()
    payments = FakeManualPaymentsService(terminal_status=ManualPaymentStatus.EXPIRED)
    service = SellerBotWebhookService(
        seller_auth_service=base_service.seller_auth_service,
        manual_payments_service=payments,
        telegram_service=telegram,
    )

    response = await service.handle_update(_callback_update("manual_payment:approve:17"))

    assert response.result == "manual_payment_expired"
    assert payments.actions == []
    assert telegram.callback_answers[-1] == (
        "callback-id",
        "Статус оплаты: Время оплаты истекло",
    )


@pytest.mark.asyncio
async def test_seller_bot_webhook_ignores_non_start_messages() -> None:
    service, _, telegram = _webhook_service()

    response = await service.handle_update(
        TelegramUpdate.model_validate(
            {
                "message": {
                    "text": "hello",
                    "chat": {"id": 100, "type": "private"},
                    "from": {"id": 99, "username": "sellername"},
                }
            }
        )
    )

    assert response.handled is False
    assert response.result == "ignored"
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_block_seller_command_uses_internal_seller_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/block_seller 5"))

    assert response.handled is True
    assert response.result == "seller_blocked"
    assert seller_bot.blocked_user_ids == [5]
    assert telegram.messages == [("-100", "Seller #5 has been blocked.")]


@pytest.mark.asyncio
async def test_new_product_caption_command_is_routed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_product_command_update())

    assert response.handled is True
    assert response.result == "bot_product_draft_created"
    assert seller_bot.product_messages == ["White Hoodie"]
    assert telegram.messages == [("-100", "Product draft created.")]


@pytest.mark.asyncio
async def test_active_orders_command_is_routed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/active_orders"))

    assert response.result == "active_orders_sent"
    assert telegram.messages == [("-100", "Active orders for -100")]


@pytest.mark.asyncio
async def test_help_command_is_routed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/help"))

    assert response.result == "help_sent"
    assert telegram.messages == [("-100", "Help for -100: /chetam /orders <ID>")]


@pytest.mark.asyncio
async def test_seller_group_command_accepts_orders_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_orders_chat_id", "-200")
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, telegram = _seller_command_webhook_service()

    response = await service.handle_update(
        _seller_group_command_update("/help", chat_id=-200)
    )

    assert response.result == "help_sent"
    assert telegram.messages == [("-200", "Help for -200: /chetam /orders <ID>")]


@pytest.mark.asyncio
async def test_chetam_command_is_routed_and_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/chetam"))

    assert response.result == "chetam_sent"
    assert seller_bot.chetam_actor_ids == [500]
    assert telegram.messages == [("-100", "Chetam for -100"), ("-100", "Second page")]
    assert telegram.parse_modes == ["HTML", "HTML"]


@pytest.mark.asyncio
async def test_orders_command_sends_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/orders 16"))

    assert response.result == "order_detail_sent"
    assert seller_bot.order_detail_requests == [(16, 500)]
    assert telegram.messages == [("-100", "ID заказа: 16\nСтатус заказа: В обработке")]
    assert telegram.reply_markups[0]["inline_keyboard"][0][0]["callback_data"] == (
        "seller_order:ship:16"
    )
    assert telegram.reply_markups[0]["inline_keyboard"][0][1]["callback_data"] == (
        "seller_order:cancel:16"
    )


@pytest.mark.asyncio
async def test_orders_command_rejects_invalid_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/orders nope"))

    assert response.result == "seller_command_error"
    assert seller_bot.order_detail_requests == []
    assert "Формат: /orders <ID заказа>" in telegram.messages[0][1]


@pytest.mark.asyncio
async def test_order_shipped_callback_updates_order_and_removes_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_callback_update("seller_order:ship:16"))

    assert response.result == "order_shipped"
    assert seller_bot.shipped_order_ids == [(16, 500)]
    assert telegram.callback_answers == [("callback-id", "Статус заказа: Отправлен.")]
    assert telegram.edits == [
        (
            "-100",
            11,
            "ID заказа: 16\nСтатус заказа: Отправлен",
            {"inline_keyboard": []},
        )
    ]


@pytest.mark.asyncio
async def test_order_cancel_callback_only_closes_interaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_callback_update("seller_order:cancel:16"))

    assert response.result == "order_action_cancelled"
    assert seller_bot.shipped_order_ids == []
    assert telegram.callback_answers == [("callback-id", "Действие отменено.")]
    assert telegram.markup_edits == [("-100", 11, {"inline_keyboard": []})]


@pytest.mark.asyncio
async def test_return_approve_callback_updates_status_and_removes_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_orders_chat_id", "-200")
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, returns, telegram = _return_action_webhook_service()

    response = await service.handle_update(_callback_update("return:approve:7", chat_id=-300))

    assert response.result == "return_request_approved"
    assert seller_bot.actor_lookup_ids == [500]
    assert returns.actions == [("approve", 7, 42, "Одобрено через Telegram")]
    assert returns.requests[7].status == ReturnRequestStatus.APPROVED
    assert telegram.callback_answers == [("callback-id", "Возврат подтверждён")]
    assert telegram.edits[0][0:2] == ("-300", 11)
    assert "Статус: Одобрено" in telegram.edits[0][2]
    assert "Решил: пользователь #42" in telegram.edits[0][2]
    assert telegram.edits[0][3] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_return_reject_callback_updates_status_and_removes_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _seller_bot, returns, telegram = _return_action_webhook_service()

    response = await service.handle_update(_callback_update("return:reject:7", chat_id=-300))

    assert response.result == "return_request_rejected"
    assert returns.actions == [("reject", 7, 42, "Отклонено через Telegram")]
    assert returns.requests[7].status == ReturnRequestStatus.REJECTED
    assert telegram.callback_answers == [("callback-id", "Возврат отклонён")]
    assert "Статус: Отклонено" in telegram.edits[0][2]
    assert telegram.edits[0][3] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_return_callback_uses_seller_chat_fallback_when_returns_chat_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_orders_chat_id", "-200")
    monkeypatch.setattr(settings, "telegram_returns_chat_id", None)
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _seller_bot, returns, telegram = _return_action_webhook_service()

    response = await service.handle_update(_callback_update("return:approve:7", chat_id=-100))

    assert response.result == "return_request_approved"
    assert returns.requests[7].status == ReturnRequestStatus.APPROVED
    assert telegram.callback_answers == [("callback-id", "Возврат подтверждён")]


@pytest.mark.asyncio
async def test_return_callbacks_are_rejected_from_orders_and_backup_chats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_orders_chat_id", "-200")
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    monkeypatch.setattr(settings, "telegram_backup_chat_id", "-400")
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _seller_bot, returns, telegram = _return_action_webhook_service()

    orders_response = await service.handle_update(
        _callback_update("return:approve:7", chat_id=-200)
    )
    backup_response = await service.handle_update(
        _callback_update("return:approve:7", chat_id=-400)
    )

    assert orders_response.result == "return_request_callback_rejected_outside_returns_chat"
    assert backup_response.result == "return_request_callback_rejected_outside_returns_chat"
    assert returns.actions == []
    assert returns.requests[7].status == ReturnRequestStatus.PENDING
    assert telegram.callback_answers == [
        ("callback-id", "Недостаточно прав"),
        ("callback-id", "Недостаточно прав"),
    ]


@pytest.mark.asyncio
async def test_return_callback_requires_authorized_seller_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    service, seller_bot, returns, telegram = _return_action_webhook_service(actor_user_id=None)

    response = await service.handle_update(_callback_update("return:approve:7", chat_id=-300))

    assert response.result == "return_request_callback_unauthorized"
    assert seller_bot.actor_lookup_ids == [500]
    assert returns.actions == []
    assert returns.requests[7].status == ReturnRequestStatus.PENDING
    assert telegram.callback_answers == [("callback-id", "Недостаточно прав")]


@pytest.mark.asyncio
async def test_return_callback_for_already_decided_request_refreshes_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    service, _seller_bot, returns, telegram = _return_action_webhook_service(
        initial_status=ReturnRequestStatus.APPROVED
    )

    response = await service.handle_update(_callback_update("return:approve:7", chat_id=-300))

    assert response.result == "return_request_already_decided"
    assert returns.actions == []
    assert returns.requests[7].status == ReturnRequestStatus.APPROVED
    assert telegram.callback_answers == [("callback-id", "Заявка уже обработана")]
    assert "Статус: Одобрено" in telegram.edits[0][2]
    assert telegram.edits[0][3] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_return_callback_for_missing_request_answers_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "-300")
    service, _seller_bot, returns, telegram = _return_action_webhook_service()
    returns.requests.clear()

    response = await service.handle_update(_callback_update("return:approve:7", chat_id=-300))

    assert response.result == "return_request_not_found"
    assert telegram.callback_answers == [("callback-id", "Заявка не найдена")]
    assert telegram.edits == []


@pytest.mark.asyncio
async def test_new_product_help_command_is_routed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update("/new_product_help"))

    assert response.handled is True
    assert response.result == "new_product_help_sent"
    assert "Размеры одежды: XS, S, M" in telegram.messages[0][1]
    assert "европейские целые размеры EU 35-46" in telegram.messages[0][1]
    assert "RU/EU/US/UK" in telegram.messages[0][1]
    assert telegram.parse_modes == ["HTML"]


@pytest.mark.asyncio
async def test_new_product_error_reply_hides_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()
    seller_bot.product_exception = RuntimeError(
        "Traceback: asyncpg password=secret raw database failure"
    )

    response = await service.handle_update(_seller_group_product_command_update())

    assert response.result == "bot_product_post_rejected"
    reply = telegram.messages[0][1]
    assert "Не удалось создать товар" in reply
    assert "внутренняя ошибка" in reply
    assert "Traceback" not in reply
    assert "password=secret" not in reply
    assert "asyncpg" not in reply


@pytest.mark.asyncio
async def test_new_product_validation_error_reply_is_seller_friendly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()
    seller_bot.product_exception = AppError(
        "размер `RU 39` недопустим для обуви. Используй европейский размер без "
        "префикса: `39`. Разрешены размеры обуви: 35, 36, ..., 46.",
        status.HTTP_400_BAD_REQUEST,
    )

    response = await service.handle_update(_seller_group_product_command_update())

    assert response.result == "bot_product_post_rejected"
    reply = telegram.messages[0][1]
    assert reply.startswith("Не удалось создать товар.")
    assert "Ошибка: размер `RU 39` недопустим для обуви" in reply
    assert "Используй европейский размер без префикса: `39`" in reply
    assert "/new_product_help" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_text", "expected_fragment"),
    [
        ("/block_seller", "Usage: /block_seller <Seller ID>. Get Seller ID with /sellers."),
        (
            "/block_seller nope",
            "Usage: /block_seller <Seller ID>. Get Seller ID with /sellers.",
        ),
        ("/block_seller 6902459394", "Telegram ID"),
        ("/block_seller 999999999999999999999999", "outside the supported range"),
    ],
)
async def test_block_seller_invalid_id_is_handled_without_seller_lookup(
    monkeypatch: pytest.MonkeyPatch,
    command_text: str,
    expected_fragment: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, seller_bot, telegram = _seller_command_webhook_service()

    response = await service.handle_update(_seller_group_command_update(command_text))

    assert response.handled is True
    assert response.result == "seller_command_error"
    assert seller_bot.blocked_user_ids == []
    assert expected_fragment in telegram.messages[0][1]


@pytest.mark.asyncio
async def test_seller_bot_webhook_sends_error_for_expired_token() -> None:
    telegram = FakeTelegramService()

    class FakeSellerAuthService:
        telegram_service = telegram

        async def handle_telegram_start(self, _: object) -> None:
            raise AppError("Seller registration expired", status.HTTP_400_BAD_REQUEST)

    service = SellerBotWebhookService(
        seller_auth_service=FakeSellerAuthService(),
        telegram_service=telegram,
    )

    response = await service.handle_update(
        TelegramUpdate.model_validate(
            {
                "message": {
                    "text": "/start seller_expired",
                    "chat": {"id": 100, "type": "private"},
                    "from": {"id": 99, "username": "sellername"},
                }
            }
        )
    )

    assert response.handled is True
    assert response.result == "registration_error"
    assert telegram.messages == [
        ("100", "Ссылка регистрации истекла. Начните регистрацию заново в Seller Panel.")
    ]


def test_seller_bot_webhook_route_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: FakeWebhookService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook/wrong",
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_bot_webhook_route_requires_secret_header_on_safe_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: FakeWebhookService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook",
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_bot_webhook_route_accepts_secret_header_without_path_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    fake_service = FakeWebhookService()
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: fake_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "registration_linked"}
    assert fake_service.update is not None


def test_seller_bot_webhook_route_accepts_secret_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    fake_service = FakeWebhookService()
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: fake_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook/secret",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_telegram_update_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "registration_linked"}
    assert fake_service.update is not None
    assert fake_service.update.message is not None
    assert fake_service.update.message.from_user is not None
    assert fake_service.update.message.from_user.username == "sellername"


def test_seller_bot_webhook_route_returns_200_for_oversized_block_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")
    service, seller_bot, telegram = _seller_command_webhook_service()
    app = create_app()
    app.dependency_overrides[get_seller_bot_webhook_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/telegram/seller-bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
                json=_seller_group_command_payload("/block_seller 999999999999999999999999"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True, "handled": True, "result": "seller_command_error"}
    assert seller_bot.blocked_user_ids == []
    assert "outside the supported range" in telegram.messages[0][1]


def test_seller_bot_webhook_secret_path_is_redacted_from_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "secret")

    redacted = redact_sensitive_path("/api/v1/telegram/seller-bot/webhook/secret")

    assert redacted == "/api/v1/telegram/seller-bot/webhook/<secret>"


def test_sensitive_tokens_are_redacted_from_log_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "seller-bot-token")
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", "webapp-bot-token")
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "seller-webhook-secret")

    redacted = redact_sensitive_text(
        "POST https://api.telegram.org/botseller-bot-token/sendMessage "
        "webapp-bot-token /api/v1/telegram/seller-bot/webhook/seller-webhook-secret"
    )

    assert "seller-bot-token" not in redacted
    assert "webapp-bot-token" not in redacted
    assert "seller-webhook-secret" not in redacted
    assert "/bot<redacted>/sendMessage" in redacted
    assert "/api/v1/telegram/seller-bot/webhook/<secret>" in redacted


def test_log_filter_redacts_uvicorn_access_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_seller_webhook_secret", "seller-webhook-secret")
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='127.0.0.1 - "POST %s HTTP/1.1" 200',
        args=("/api/v1/telegram/seller-bot/webhook/seller-webhook-secret",),
        exc_info=None,
    )

    SensitiveDataLogFilter().filter(record)

    message = record.getMessage()
    assert "seller-webhook-secret" not in message
    assert "/api/v1/telegram/seller-bot/webhook/<secret>" in message


class FakeWebhookService:
    def __init__(self) -> None:
        self.update: TelegramUpdate | None = None

    async def handle_update(self, update: TelegramUpdate) -> SellerBotWebhookResponse:
        self.update = update
        return SellerBotWebhookResponse(handled=True, result="registration_linked")


class FakeSellerBotCommandService:
    def __init__(self) -> None:
        self.blocked_user_ids: list[int] = []
        self.unblocked_user_ids: list[int] = []
        self.chetam_actor_ids: list[int | None] = []
        self.order_detail_requests: list[tuple[int, int | None]] = []
        self.shipped_order_ids: list[tuple[int, int | None]] = []
        self.actor_lookup_ids: list[int] = []
        self.actor_user_id: int | None = 42
        self.product_messages: list[str] = []
        self.product_exception: Exception | None = None

    def format_help_command(self, *, chat_id: int) -> str:
        return f"Help for {chat_id}: /chetam /orders <ID>"

    async def format_sellers_command(self, *, chat_id: int) -> str:
        return f"Seller list for {chat_id}"

    async def format_active_orders_command(self, *, chat_id: int) -> list[str]:
        return [f"Active orders for {chat_id}"]

    async def format_chetam_command(
        self,
        *,
        chat_id: int,
        actor_telegram_user_id: int | None,
    ) -> list[str]:
        self.chetam_actor_ids.append(actor_telegram_user_id)
        return [f"Chetam for {chat_id}", "Second page"]

    async def format_order_detail_command(
        self,
        *,
        chat_id: int,
        order_id: int,
        actor_telegram_user_id: int | None,
    ) -> list[str]:
        del chat_id
        self.order_detail_requests.append((order_id, actor_telegram_user_id))
        return [f"ID заказа: {order_id}\nСтатус заказа: В обработке"]

    def order_action_reply_markup(self, order_id: int) -> dict[str, object]:
        return {
            "inline_keyboard": [
                [
                    {"text": "SHIPPED", "callback_data": f"seller_order:ship:{order_id}"},
                    {"text": "CANCEL", "callback_data": f"seller_order:cancel:{order_id}"},
                ]
            ]
        }

    async def actor_user_id_for_telegram(self, telegram_user_id: int) -> int | None:
        self.actor_lookup_ids.append(telegram_user_id)
        return self.actor_user_id

    async def mark_order_shipped_command(
        self,
        *,
        chat_id: int,
        order_id: int,
        actor_telegram_user_id: int | None,
    ) -> list[str]:
        del chat_id
        self.shipped_order_ids.append((order_id, actor_telegram_user_id))
        return [f"ID заказа: {order_id}\nСтатус заказа: Отправлен"]

    async def block_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self.blocked_user_ids.append(target_user_id)
        return f"Seller #{target_user_id} has been blocked."

    async def unblock_seller_command(
        self,
        *,
        chat_id: int,
        target_user_id: int,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        self.unblocked_user_ids.append(target_user_id)
        return f"Seller #{target_user_id} has been unblocked."

    async def create_quick_product_draft_command(
        self,
        *,
        chat_id: int,
        message,
        actor_telegram_user_id: int | None,
        actor_username: str | None,
    ) -> str:
        del chat_id, actor_telegram_user_id, actor_username
        if self.product_exception is not None:
            raise self.product_exception
        title_line = (message.caption or "").splitlines()[1]
        self.product_messages.append(title_line.split(":", 1)[1].strip())
        return "Product draft created."

    def format_new_product_help_command(self, *, chat_id: int) -> str:
        del chat_id
        return (
            "Размеры одежды: XS, S, M, L, XL, XXL, 3XL, ONE_SIZE.\n"
            "Размеры обуви: европейские целые размеры EU 35-46. "
            "RU/EU/US/UK и половинные размеры не поддерживаются."
        )


def _webhook_service() -> tuple[
    SellerBotWebhookService,
    FakeSellerAuthRepository,
    FakeTelegramService,
]:
    telegram = FakeTelegramService()
    seller_auth_service = SellerAuthService(
        DummySession(),
        telegram_service=telegram,
        audit_service=FakeAuditService(),
        token_factory=lambda: "start-token",
        code_factory=lambda: "123456",
        now_factory=_now,
    )
    repository = FakeSellerAuthRepository()
    seller_auth_service.repository = repository
    return (
        SellerBotWebhookService(
            seller_auth_service=seller_auth_service,
            telegram_service=telegram,
        ),
        repository,
        telegram,
    )


def _seller_command_webhook_service() -> tuple[
    SellerBotWebhookService,
    FakeSellerBotCommandService,
    FakeTelegramService,
]:
    telegram = FakeTelegramService()

    class FakeSellerAuthService:
        telegram_service = telegram

    seller_bot = FakeSellerBotCommandService()
    return (
        SellerBotWebhookService(
            seller_auth_service=FakeSellerAuthService(),
            seller_bot_service=seller_bot,
            telegram_service=telegram,
        ),
        seller_bot,
        telegram,
    )


def _return_action_webhook_service(
    *,
    initial_status: ReturnRequestStatus = ReturnRequestStatus.PENDING,
    actor_user_id: int | None = 42,
) -> tuple[
    SellerBotWebhookService,
    FakeSellerBotCommandService,
    FakeReturnRequestsService,
    FakeTelegramService,
]:
    telegram = FakeTelegramService()

    class FakeSellerAuthService:
        telegram_service = telegram

    seller_bot = FakeSellerBotCommandService()
    seller_bot.actor_user_id = actor_user_id
    returns = FakeReturnRequestsService(initial_status=initial_status)
    return (
        SellerBotWebhookService(
            seller_auth_service=FakeSellerAuthService(),
            seller_bot_service=seller_bot,
            returns_service=returns,
            telegram_service=telegram,
        ),
        seller_bot,
        returns,
        telegram,
    )


def _start_payload() -> SellerRegistrationStartRequest:
    return SellerRegistrationStartRequest(
        email="seller@example.com",
        password="Password1",
        telegram_username="@sellername",
    )


def _telegram_update_payload() -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "text": "/start seller_token",
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99, "username": "sellername", "first_name": "Ada"},
        },
    }


def _seller_group_command_payload(text: str, *, chat_id: int = -100) -> dict[str, object]:
    return {
        "update_id": 10,
        "message": {
            "message_id": 20,
            "text": text,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": 500, "username": "approver"},
        },
    }


def _seller_group_command_update(text: str, *, chat_id: int = -100) -> TelegramUpdate:
    return TelegramUpdate.model_validate(_seller_group_command_payload(text, chat_id=chat_id))


def _seller_group_product_command_update() -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 11,
            "message": {
                "message_id": 21,
                "caption": "/new_product\nНазвание: White Hoodie\nЦена: 1990",
                "photo": [{"file_id": "photo", "width": 1200, "height": 1500}],
                "chat": {"id": -100, "type": "supergroup"},
                "from": {"id": 500, "username": "operator"},
            },
        }
    )


def _telegram_start_update() -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "text": "/start seller_start-token",
                "chat": {"id": 100, "type": "private"},
                "from": {
                    "id": 99,
                    "username": "sellername",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                },
            },
        }
    )


def _callback_update(
    callback_data: str,
    *,
    chat_id: int = -100,
    with_photo: bool = False,
) -> TelegramUpdate:
    message: dict[str, object] = {
        "message_id": 11,
        "chat": {"id": chat_id, "type": "supergroup"},
    }
    if with_photo:
        message["caption"] = "Проверка оплаты"
        message["photo"] = [
            {
                "file_id": "receipt-photo",
                "width": 800,
                "height": 600,
            }
        ]
    else:
        message["text"] = "approval"
    return TelegramUpdate.model_validate(
        {
            "update_id": 2,
            "callback_query": {
                "id": "callback-id",
                "from": {"id": 500, "username": "approver"},
                "message": message,
                "data": callback_data,
            },
        }
    )


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
