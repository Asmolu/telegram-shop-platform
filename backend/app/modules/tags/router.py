from fastapi import APIRouter

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "tags", "status": "stub"}
