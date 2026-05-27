from fastapi import APIRouter

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "orders", "status": "stub"}
