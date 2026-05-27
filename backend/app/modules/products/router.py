from fastapi import APIRouter

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "products", "status": "stub"}
