from fastapi import APIRouter

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "telegram", "status": "stub"}
