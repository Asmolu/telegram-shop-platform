# Сценарий демонстрации

**Длительность:** 20–30 минут. **Подготовка:** отдельные demo users, товары, stock, Look, coupon, Bot 1/Bot 2 и тестовые payment instructions; никаких production-персональных данных.

## 1. Контекст (2 минуты)

Покажите границы решения: Mini App покупателя, Seller Panel, backend, Bot 1 и Bot 2. Объясните, что текущий платеж — ручная СБП-проверка, а не эквайринг.

## 2. Покупатель (10 минут)

1. Открыть Mini App из Telegram/channel entry.
2. Показать feed, поиск, фильтры, favorites и detail активного товара.
3. Открыть Look, изменить выбранные компоненты и добавить подходящие варианты.
4. Оформить корзину: адрес, метод доставки, рост/вес, coupon; отметить отдельную стоимость доставки.
5. Показать заказ `ORD-xxxxxx`, инструкции СБП и 30-минутный срок.
6. Показать in-app/service notification и разницу write access/marketing opt-in.

## 3. Продавец (10 минут)

1. Показать dashboard, товар, варианты, stock и `is_listed`.
2. Открыть заказ, submitted payment, подтвердить его и перевести fulfillment status.
3. Показать delivered order, review moderation и return request.
4. Одобрить частичный возврат, создать ручной refund и показать delta-safe restock.
5. Показать campaign/channel entry и audit trail без реальной массовой отправки.

## 4. Завершение

Открыть [Commercial Scope](COMMERCIAL_SCOPE.md), назвать известные ограничения и согласовать пилот/UAT. Не менять production, не публиковать канал и не запускать кампанию во время demo без отдельного разрешения.

