from fastapi import APIRouter, HTTPException

from app.models.schemas import KnowledgeCreateRequest, KnowledgeResponse
from app.infrastructure.storage.knowledge_store import KnowledgeStore

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
_store = KnowledgeStore()


@router.post("", response_model=KnowledgeResponse)
async def create_knowledge(req: KnowledgeCreateRequest):
    kid = await _store.create(req.name, req.description)
    item = await _store.get(kid)
    return KnowledgeResponse(**item)


@router.get("", response_model=list[KnowledgeResponse])
async def list_knowledge():
    items = await _store.list_all()
    return [KnowledgeResponse(**i) for i in items]


@router.delete("/{knowledge_id}")
async def delete_knowledge(knowledge_id: int):
    deleted = await _store.delete(knowledge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"status": "ok"}
