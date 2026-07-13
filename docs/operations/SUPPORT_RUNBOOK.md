# Support runbook

## Triage

Collect order number, customer-visible error, timestamp, surface, app/browser version context and
request id if shown. Never request bot token, password, full initData, payment credential or unnecessary
return media. Verify customer ownership before disclosing order/payment/return details.

| Issue | Check | Safe response |
| --- | --- | --- |
| cannot authenticate | launched from Telegram, initData age, current Bot 1 | reopen Mini App; never paste initData |
| no Telegram update | `/start`, write access, opt-in, blocked state | explain service vs marketing |
| campaign not received | real Bot 1 private chat + marketing/service opt-in | channel entry alone is insufficient |
| promo rejected | code/window/usage/cart selection | delivery is not discounted |
| payment expired/rejected | payment state and seller review | seller contact; do not claim automatic refund |
| return unavailable | DELIVERED, delivered_at, 24h, item returnable, existing request | legal escalation if policy dispute |
| media missing | file path/volume/proxy | incident escalation; avoid re-uploading sensitive data casually |

Support owner, hours, channels and escalation SLA are `NOT APPROVED` and block supported commercial
launch. Customer FAQ: [../sales/CUSTOMER_SUPPORT_FAQ.md](../sales/CUSTOMER_SUPPORT_FAQ.md).

