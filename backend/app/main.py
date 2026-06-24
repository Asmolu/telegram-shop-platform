import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.monitoring import initialize_error_monitoring
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import close_redis_client
from app.core.request_logging import RequestLoggingMiddleware
from app.db.session import dispose_database_engine
from app.modules.customer_notifications.campaigns.worker import run_customer_campaign_worker
from app.modules.manual_payments.worker import run_manual_payment_expiration_worker
from app.modules.uploads.storage import ensure_upload_directories


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_upload_directories()
    worker_stop = asyncio.Event()
    worker_tasks: list[asyncio.Task[None]] = []
    if settings.customer_campaign_worker_enabled and settings.telegram_customer_bot_token:
        worker_tasks.append(asyncio.create_task(run_customer_campaign_worker(worker_stop)))
    if settings.manual_payment_expiration_worker_enabled:
        worker_tasks.append(
            asyncio.create_task(run_manual_payment_expiration_worker(worker_stop))
        )
    try:
        yield
    finally:
        worker_stop.set()
        if worker_tasks:
            await asyncio.gather(*worker_tasks)
        await close_redis_client()
        await dispose_database_engine()


def create_app() -> FastAPI:
    configure_logging()
    initialize_error_monitoring()
    ensure_upload_directories()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.middleware("http")
    async def upload_cache_headers(request, call_next):
        response = await call_next(request)
        _set_upload_cache_headers(request.url.path, response.headers)
        return response

    app.mount(
        settings.public_uploads_mount_path,
        StaticFiles(directory=settings.uploads_dir_path),
        name="uploads",
    )

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def _set_upload_cache_headers(path: str, headers) -> None:
    mount_path = settings.public_uploads_mount_path.rstrip("/") or "/uploads"
    if not path.startswith(f"{mount_path}/"):
        return

    relative_path = path.removeprefix(f"{mount_path}/")
    if relative_path.startswith("payment_receipts/"):
        headers["Cache-Control"] = "private, no-store"
        return

    if _is_product_derivative_path(relative_path):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return

    if "Cache-Control" not in headers:
        headers["Cache-Control"] = "no-cache"


def _is_product_derivative_path(relative_path: str) -> bool:
    return relative_path.startswith("products/") and relative_path.endswith(
        (".thumbnail.webp", ".card.webp", ".detail.webp")
    )
