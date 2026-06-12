from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.tables import SessionTable, MasteryNodeTable

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{user_id}")
async def get_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    sessions = await db.scalar(
        select(func.count()).select_from(SessionTable)
        .where(SessionTable.user_id == user_id)
    ) or 0

    avg = await db.scalar(
        select(func.avg(MasteryNodeTable.mastery))
        .where(MasteryNodeTable.user_id == str(user_id))
    )
    avg_mastery = int(round(avg)) if avg is not None else 0

    return {"user_id": user_id, "stats": {"sessions": sessions, "avg_mastery": avg_mastery}}
