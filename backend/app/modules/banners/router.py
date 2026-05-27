from fastapi import APIRouter

router = APIRouter(prefix="/banners", tags=["banners"])


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "banners", "status": "stub"}
