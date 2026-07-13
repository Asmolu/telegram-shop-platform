# Security checklist перед коммерческим запуском

**Вердикт текущего среза:** техническая база присутствует, полная security acceptance не зафиксирована.

## Обязательно до запуска

- [ ] Утвердить threat model, владельцев рисков и допустимый остаточный риск.
- [ ] Провести независимый pentest публичного API, Mini App, Seller Panel и uploads.
- [ ] Проверить IDOR/BOLA для всех user/store-scoped объектов.
- [ ] Проверить HMAC, replay/freshness и разделение Bot 1/Bot 2.
- [ ] Утвердить CORS, CSP, HSTS, cookie/token и reverse-proxy headers.
- [ ] Включить secret scanning, dependency/SCA scanning и процесс CVE patching.
- [ ] Определить malware scanning, quarantine и авторизованную раздачу вложений.
- [ ] Проверить rate limits на edge и в приложении под распределенной нагрузкой.
- [ ] Ротировать production secrets перед launch и зафиксировать владельцев.
- [ ] Провести backup restore drill и подтвердить RPO/RTO.
- [ ] Настроить alerting и security incident contacts.
- [ ] Проверить отсутствие секретов/PII в Git, логах, telemetry и документации.
- [ ] Утвердить privacy/legal документы и сроки хранения.
- [ ] Запретить или формализовать нелинейные переходы статусов заказа.
- [ ] Записать security sign-off с датой, релизом и исключениями.

После каждого существенного изменения auth, payments, uploads, RBAC, инфраструктуры или Telegram-интеграции checklist пересматривается. Незаполненный пункт не маскируется формулировкой «production-grade», а переносится в risk register с владельцем и сроком.
