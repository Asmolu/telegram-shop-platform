from fastapi import APIRouter

router = APIRouter(prefix="/promo-codes", tags=["promo-codes"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "promo_codes", "status": "stub"}
