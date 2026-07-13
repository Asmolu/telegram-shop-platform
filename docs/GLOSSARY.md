# Глоссарий

Статус: канонический. Последняя проверка: 2026-07-13. Конфиденциальность: Public.

| Термин | Значение в проекте |
| --- | --- |
| StyleXac | текущее production domain family и название платформы в репозиторных инструкциях |
| ICON STORE | текущее product/brand name |
| Customer | покупатель с ролью `USER` |
| Seller | оператор магазина с ролью `SELLER` |
| Admin | роль `ADMIN` с расширенным доступом |
| Mini App | мобильный React storefront внутри Telegram WebView или обычного browser |
| Seller Panel | desktop-first React dashboard |
| Bot 1 | customer bot: `/start`, `/stop`, notifications, campaigns, channel entry |
| Bot 2 | seller/admin/auth bot и operational callbacks |
| Look | комплект товаров; не имеет собственного stock |
| `ONE_SIZE` | size group, который не требует customer size selector |
| Manual payment | перевод по реквизитам с ручной проверкой продавцом |
| Outbox | PostgreSQL queue, атомарно создаваемая вместе с business state |
| Durable in-app notification | server-side notification row с `seen_at` |
| Service notification | транзакционное/операционное уведомление, не marketing consent |
| Campaign | массовая Bot 1 рассылка по eligible private chats |
| Source of truth | наиболее авторитетный источник факта; для данных — PostgreSQL |
| RPO / RTO | допустимая потеря данных / целевое время восстановления; пока не утверждены |

