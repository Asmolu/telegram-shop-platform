from fastapi import APIRouter

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "statistics", "status": "stub"}
