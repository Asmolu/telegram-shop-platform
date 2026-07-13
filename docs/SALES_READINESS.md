# Готовность к продаже

Статус: канонический. Последняя проверка: 2026-07-13. Конфиденциальность: Internal.

## Решение

Продукт можно показывать в контролируемой demo-среде и предлагать как внедрение с явно
согласованным scope. Нельзя продавать его как turnkey SaaS с автоматическими платежами,
утвержденным SLA или готовым legal/compliance package.

| Область | Статус | Sales-safe формулировка |
| --- | --- | --- |
| Storefront, catalog, Looks, cart, checkout | Implemented and deployed | «Развернутый Telegram storefront с каталогом и комплектами» |
| Orders и stock transaction | Implemented and deployed | «Транзакционный checkout с атомарным списанием stock» |
| Payment | Implemented, manual | «Ручная оплата по СБП с подтверждением продавцом» |
| Returns | Implemented; legal review required | «Workflow заявок, ручного refund record и optional restock» |
| Notifications | Implemented and deployed | «Bot 1 и durable in-app status notifications» |
| Campaigns | Implemented; audience constraints | «Рассылки только eligible Bot 1 private chats» |
| Backup | Local verified; offsite conditional | «Локальный проверяемый backup; remote upload по cadence/config» |
| Pricing | `NOT APPROVED` | Не называть цену без решения owner |
| SLA / RPO / RTO | `NOT APPROVED` | Не обещать доступность или сроки восстановления |
| Legal documents | `NEEDS BUSINESS DECISION` | Требуется qualified Russian lawyer |

## Блокеры безусловного запуска нового клиента

1. Утвердить legal documents, data retention/deletion и 24-hour return policy.
2. Утвердить pricing, support owner, SLA, RPO и RTO.
3. Согласовать manual payment/fiscal receipt model либо интегрировать provider.
4. Проверить tenant model: текущая система не документирована как multi-tenant SaaS.
5. Устранить systemd path drift и подтвердить offsite backup ownership.
6. Утвердить monitoring/alerting и production access matrix.

Канонические claims: [sales/FEATURE_EVIDENCE_MATRIX.md](sales/FEATURE_EVIDENCE_MATRIX.md).
Риски: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

