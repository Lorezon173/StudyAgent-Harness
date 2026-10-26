"""原三类owner断言以真实JWT/Service/数据库验证，拒绝先于模型和SSE。"""
from sqlalchemy import select,func
from tests.api.test_conversation_transactions import dbkit,controlled,api_client,headers
from app.models.tables import SessionTable,MessageTable


def _check_owner(dbkit,monkeypatch,controlled,path,owner):
    async def check(factory,engine):
        async with factory() as db:
            db.add(SessionTable(id='owned',user_id=owner,state_json='{}'))
            await db.commit()
        async with await api_client(factory,monkeypatch) as client:
            response=await client.post(path,headers=headers(2),json={'session_id':'owned','message':'hi'})
            assert response.status_code==403
            assert response.json()=={'detail':'无权写入该会话'}
            assert controlled.calls==[]
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(MessageTable))==0
    dbkit(check)


def test_chat_rejects_null_owned_existing_session_before_generation(dbkit,monkeypatch,controlled):
    _check_owner(dbkit,monkeypatch,controlled,'/api/chat',None)


def test_chat_rejects_other_users_session_before_generation(dbkit,monkeypatch,controlled):
    _check_owner(dbkit,monkeypatch,controlled,'/api/chat',1)


def test_stream_rejects_other_users_session_before_sse(dbkit,monkeypatch,controlled):
    _check_owner(dbkit,monkeypatch,controlled,'/api/chat/stream',1)
