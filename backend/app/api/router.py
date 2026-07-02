from fastapi import APIRouter

from app.modules.analytics.router import dashboard_router
from app.modules.analytics.router import router as analytics_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.banners.router import router as banners_router
from app.modules.cart.router import router as cart_router
from app.modules.categories.router import router as categories_router
from app.modules.channel_entry.router import router as channel_entry_router
from app.modules.customer_notifications.campaigns.router import (
    router as customer_notification_campaigns_router,
)
from app.modules.customer_notifications.router import router as customer_notifications_router
from app.modules.favorites.router import router as favorites_router
from app.modules.looks.router import admin_router as looks_admin_router
from app.modules.looks.router import public_router as looks_public_router
from app.modules.manual_payments.router import customer_router as manual_payments_customer_router
from app.modules.manual_payments.router import seller_router as manual_payments_seller_router
from app.modules.notifications.router import router as notifications_router
from app.modules.orders.router import router as orders_router
from app.modules.products.router import router as products_router
from app.modules.promo_codes.router import router as promo_codes_router
from app.modules.returns.router import admin_router as returns_admin_router
from app.modules.returns.router import customer_router as returns_customer_router
from app.modules.reviews.router import product_reviews_router
from app.modules.reviews.router import router as reviews_router
from app.modules.seller_auth.router import router as seller_auth_router
from app.modules.seller_bot.router import router as seller_bot_router
from app.modules.tags.router import router as tags_router
from app.modules.telegram.router import router as telegram_router
from app.modules.uploads.router import router as uploads_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(dashboard_router)
api_router.include_router(analytics_router)
api_router.include_router(audit_router)
api_router.include_router(auth_router)
api_router.include_router(seller_auth_router)
api_router.include_router(seller_bot_router)
api_router.include_router(telegram_router)
api_router.include_router(users_router)
api_router.include_router(banners_router)
api_router.include_router(cart_router)
api_router.include_router(orders_router)
api_router.include_router(returns_customer_router)
api_router.include_router(returns_admin_router)
api_router.include_router(looks_admin_router)
api_router.include_router(looks_public_router)
api_router.include_router(manual_payments_customer_router)
api_router.include_router(manual_payments_seller_router)
api_router.include_router(promo_codes_router)
api_router.include_router(reviews_router)
api_router.include_router(product_reviews_router)
api_router.include_router(favorites_router)
api_router.include_router(notifications_router)
api_router.include_router(categories_router)
api_router.include_router(channel_entry_router)
api_router.include_router(customer_notifications_router)
api_router.include_router(customer_notification_campaigns_router)
api_router.include_router(tags_router)
api_router.include_router(products_router)
api_router.include_router(uploads_router)
