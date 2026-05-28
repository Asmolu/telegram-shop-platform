from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.cart.router import router as cart_router
from app.modules.categories.router import router as categories_router
from app.modules.orders.router import router as orders_router
from app.modules.products.router import router as products_router
from app.modules.promo_codes.router import router as promo_codes_router
from app.modules.tags.router import router as tags_router
from app.modules.uploads.router import router as uploads_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(cart_router)
api_router.include_router(orders_router)
api_router.include_router(promo_codes_router)
api_router.include_router(categories_router)
api_router.include_router(tags_router)
api_router.include_router(products_router)
api_router.include_router(uploads_router)
