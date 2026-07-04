# Telegram Channel Entry

Channel entry is the flow that lets a seller/admin publish a pinned Telegram channel message that opens the StyleXac Mini App with a `startapp` parameter.

## Current Entry Points

| Area | Value |
| --- | --- |
| Seller Panel route | `/channel-entry` |
| API module | `backend/app/modules/channel_entry` |
| Bot used | Bot 1 customer bot |
| Default start parameter | `channel_pin` |
| Current URL button | `https://t.me/CheckYouStyleBot?startapp=channel_pin` |

If `TELEGRAM_MINI_APP_SHORT_NAME` is configured, the backend direct-link builder can use the Telegram short-name Mini App path. Otherwise it builds the bot username link with `startapp`.

## Bot Responsibility

Channel entry is a buyer-facing entry surface and therefore uses Bot 1. Bot 2 is reserved for seller/admin/auth-related flows and must not publish buyer channel-entry messages.

## Message Publication Flow

1. Seller/admin opens Seller Panel route `/channel-entry`.
2. Seller/admin selects or enters a channel target.
3. Backend validates the channel chat id.
4. Backend builds the Mini App URL with the configured start parameter.
5. Backend asks Bot 1 to send the channel message.
6. Backend optionally asks Bot 1 to pin the message.
7. Backend stores history with Telegram `message_id`, pin state, publish state, and sanitized error fields.

Supported channel chat id formats:

- public channel username, for example `@stylexac_channel`
- Telegram channel id with `-100` prefix

## Button Type

Telegram channel posts must use an inline URL button.

Do not use Telegram `web_app` buttons for channel posts. `web_app` buttons are not the channel-entry mechanism used by the current implementation.

## Auth and Customer State

When a user enters from a channel message, Mini App Telegram `initData` auth can create or update a backend `User`. This does not by itself create a real private Bot 1 chat because the user has not necessarily opened a private chat with Bot 1.

Notification eligibility after channel entry works through one of two paths:

- the user opens Bot 1 private chat and sends `/start`, creating real private chat state
- the user grants Mini App write access, and the backend records `write_access_granted=true`

Service notification delivery prefers `telegram_chat_id` from a real private chat. If no real private chat exists, current backend logic can use `telegram_user_id` when write access is granted.

Campaign delivery is stricter: current campaign delivery requires a real private Bot 1 chat and eligible opt-in state.

## Configuration

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_CUSTOMER_BOT_TOKEN` | Bot 1 token used to publish and pin channel messages |
| `TELEGRAM_CUSTOMER_BOT_USERNAME` | Bot 1 username used for fallback direct links |
| `TELEGRAM_MINI_APP_SHORT_NAME` | Optional Mini App short-name path |
| `TELEGRAM_CHANNEL_ENTRY_START_PARAM` | Start parameter, default `channel_pin` |

Use placeholders only in documentation:

```text
TELEGRAM_CUSTOMER_BOT_TOKEN=<BOT_TOKEN>
TELEGRAM_CUSTOMER_BOT_USERNAME=CheckYouStyleBot
TELEGRAM_MINI_APP_SHORT_NAME=<SECRET>
TELEGRAM_CHANNEL_ENTRY_START_PARAM=channel_pin
```

## Operational Checks

After deploying channel-entry changes:

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=250 backend
```

Smoke the public surfaces:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

Use Seller Panel `/channel-entry` to publish a test message only to an approved operational channel. Do not use production customer channels for destructive tests.

## Troubleshooting

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Publish fails with Telegram auth error | Bot 1 token is missing or invalid | Confirm `TELEGRAM_CUSTOMER_BOT_TOKEN` on server without printing it |
| Publish fails with chat error | Bot 1 is not an admin in the channel or chat id is wrong | Check channel admin permissions and channel id format |
| Pin fails but message publishes | Bot 1 lacks pin permission | Grant pin permission or publish without pin |
| User receives no order notification after channel entry | No private chat and no write access | Ask user to grant write access in Mini App or open Bot 1 private chat |
| Campaign does not target channel-entry user | Campaign delivery requires real private chat | Confirm Bot 1 `/start` private-chat subscription exists |
