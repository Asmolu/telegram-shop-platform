# Telegram integration

| Flow | Bot | Endpoint/entry | Rule |
| --- | --- | --- | --- |
| Mini App auth | configured WebApp/Bot 1 token | `/auth/telegram/login` | validate initData server-side |
| Customer `/start`/`/stop` | Bot 1 | customer webhook | private subscription state |
| Service notifications | Bot 1 | outbox/customer service | chat preferred, write-access fallback |
| Campaigns | Bot 1 | campaign worker | real unblocked private chat + opt-in |
| Channel publish/pin | Bot 1 | `/channel-entry` seller API | URL `startapp`, not `web_app` button |
| Seller auth/actions | Bot 2 | seller webhook | role/identity/group/callback validation |
| Payment/return callbacks | Bot 2 | seller webhook | operational group separation |
| Backup status | Bot 2 token/script | systemd script | dedicated backup chat, legacy fallback |

Webhook setup scripts build current non-secret URL and set a secret header; legacy seller path with
secret remains for compatibility. Channel default start parameter is `channel_pin`. Opening channel
entry can create/update User through auth but never fabricates Bot 1 private-chat state.

Source: `telegram/router.py`, `telegram/service.py`, `customer_notifications/*`,
`channel_entry/*`, webhook scripts.

