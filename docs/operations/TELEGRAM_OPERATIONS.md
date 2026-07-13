# Telegram operations

Maintain two separate bots and three Bot 2 chat purposes (orders, returns, backup). Verify webhook
URLs/secrets without printing secret values. Use repository diagnostics script only with authorized
environment and sanitized output.

Channel entry requires Bot 1 admin permission to post/pin, configured channel, Mini App short name
when used and URL `startapp` button. Bot private message requires prior bot interaction or granted
write access for service; campaign always requires real private chat.

During 403 mark blocked state where code supports it; during 429 honor retry-after. Do not manually
move Customer flows to Bot 2.

