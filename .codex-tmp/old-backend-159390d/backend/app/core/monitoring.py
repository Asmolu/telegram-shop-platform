import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def initialize_error_monitoring() -> None:
    if not settings.error_monitoring_enabled:
        return

    if not settings.sentry_dsn:
        logger.warning("Error monitoring is enabled but SENTRY_DSN is not configured")
        return

    logger.info("Error monitoring configured", extra={"provider": "sentry_placeholder"})
