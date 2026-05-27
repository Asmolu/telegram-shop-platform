from fastapi import APIRouter

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "cart", "status": "stub"}
