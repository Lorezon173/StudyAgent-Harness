"""共享教学服务的真实HTTP持久化；失败回复为空且状态可恢复。"""
from sqlalchemy import select,event
from tests.api.test_conversation_transactions import dbkit,api_client,headers,candidate_runner
from app.models.tables import SessionTable,MessageTable


def reply_runner(*args,**kwargs):
    result=candidate_runner()(*args,**kwargs)
    result.reply='这是 AI 回复'
    result.teaching_state['last_question']=result.reply
    result.turn_count=11
    return result


def test_chat_persist_happy_path(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        async with await api_client(factory,monkeypatch) as client:
            app.state.conversation_service.runner=reply_runner
            response=await client.post('/api/chat',headers=headers(),json={'message':'帮我理解 RAG','session_id':'s-happy','user_id':1})
            data=response.json()
            assert response.status_code==200 and data['stack']=='new' and data['reply']=='这是 AI 回复' and data['persisted'] is True
        async with factory() as db:
            session=await db.get(SessionTable,'s-happy')
            assert session.title=='帮我理解 RAG' and session.user_id==1
            messages=list((await db.scalars(select(MessageTable).order_by(MessageTable.id))).all())
            assert [(m.role,m.content,m.turn_index) for m in messages]==[('user','帮我理解 RAG',0),('assistant','这是 AI 回复',0)]
    dbkit(check)


def test_chat_persist_second_turn(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        async with await api_client(factory,monkeypatch) as client:
            app.state.conversation_service.runner=reply_runner
            for text in ['第一个问题','第二个问题']:
                response=await client.post('/api/chat',headers=headers(2),json={'message':text,'session_id':'s-turn2','user_id':2})
                assert response.status_code==200 and response.json()['persisted']
        async with factory() as db:
            messages=list((await db.scalars(select(MessageTable).order_by(MessageTable.id))).all())
            assert len(messages)==4 and [m.turn_index for m in messages]==[0,0,1,1]
            assert messages[2].role=='user' and messages[2].content=='第二个问题' and messages[3].role=='assistant'
            assert (await db.get(SessionTable,'s-turn2')).title=='第一个问题'
    dbkit(check)


def test_chat_persist_error_resilience(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        attempts=[]
        @event.listens_for(engine.sync_engine,'before_cursor_execute')
        def fail(conn,cursor,statement,params,context,many):
            if statement.startswith('INSERT INTO messages'):
                attempts.append(params)
                if len(attempts)==2:
                    raise RuntimeError('second message failed')
        async with await api_client(factory,monkeypatch) as client:
            app.state.conversation_service.runner=reply_runner
            response=await client.post('/api/chat',headers=headers(),json={'message':'测试错误恢复','session_id':'s-err'})
            data=response.json()
            assert response.status_code==200 and data['stack']=='new' and data['persisted'] is False
            assert data['reply']=='' and data['status']=='failed'
        async with factory() as db:
            assert list((await db.scalars(select(MessageTable))).all())==[]
    dbkit(check)


def test_chat_turn_count_is_teaching_round(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        async with await api_client(factory,monkeypatch) as client:
            app.state.conversation_service.runner=reply_runner
            response=await client.post('/api/chat',headers=headers(),json={'message':'hi','session_id':'sc1'})
            assert response.json()['turn_count']==1 and response.json()['persisted'] is True
    dbkit(check)
