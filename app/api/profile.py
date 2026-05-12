from fastapi import APIRouter

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{user_id}")
async def get_profile(user_id: int):
    return {"user_id": user_id, "stats": {"sessions": 0, "avg_mastery": 0}}
