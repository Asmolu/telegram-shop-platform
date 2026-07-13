# Стратегия резервного копирования

**Статус:** внутренний policy summary, 13 июля 2026 года. Практические команды — [Backup and Restore](operations/BACKUP_AND_RESTORE.md), аварийный сценарий — [Disaster Recovery](operations/DISASTER_RECOVERY.md).

Защищаются PostgreSQL, необходимые uploads и данные конфигурации/версии для воспроизводимого восстановления; секреты резервируются отдельным защищенным процессом. PostgreSQL остается source of truth. Копия считается пригодной только после автоматической или документированной restore verification.

Текущие цели: daily 04:00 Europe/Moscow, local 3 days/max 20, remote 14 days/max 2, remote cadence 7, lock от параллельного запуска и state для cadence. Требуются шифрование, least-privilege credentials, off-host copy, мониторинг возраста последнего успешного backup, регулярный restore drill и согласованные RPO/RTO.

Migration revision фиксируется в backup/release evidence; текущий head среза — `20260713_0056`. Retention не заменяет legal deletion policy: удаление персональных данных и срок инерции backup должны быть утверждены отдельно.
