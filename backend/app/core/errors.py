import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.log_sanitization import redact_sensitive_path

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.message = message
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.error(
                "application error",
                extra=_request_log_extra(request),
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": [_serialize_validation_error(error) for error in exc.errors()]},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "database error",
            extra=_request_log_extra(request),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database service unavailable"},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled error",
            extra=_request_log_extra(request),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


def _serialize_validation_error(error: dict) -> dict:
    serialized = dict(error)
    ctx = serialized.get("ctx")
    if isinstance(ctx, dict) and "error" in ctx:
        serialized["ctx"] = {**ctx, "error": str(ctx["error"])}
    return serialized


def _request_log_extra(request: Request) -> dict[str, object]:
    return {
        "request_id": getattr(request.state, "request_id", None),
        "method": request.method,
        "path": redact_sensitive_path(request.url.path),
    }
