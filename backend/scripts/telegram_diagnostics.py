from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"
TELEGRAM_API_BASE_URL = "https://api.telegram.org"
BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ENV_KEYS = (
    "TELEGRAM_ORDERS_CHAT_ID",
    "TELEGRAM_RETURNS_CHAT_ID",
    "TELEGRAM_BACKUP_CHAT_ID",
    "TELEGRAM_SELLER_CHAT_ID",
)


class TelegramDiagnosticError(Exception):
    """Raised when a configured Telegram target cannot be verified."""


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_optional_quotes(value.strip())
    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def merged_env_values(env_file: Path) -> dict[str, str]:
    values = load_env_file(env_file)
    for key in (BOT_TOKEN_ENV, *CHAT_ENV_KEYS):
        env_value = os.getenv(key)
        if env_value is not None:
            values[key] = env_value
    return values


async def telegram_post(
    client: httpx.AsyncClient,
    *,
    bot_token: str,
    method: str,
    payload: dict[str, object],
) -> dict[str, object]:
    try:
        response = await client.post(
            f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/{method}",
            json=payload,
        )
    except httpx.HTTPError as exc:
        raise TelegramDiagnosticError(f"{method} request failed: {type(exc).__name__}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise TelegramDiagnosticError(f"{method} returned invalid JSON") from exc

    if not isinstance(body, dict):
        raise TelegramDiagnosticError(f"{method} returned invalid JSON")
    if response.status_code >= 400 or not body.get("ok", False):
        description = body.get("description") or f"HTTP {response.status_code}"
        raise TelegramDiagnosticError(f"{method} failed: {description}")
    return body


async def run_diagnostics(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file).resolve()
    values = merged_env_values(env_file)
    bot_token = (values.get(BOT_TOKEN_ENV) or "").strip()
    print(f"Env file: {env_file}")
    print(f"{BOT_TOKEN_ENV}: {'configured' if bot_token else 'missing'}")
    if not bot_token:
        print(f"error: {BOT_TOKEN_ENV} is required for Telegram diagnostics", file=sys.stderr)
        return 1

    failed = False
    timeout = httpx.Timeout(args.timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            bot = await telegram_post(client, bot_token=bot_token, method="getMe", payload={})
        except TelegramDiagnosticError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        result = bot.get("result")
        username = result.get("username") if isinstance(result, dict) else None
        bot_id = result.get("id") if isinstance(result, dict) else None
        print(f"getMe: ok username={username or '-'} id={bot_id or '-'}")

        for key in CHAT_ENV_KEYS:
            chat_id = (values.get(key) or "").strip()
            if not chat_id:
                print(f"{key}: skipped (not configured)")
                continue
            try:
                chat = await telegram_post(
                    client,
                    bot_token=bot_token,
                    method="getChat",
                    payload={"chat_id": chat_id},
                )
            except TelegramDiagnosticError as exc:
                failed = True
                print(f"{key}: invalid ({exc})", file=sys.stderr)
                continue

            chat_result = chat.get("result")
            if not isinstance(chat_result, dict):
                failed = True
                print(f"{key}: invalid (getChat returned no chat metadata)", file=sys.stderr)
                continue
            title = chat_result.get("title") or chat_result.get("username") or "-"
            chat_type = chat_result.get("type") or "-"
            print(f"{key}: ok id={chat_id} type={chat_type} title={title}")

            if args.send:
                await telegram_post(
                    client,
                    bot_token=bot_token,
                    method="sendMessage",
                    payload={
                        "chat_id": chat_id,
                        "text": args.message,
                        "disable_web_page_preview": True,
                    },
                )
                print(f"{key}: test message sent")

    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify configured Bot 2 Telegram chats.")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Backend env file to load; process environment overrides matching keys.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send a test message to each configured and valid chat.",
    )
    parser.add_argument(
        "--message",
        default="Telegram diagnostics test message.",
        help="Message text used only with --send.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="Telegram API timeout.",
    )
    return parser.parse_args()


def main() -> int:
    return asyncio.run(run_diagnostics(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
