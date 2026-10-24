from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.storage.library_store import LibraryStore
from app.models.schemas import KnowledgeCreateRequest, KnowledgeResponse
from app.models.workspace_schemas import LibraryUpdate

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("", response_model=KnowledgeResponse)
async def create_knowledge(req: KnowledgeCreateRequest, db: AsyncSession = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    try:
        item = await LibraryStore(db).create(current_user["user_id"], req.model_dump())
        response = KnowledgeResponse.model_validate(item)
        await db.commit()
        return response
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail="画像不存在") from exc
    except Exception:
        await db.rollback()
        raise


@router.get("", response_model=list[KnowledgeResponse])
async def list_knowledge(q: str | None = Query(None, max_length=256),
                         profile_id: str | None = Query(None, max_length=36),
                         limit: int = Query(50, ge=1, le=100), before_id: int | None = Query(None, gt=0),
                         db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return await LibraryStore(db).list(current_user["user_id"], q, profile_id, limit, before_id)


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(knowledge_id: int, db: AsyncSession = Depends(get_db),
                        current_user: dict = Depends(get_current_user)):
    item = await LibraryStore(db).get(current_user["user_id"], knowledge_id)
    if item is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return item


@router.patch("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(knowledge_id: int, req: LibraryUpdate, db: AsyncSession = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    try:
        item = await LibraryStore(db).update(current_user["user_id"], knowledge_id, req.model_dump(exclude_unset=True))
        if item is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        response = KnowledgeResponse.model_validate(item)
        await db.commit()
        return response
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail="画像不存在") from exc
    except Exception:
        await db.rollback()
        raise


@router.delete("/{knowledge_id}")
async def delete_knowledge(knowledge_id: int, db: AsyncSession = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    try:
        deleted = await LibraryStore(db).delete(current_user["user_id"], knowledge_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="知识库不存在")
        await db.commit()
        return {"status": "ok"}
    except Exception:
        await db.rollback()
        raise
