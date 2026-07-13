# Seller acceptance checklist

**Среда:** согласованная staging/pre-production, не production без отдельного разрешения. Для каждого пункта сохраняются результат, дата и ответственный без персональных demo-данных.

## Покупатель

- [ ] Bot 1 `/start`/`/stop`, write access и marketing opt-in ведут себя раздельно.
- [ ] Каталог, search, filters, detail, favorites и Look работают на целевых устройствах.
- [ ] Варианты одежды/обуви и `ONE_SIZE` выбираются корректно.
- [ ] Cart/checkout валидируют stock, address, height/weight, coupon и delivery price.
- [ ] Order snapshot/number/totals корректны; СБП показывает срок 30 минут.
- [ ] In-app и service notifications соответствуют событиям.
- [ ] Review доступен только после покупки и проходит модерацию.
- [ ] Return/refund UX соответствует утвержденной политике.

## Продавец и операции

- [ ] Seller видит только свой scope; admin действия определены.
- [ ] Product/listing/variant/stock операции корректны и audited где критично.
- [ ] Payment approve/reject/expire корректно меняет заказ и stock.
- [ ] Fulfillment status и delivered timestamp согласованы с процессом.
- [ ] Partial return/refund и повторная обработка не дублируют restock.
- [ ] Campaign требует eligible opt-in/private chat; channel entry использует Bot 1.
- [ ] Backup restore drill, monitoring, alerting и support escalation приняты.
- [ ] Legal/security checklists подписаны; известные ограничения приняты письменно.

