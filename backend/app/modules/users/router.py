from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "users", "status": "stub"}
