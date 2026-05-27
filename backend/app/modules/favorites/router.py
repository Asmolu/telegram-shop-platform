from fastapi import APIRouter

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "favorites", "status": "stub"}
