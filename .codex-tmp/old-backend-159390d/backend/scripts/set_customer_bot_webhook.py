from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urljoin

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.modules.telegram.service import TelegramDeliveryError, TelegramService  # noqa: E402


def build_webhook_url(base_url: str) -> str:
    _required_webhook_secret()
    api_prefix = settings.api_v1_prefix.strip("/")
    path = f"{api_prefix}/telegram/customer-bot/webhook"
    return urljoin(base_url.rstrip("/") + "/", path)


def redact_secret(value: str) -> str:
    secret = settings.telegram_customer_webhook_secret
    if not secret:
        return value
    return value.replace(secret, "<secret>")


async def set_webhook(base_url: str) -> None:
    secret = _required_webhook_secret()
    service = _customer_telegram_service()
    await service.set_webhook(build_webhook_url(base_url), secret_token=secret)
    print("Customer Bot 1 webhook configured.")
    print(
        "Webhook path: "
        f"{settings.api_v1_prefix.rstrip('/')}/telegram/customer-bot/webhook"
    )


async def show_webhook_info() -> None:
    service = _customer_telegram_service()
    info = await service.get_webhook_info()
    printable = {
        "url": redact_secret(str(info.get("url") or "")),
        "pending_update_count": info.get("pending_update_count"),
        "last_error_date": info.get("last_error_date"),
        "last_error_message": info.get("last_error_message"),
        "max_connections": info.get("max_connections"),
        "allowed_updates": info.get("allowed_updates"),
    }
    for key, value in printable.items():
        print(f"{key}: {value}")


async def main_async(args: argparse.Namespace) -> int:
    if not settings.telegram_customer_bot_token:
        print("TELEGRAM_CUSTOMER_BOT_TOKEN is not configured.", file=sys.stderr)
        return 1

    try:
        if args.command == "set":
            await set_webhook(args.base_url)
        elif args.command == "info":
            await show_webhook_info()
    except TelegramDeliveryError as exc:
        print(f"Telegram API request failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _customer_telegram_service() -> TelegramService:
    return TelegramService(bot_token=settings.telegram_customer_bot_token)


def _required_webhook_secret() -> str:
    secret = settings.telegram_customer_webhook_secret
    if not secret:
        raise TelegramDeliveryError("TELEGRAM_CUSTOMER_WEBHOOK_SECRET is not configured")
    return secret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the Customer Bot 1 Telegram webhook.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_parser = subparsers.add_parser("set", help="Set the Customer Bot 1 webhook")
    set_parser.add_argument(
        "--base-url",
        required=True,
        help="Public backend base URL, for example https://api.stylexac.ru",
    )

    subparsers.add_parser("info", help="Show redacted Customer Bot 1 webhook info")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))
