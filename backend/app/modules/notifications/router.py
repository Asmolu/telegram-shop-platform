from fastapi import APIRouter

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "notifications", "status": "stub"}
