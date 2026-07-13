# StyleXac — продуктовый one-pager

## Что это

StyleXac — модульная commerce-платформа для продаж через Telegram: мобильный Mini App для покупателя, desktop Seller Panel для магазина, два специализированных Telegram-бота и FastAPI backend. Каталог, образы (Looks), заказы, ручная оплата СБП, доставка, возвраты, отзывы, уведомления и аналитические события объединены в одной системе.

## Ценность

Покупатель проходит путь от discovery до статуса заказа внутри знакомого Telegram-контекста. Продавец управляет ассортиментом, stock, заказами, платежами, возвратами, кампаниями и channel entry из отдельной панели. PostgreSQL остается источником истины, а критические операции выполняются транзакционно и журналируются.

## Отличительные возможности

- mobile-first Mini App и отдельный desktop-first Seller Panel;
- товарные варианты, `ONE_SIZE`, скрытые активные компоненты Looks;
- атомарный checkout с неизменяемым снимком позиции заказа;
- ручной payment lifecycle с 30-минутным окном;
- частичные возвраты и контролируемое восстановление stock;
- Bot 1 для customer lifecycle, Bot 2 для seller/admin/auth;
- durable outbox и in-app уведомления;
- production compose, Alembic, backup/restore runbooks.

## Текущий статус

Репозиторий имеет рабочую реализацию и существенное тестовое покрытие; текущий migration head — `20260713_0056`. Коммерческий запуск требует закрыть legal/security/operations acceptance, проверить production-конфигурацию без раскрытия секретов и выполнить smoke/UAT по [Seller Acceptance Checklist](SELLER_ACCEPTANCE_CHECKLIST.md). Это не утверждение о сертификации или юридической готовности.

