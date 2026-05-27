from fastapi import APIRouter

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "categories", "status": "stub"}
