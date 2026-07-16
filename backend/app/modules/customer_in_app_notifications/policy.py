from app.db.models import (
    CustomerInAppNotificationCategory,
    ManualPaymentStatus,
    OrderStatus,
)

SUPPRESSED_NOTIFICATION_KEYS = frozenset(
    {
        (
            CustomerInAppNotificationCategory.ORDER,
            OrderStatus.PROCESSING.value,
        ),
        (
            CustomerInAppNotificationCategory.PAYMENT,
            ManualPaymentStatus.SUBMITTED.value,
        ),
    }
)


def is_suppressed_notification(
    category: CustomerInAppNotificationCategory,
    event_code: str,
) -> bool:
    return (category, event_code) in SUPPRESSED_NOTIFICATION_KEYS
