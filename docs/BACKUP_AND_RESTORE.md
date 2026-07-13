# Резервное копирование и восстановление

**Срез:** 13 июля 2026 года. Канонический runbook — [Operations Backup and Restore](operations/BACKUP_AND_RESTORE.md).

Целевой intent: ежедневный запуск в 04:00 Europe/Moscow; local retention 3 дня и максимум 20 копий; remote retention 14 дней и максимум 2; remote upload cadence 7. Механизм использует lock/state и обязательную restore verification. Конкретный pre-deploy backup подтвержден локально и успешно проверен восстановлением; remote upload для него был skipped по состоянию/политике. Это не подтверждает доступность всех последующих backup.

Production операции выполняются только через утвержденный service:
```bash
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

Не публиковать пути с credentials, dumps и содержимое пользовательских данных. Repository template с `/opt/TelegramShopPlatform` не устанавливать verbatim: текущий production path — `/opt/telegram-shop`. Восстановление репетируется в изолированной БД; RPO/RTO подтверждаются drill evidence.
