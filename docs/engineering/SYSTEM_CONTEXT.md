# System context

| External actor/system | Exchange | Trust boundary |
| --- | --- | --- |
| Customer / Telegram WebView | initData, catalog/order/payment/return data | untrusted client; validate server-side |
| Seller/Admin browser | credentials/JWT, operational mutations | RBAC and audit boundary |
| Telegram Bot API | webhooks and sends | webhook secret + bot identity; external availability |
| Telegram channel | Bot 1 publish/pin and URL deep link | channel permissions |
| PostgreSQL | all durable business state | primary data boundary |
| Redis | cache/rate limits/temporary state | disposable relative to orders |
| Local uploads | images/payment/return evidence | sensitive file boundary |
| Yandex Disk | optional offsite backup | credentials/data transfer boundary |
| Sentry | optional error monitoring | only when configured; data-transfer review required |

No payment provider, carrier API, ERP or fiscal service is integrated. Source: config, modules and
dependency manifests.

