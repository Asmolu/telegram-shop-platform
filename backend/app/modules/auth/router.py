from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "auth", "status": "stub"}
