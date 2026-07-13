# Подключение продавца

## До настройки

Назначить владельца магазина и операционные роли; собрать юридические реквизиты, support contacts, ассортимент/варианты/остатки, цены, изображения и права на контент, delivery geography, СБП-реквизиты, возвратную политику, Telegram bots/channel и branding. Секреты передавать только защищенным способом.

## Настройка

1. Создать/проверить магазин и seller/admin access.
2. Подключить Bot 1 к customer flows, Bot 2 к seller/admin/auth; не смешивать токены.
3. Настроить домены и environment variables без hardcode.
4. Импортировать категории, бренды, товары, варианты и stock; проверить `is_listed`.
5. Создать Looks и убедиться, что покупатель явно понимает выбранные компоненты.
6. Проверить delivery methods/prices, coupon и payment instructions.
7. Загрузить утвержденные customer/legal тексты.
8. Настроить support, monitoring, backup и escalation contacts.

## Обучение и пилот

Продавец проходит order/payment/fulfillment/return/refund, campaign opt-in, channel entry, review moderation и incident escalation. Затем выполняется [Seller Acceptance Checklist](SELLER_ACCEPTANCE_CHECKLIST.md) на тестовых данных. Launch разрешается только с подписанными product, technical, legal и operational acceptance.

