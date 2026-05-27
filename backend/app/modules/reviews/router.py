from fastapi import APIRouter

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "reviews", "status": "stub"}
