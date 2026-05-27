from fastapi import APIRouter

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "uploads", "status": "stub"}
