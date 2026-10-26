"""Task8: real transaction and public teaching request contracts."""
import pytest
from pydantic import ValidationError

from app.models.schemas import ChatRequest, ChatResponse
from app.api._dirty_flag import DirtyFlag


@pytest.mark.parametrize("body", [
    {"message": "x" * 4001}, {"message": 42},
    {"message": "x", "session_id": ""},
    {"message": "x", "request_id": ""},
    {"message": "x", "expected_state_version": True},
    {"message": "x", "expected_state_version": -1},
    {"message": "x", "profile_id": "not-a-uuid"},
])
def test_reject_invalid_teaching_request(body):
    with pytest.raises(ValidationError):
        ChatRequest(**body)


def test_original_message_and_finite_fractional_score():
    text = "  中文\n原文  "
    assert ChatRequest(message=text).message == text
    assert ChatRequest(message="x" * 4000).message == "x" * 4000
    assert ChatResponse(reply="ok", session_id="s", mastery_score=65.25).mastery_score == 65.25


def test_dirty_profiles_do_not_clear_other_profile_or_legacy():
    from app.infrastructure.storage.dirty_flag import DirtyFlag as InfraDirtyFlag
    import app.api._dirty_flag as api_flag
    import app.infrastructure.storage.dirty_flag as infra_flag
    assert DirtyFlag is InfraDirtyFlag
    assert api_flag._dirty_users is infra_flag._dirty_users and api_flag._lock is infra_flag._lock
    DirtyFlag._reset()
    DirtyFlag.mark_dirty(8)
    InfraDirtyFlag.mark_dirty(8, profile_id="a")
    DirtyFlag.mark_dirty(8, profile_id="b")
    DirtyFlag.clear_dirty(8, profile_id="a")
    assert not DirtyFlag.is_dirty(8, profile_id="a")
    assert DirtyFlag.is_dirty(8, profile_id="b")
    assert DirtyFlag.is_dirty(8)
    DirtyFlag._reset()
import asyncio
import json
from uuid import uuid4
from sqlalchemy import event, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.database import Base
from app.models.tables import UserTable, SessionTable, MessageTable
from app.models.workspace_tables import TopicProfileTable, ProfileNodeTable
from app.harness.teaching_context import TeachingState
from app.orchestration.session_service import SessionService


@pytest.fixture
def dbkit(tmp_path):
    async def run(check):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'task8.db'}", poolclass=NullPool)
        @event.listens_for(engine.sync_engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        try:
            async with engine.begin() as conn:
                assert await conn.scalar(__import__('sqlalchemy').text('PRAGMA foreign_keys')) == 1
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                db.add_all([UserTable(id=1, username='one', password_hash='x'), UserTable(id=2, username='two', password_hash='x')])
                await db.commit()
            await asyncio.wait_for(check(factory, engine), 25)
        finally:
            await engine.dispose()
    return lambda check: asyncio.run(run(check))


async def seed(factory, *, state=None, owner=1, bound=True):
    pid, aid, bid = [str(uuid4()) for _ in range(3)]
    async with factory() as db:
        db.add(TopicProfileTable(id=pid, user_id=1, name='subject'))
        await db.flush()
        db.add_all([ProfileNodeTable(id=aid, profile_id=pid, title='A'), ProfileNodeTable(id=bid, profile_id=pid, title='B')])
        await db.flush()
        data = TeachingState(active_node_id=aid, stage='awaiting_response', last_question='A question', committed_turn_count=1).to_dict() if state is None else state
        db.add(SessionTable(id='s', user_id=owner, profile_id=pid if bound else None, active_node_id=aid if bound else None,
                            state_json=json.dumps(data), next_turn_index=1))
        await db.flush()
        db.add_all([MessageTable(session_id='s', role='user', content='old answer', turn_index=0),
                    MessageTable(session_id='s', role='assistant', content='A question', turn_index=0)])
        await db.commit()
    return pid, aid, bid


@pytest.mark.parametrize('state,bound', [({}, True), ({'schema_version': 1}, False), ({'schema_version': 99}, False), ({'schema_version': 1, 'stage': []}, False)])
def test_legacy_wrapper_cannot_replace_workspace_state(dbkit, state, bound):
    async def check(factory, engine):
        from app.api._persist import persist_turn
        await seed(factory, state=state, bound=bound)
        writes = []
        @event.listens_for(engine.sync_engine, 'before_cursor_execute')
        def trace(conn, cursor, statement, params, context, many):
            if statement.lstrip().split()[0].upper() in {'UPDATE', 'INSERT', 'DELETE'}:
                writes.append(statement)
        class Graph:
            async def save(self):
                raise AssertionError('workspace may not save an old full graph')
        async with factory() as db:
            assert await persist_turn(db, 's', 1, 'new', 'reply', Graph()) is None
        assert writes == []
        async with factory() as db:
            row = await db.get(SessionTable, 's')
            assert json.loads(row.state_json) == state
            assert await db.scalar(select(func.count()).select_from(MessageTable)) == 2
    dbkit(check)


def test_switch_node_invalidates_pending_question_only_when_changed(dbkit):
    async def check(factory, engine):
        _, aid, bid = await seed(factory)
        async with factory() as db:
            await SessionService(db).set_active_node(1, 's', 0, aid)
            await db.commit()
        async with factory() as db:
            same = await db.get(SessionTable, 's')
            assert json.loads(same.state_json)['last_question'] == 'A question'
            assert same.state_version == 0
            await db.rollback()
            await SessionService(db).set_active_node(1, 's', 0, bid)
            await db.commit()
        async with factory() as db:
            changed = await db.get(SessionTable, 's')
            state = json.loads(changed.state_json)
            assert state['last_question'] is None
            assert state['stage'] == 'init'
            assert state['committed_turn_count'] == 1
            assert changed.state_version == 1
    dbkit(check)

@pytest.fixture
def controlled(monkeypatch):
    from tests.unit.orchestration.test_conversation_context import ControlledClient
    from app.infrastructure.llm import LLMService
    control = ControlledClient()
    monkeypatch.setattr(LLMService, 'llm', property(lambda self: control))
    monkeypatch.setattr('app.core.config.settings.rag_enabled', False)
    return control


async def api_client(factory, monkeypatch):
    from contextlib import asynccontextmanager
    from app.main import app
    from app.core.database import get_db
    import app.main as main
    async def initialized():
        pass
    async def database():
        async with factory() as db:
            yield db
    monkeypatch.setattr(main, 'init_db', initialized)
    monkeypatch.setattr(main, 'async_session', factory, raising=False)
    monkeypatch.setattr('app.api.chat.async_session', factory, raising=False)
    monkeypatch.setattr('app.api.chat_stream.async_session', factory, raising=False)
    app.dependency_overrides[get_db] = database
    @asynccontextmanager
    async def context():
        import httpx
        try:
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
    return context()


def headers(uid=1):
    from app.core.security import create_access_token
    return {'Authorization': 'Bearer ' + create_access_token(uid)}


def test_real_http_lifespan_atomic_state_and_replay(dbkit, monkeypatch, controlled):
    async def check(factory, engine):
        pid, aid, _ = await seed(factory)
        async with await api_client(factory, monkeypatch) as client:
            response = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'r1','message':'原文  \n中文','user_id':2})
            assert response.status_code == 200, response.text
            saved = response.json()
            assert saved['persisted'] is True
            assert saved['status'] == 'completed'
            assert saved['turn_count'] == 2
            assert saved['state_version'] == 1
            assert saved['profile_revision'] == 0
            assert saved['context_reduced'] is False
            assert saved['reduction_reasons'] == []
            calls = len(controlled.calls)
            replay = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'r1','message':'原文  \n中文'})
            assert replay.json() == saved
            assert len(controlled.calls) == calls
            conflict = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'r1','message':'改文'})
            assert conflict.status_code == 409
            messages = await client.get('/api/sessions/s/messages', headers=headers())
            assert [m['content'] for m in messages.json()][-2:] == ['原文  \n中文', saved['reply']]
    dbkit(check)


def test_real_http_uses_previous_question_in_actual_agent_prompt(dbkit, monkeypatch, controlled):
    async def check(factory, engine):
        await seed(factory)
        async with await api_client(factory, monkeypatch) as client:
            result = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'r','message':'现在回答'})
            assert result.status_code == 200
            assert any('A question' in messages[1].content and 'old answer' in messages[1].content for messages in controlled.calls)
    dbkit(check)

@pytest.mark.parametrize('owner,bound,code', [(None,False,403),(2,False,403),(1,False,409)])
def test_model_never_runs_for_inaccessible_or_unbound_session(dbkit, monkeypatch, controlled, owner, bound, code):
    async def check(factory, engine):
        await seed(factory, state={}, owner=owner, bound=bound)
        async with await api_client(factory, monkeypatch) as client:
            result = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'r','message':'hi'})
            assert result.status_code == code
            assert controlled.calls == []
    dbkit(check)


def test_unauthenticated_never_calls_model(dbkit, monkeypatch, controlled):
    async def check(factory, engine):
        async with await api_client(factory, monkeypatch) as client:
            result = await client.post('/api/chat', json={'message':'hi'})
            assert result.status_code == 401
            assert controlled.calls == []
    dbkit(check)


def test_new_client_id_gets_owned_default_container_without_old_graph(dbkit, monkeypatch, controlled):
    async def check(factory, engine):
        async with await api_client(factory, monkeypatch) as client:
            result = await client.post('/api/chat', headers=headers(), json={'session_id':'my-new-id','request_id':'r','message':'hi','user_id':2})
            assert result.json()['persisted'] is True
            assert result.json()['mastery_score'] is None
        async with factory() as db:
            row = await db.get(SessionTable, 'my-new-id')
            assert row.user_id == 1 and row.profile_id is not None
            profile = await db.get(TopicProfileTable, row.profile_id)
            assert profile.kind == 'legacy'
            assert await db.scalar(select(func.count()).select_from(ProfileNodeTable)) == 0
            assert json.loads(row.state_json)['committed_turn_count'] == 1
    dbkit(check)


def test_two_real_turns_then_old_http_and_sse_replay(dbkit, monkeypatch, controlled):
    async def check(factory, engine):
        _,_,bid = await seed(factory)
        async with await api_client(factory, monkeypatch) as client:
            first = (await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'one','message':'one'})).json()
            assert first['persisted'] is True
            second = await client.post('/api/chat/stream', headers=headers(), json={'session_id':'s','request_id':'two','message':'two'})
            frames = [json.loads(line[6:]) for line in second.text.splitlines() if line.startswith('data: ')]
            assert frames[-1]['type'] == 'final'
            assert frames[-1]['persisted'] is True and frames[-1]['turn_count'] == 3
            changed = await client.patch('/api/sessions/s/active-node', headers=headers(), json={'expected_state_version':2,'node_id':bid})
            assert changed.status_code == 200
            count = len(controlled.calls)
            replay = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'one','message':'one'})
            assert replay.json() == first
            stream = await client.post('/api/chat/stream', headers=headers(), json={'session_id':'s','request_id':'one','message':'one'})
            repeated = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
            assert repeated == [{'type':'final', **first}]
            explicit = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'one','message':'one','expected_state_version':0})
            assert explicit.json() == first
            for extra in ({'expected_state_version':1},{'profile_id':str(uuid4())}):
                conflict = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'one','message':'one',**extra})
                assert conflict.status_code == 409 and conflict.json()['detail']['code'] == 'payload_conflict'
            assert len(controlled.calls) == count
    dbkit(check)


def test_switch_b_old_a_answer_has_no_delta_until_b_new_question(dbkit, monkeypatch, controlled):
    controlled.responses['critic_assess'] = {'mastery_level':'partial','mastery_score':65.25,'mastery_rationale':'observed'}
    async def check(factory, engine):
        from app.models.workspace_tables import ProfileEvidenceTable
        pid, aid, bid = await seed(factory)
        async with await api_client(factory, monkeypatch) as client:
            changed = await client.patch('/api/sessions/s/active-node', headers=headers(), json={'expected_state_version':0,'node_id':bid})
            assert changed.status_code == 200
            response = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'b-first','message':'old A answer'})
            assert response.json()['persisted'] is True
            assert response.json()['turn_count'] == 2
            async with factory() as db:
                b = await db.get(ProfileNodeTable, bid)
                assert b.practice_count == 0 and b.mastery is None and b.revision == 0
                assert (await db.get(TopicProfileTable, pid)).revision == 0
                assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable)) == 0
            response = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'b-second','message':'B answer'})
            assert response.json()['persisted'] is True
            assert response.json()['mastery_score'] == 65.25
            async with factory() as db:
                assert (await db.get(ProfileNodeTable, bid)).practice_count == 1
                assert (await db.get(ProfileNodeTable, aid)).practice_count == 0
                assert (await db.get(TopicProfileTable, pid)).revision == 1
                assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable)) == 1
    dbkit(check)


def test_full_history_summary_uses_real_llm_and_preserves_extensions(dbkit, monkeypatch, controlled):
    async def check(factory, engine):
        pid, aid, _ = await seed(factory)
        checked=set()
        @event.listens_for(engine.sync_engine,'checkout')
        def out(connection,record,proxy):
            checked.add(id(connection))
        @event.listens_for(engine.sync_engine,'checkin')
        def into(connection,record):
            checked.discard(id(connection))
        original=controlled.invoke
        def invoke(messages):
            assert not checked, 'summary or Agent started with a checked out DB connection'
            return original(messages)
        monkeypatch.setattr(controlled,'invoke',invoke)
        async with factory() as db:
            row = await db.get(SessionTable, 's')
            state = json.loads(row.state_json)
            state.update(summary='previous', summary_until_message_id=None, extension={'nested':[True,None,2.5]})
            row.state_json = json.dumps(state)
            row.next_turn_index = 31
            await db.flush()
            for n in range(1,31):
                db.add_all([MessageTable(session_id='s', turn_index=n, role='user', content=f'old user {n}'),
                            MessageTable(session_id='s', turn_index=n, role='assistant', content=f'old assistant {n}')])
            await db.commit()
        async with await api_client(factory, monkeypatch) as client:
            response = await client.post('/api/chat', headers=headers(), json={'session_id':'s','request_id':'summary','message':'now'})
            assert response.json()['persisted'] is True
            summaries = [c for c in controlled.calls if '仅总结所提供' in c[0].content]
            assert len(summaries) == 1
            supplied = json.loads(summaries[0][1].content)['omitted_messages']
            assert len(supplied) == 50 and supplied[0]['content'] == 'old answer'
        async with factory() as db:
            state = json.loads((await db.get(SessionTable, 's')).state_json)
            assert state['summary_until_message_id'] == supplied[-1]['id']
            assert state['extension'] == {'nested':[True,None,2.5]}
    dbkit(check)

from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace as NS
from app.orchestration.conversation_service import ConversationService
from app.orchestration.assembly import NewStackResult
from app.harness.teaching_context import AssessmentDelta
from app.models.workspace_tables import ChatRequestTable, ProfileEvidenceTable, SessionViewStateTable
from app.infrastructure.storage.chat_request_store import WorkspaceConflict


def candidate_runner(*, score=None, duplicate=False, mutate=None, started=None, release=None):
    def runner(sid, uid, text, *, graph, on_event, context):
        if started:
            started()
        if release is not None:
            assert release.wait(15), 'test generation barrier timed out'
        state = context.state.to_dict()
        state.update(stage='awaiting_response',last_question='next question',summary=context.summary,
            summary_until_message_id=context.summary_until_message_id,committed_turn_count=context.state.committed_turn_count+1)
        deltas = [AssessmentDelta(context.active_node_id, score, 'actual evidence', 'source', question_message_id=context.question_message_id)] if score is not None and context.has_pending_question else []
        if duplicate and deltas:
            deltas.append(AssessmentDelta(context.active_node_id, 100, 'final', 'source2', question_message_id=context.question_message_id))
        result = NewStackResult('next question',score,99,['Socratic'],0,teaching_state=state,assessment_deltas=deltas)
        if mutate:
            mutate(result)
        return result
    return runner


@pytest.mark.parametrize('stage', ['second_message','evidence','delta','snapshot','complete','commit'])
def test_all_business_writes_rollback_at_each_failure_boundary(dbkit, monkeypatch, stage):
    async def check(factory, engine):
        pid, aid, _ = await seed(factory)
        fired = []
        @event.listens_for(engine.sync_engine, 'before_cursor_execute')
        def fail(conn,cursor,statement,params,context,many):
            sql = statement.lower()
            if sql.startswith('insert into messages'):
                conn.info['task8_business'] = True
                if stage == 'second_message' and params[1] == 'assistant':
                    fired.append(stage)
                    raise RuntimeError(stage)
            selected = (stage == 'evidence' and sql.startswith('insert into profile_evidence')
                or stage == 'delta' and sql.startswith('update profile_nodes')
                or stage == 'snapshot' and sql.startswith('update sessions') and 'state_json' in sql
                or stage == 'complete' and sql.startswith('update chat_requests') and 'response_json' in sql)
            if selected:
                fired.append(stage)
                raise RuntimeError(stage)
        @event.listens_for(engine.sync_engine, 'commit')
        def fail_commit(conn):
            if stage == 'commit' and conn.info.get('task8_business'):
                fired.append(stage)
                raise RuntimeError(stage)
        service = ConversationService(factory, runner=candidate_runner(score=65.25))
        result = await service.submit_turn(1, ChatRequest(session_id='s',request_id='fail',message='new answer'))
        assert result.persisted is False and result.status == 'failed' and result.reply == '' and result.turn_count is None
        assert fired == [stage]
        async with factory() as db:
            row = await db.get(SessionTable,'s')
            assert row.state_version == 0 and row.next_turn_index == 1 and row.active_request_id is None
            assert json.loads(row.state_json)['committed_turn_count'] == 1
            node = await db.get(ProfileNodeTable,aid)
            assert node.mastery is None and node.practice_count == 0 and node.revision == 0
            assert (await db.get(TopicProfileTable,pid)).revision == 0
            assert await db.scalar(select(func.count()).select_from(MessageTable)) == 2
            assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable)) == 0
            request = await db.get(ChatRequestTable,(1,'s','fail'))
            assert request.status == 'failed' and request.attempt == 2 and request.response_json is None
        await service.aclose()
    dbkit(check)


@pytest.mark.parametrize('score', [0,100,65.25])
def test_incremental_scores_once_and_only_one_final_business_commit(dbkit, score):
    async def check(factory, engine):
        pid, aid, bid = await seed(factory)
        commits = []
        @event.listens_for(engine.sync_engine,'before_cursor_execute')
        def mark(conn,cursor,statement,params,context,many):
            if statement.startswith('INSERT INTO messages'):
                conn.info['business'] = True
        @event.listens_for(engine.sync_engine,'commit')
        def committed(conn):
            if conn.info.get('business'):
                commits.append(True)
        service = ConversationService(factory,runner=candidate_runner(score=score))
        result = await service.submit_turn(1,ChatRequest(session_id='s',request_id='r',message='answer'))
        assert result.persisted and result.mastery_score == score and result.turn_count == 2
        assert commits == [True]
        async with factory() as db:
            node, other = await db.get(ProfileNodeTable,aid), await db.get(ProfileNodeTable,bid)
            assert (node.mastery,node.practice_count,node.revision)==(score,1,1)
            assert (other.mastery,other.practice_count,other.revision)==(None,0,0)
            evidence = (await db.scalars(select(ProfileEvidenceTable))).one()
            answer = await db.get(MessageTable,evidence.message_id)
            assert answer.role=='user' and answer.content=='answer' and evidence.score==score
            assert (await db.get(TopicProfileTable,pid)).revision == 1
    dbkit(check)


@pytest.mark.parametrize('field,value', [('question_message_id',999),('answer_message_id',999),('score',True),('score',float('nan')),('node_id','foreign')])
def test_forged_delta_never_partially_saves(dbkit, field, value):
    async def check(factory, engine):
        _, aid, _ = await seed(factory)
        service = ConversationService(factory,runner=candidate_runner(score=50,
            mutate=lambda result: setattr(result.assessment_deltas[0],field,value)))
        with pytest.raises(__import__('fastapi').HTTPException) as caught:
            await service.submit_turn(1,ChatRequest(session_id='s',request_id='bad',message='answer'))
        assert caught.value.status_code==409
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(MessageTable))==2
            assert (await db.get(ProfileNodeTable,aid)).practice_count==0
            assert (await db.get(ChatRequestTable,(1,'s','bad'))).status=='failed'
    dbkit(check)


def test_failed_resubmit_is_read_only_and_explicit_retry_keeps_original_payload(dbkit):
    async def check(factory, engine):
        await seed(factory)
        calls=[]
        def failed(*args,**kwargs):
            calls.append('failed')
            raise RuntimeError('controlled generation failure')
        service=ConversationService(factory,runner=failed)
        request=ChatRequest(session_id='s',request_id='r',message=' exact\noriginal ')
        first=await service.submit_turn(1,request)
        assert first.status=='failed' and first.attempt==2
        replay=await service.submit_turn(1,request)
        assert replay==first and calls==['failed']
        async with factory() as db:
            original=await db.get(ChatRequestTable,(1,'s','r'))
            payload,digest=original.request_payload,original.payload_hash
        service.runner=candidate_runner()
        done=await service.retry_turn(user_id=1,session_id='s',request_id='r',expected_attempt=2,expected_state_version=0)
        assert done.persisted and done.attempt==3
        async with factory() as db:
            row=await db.get(ChatRequestTable,(1,'s','r'))
            assert row.request_payload==payload and row.payload_hash==digest and row.base_state_version==0
        with pytest.raises(WorkspaceConflict):
            await service.retry_turn(user_id=1,session_id='s',request_id='r',expected_attempt=2,expected_state_version=0)
    dbkit(check)


class ManualClock:
    def __init__(self):
        self.value=0
        self.epoch=datetime.now(timezone.utc)
        self.pending=[]
        self.registered=asyncio.Event()
    def monotonic_now(self):
        return self.value
    def utc_now(self):
        return self.epoch+timedelta(seconds=self.value)
    async def wait_until(self,deadline):
        future=asyncio.get_running_loop().create_future()
        self.pending.append((deadline,future))
        self.registered.set()
        if self.value>=deadline:
            future.set_result(None)
        await future
    def advance(self,seconds):
        self.value+=seconds
        for deadline,future in self.pending:
            if deadline<=self.value and not future.done():
                future.set_result(None)


def test_renew_30_lease_180_deadline_300_and_late_worker_fence(dbkit):
    async def check(factory,engine):
        await seed(factory)
        clock=ManualClock()
        release=threading.Event()
        started=asyncio.Event()
        loop=asyncio.get_running_loop()
        service=ConversationService(factory,clock=clock,runner=candidate_runner(
            started=lambda:loop.call_soon_threadsafe(started.set),release=release))
        prepared=await service.prepare_request(1,ChatRequest(session_id='s',request_id='timed',message='answer'))
        task=asyncio.create_task(service.run_claim(prepared))
        try:
            await started.wait()
            await clock.registered.wait()
            clock.advance(30)
            for _ in range(100):
                async with factory() as db:
                    row=await db.get(ChatRequestTable,(1,'s','timed'))
                    renewed=row.lease_until==clock.epoch.replace(tzinfo=None)+timedelta(seconds=210)
                if renewed:
                    break
            assert renewed
            clock.advance(270)
            result=await task
            assert result.status=='interrupted' and result.error_code=='deadline_exceeded' and result.attempt==2
            release.set()
            async with factory() as db:
                assert await db.scalar(select(func.count()).select_from(MessageTable))==2
                assert (await db.get(SessionTable,'s')).active_request_id is None
            from app.orchestration.turn_commit import commit_turn
            loaded=NS()
            with pytest.raises(WorkspaceConflict):
                async with factory() as db:
                    await commit_turn(db,user_id=1,session_id='s',request_id='timed',attempt=1,
                        base_state_version=0,result=loaded,now=clock.utc_now())
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task,return_exceptions=True)
            await service.aclose()
    dbkit(check)


def test_get_snapshot_and_same_request_recover_expiry_in_real_transactions(dbkit,monkeypatch,controlled):
    async def check(factory,engine):
        await seed(factory)
        async with await api_client(factory,monkeypatch) as client:
            from app.main import app
            service=app.state.conversation_service
            service.clock=clock=ManualClock()
            prepared=await service.prepare_request(1,ChatRequest(session_id='s',request_id='expired',message='original'))
            first=await client.get('/api/sessions/s/requests/expired',headers=headers())
            assert first.json()['status']=='running' and first.json()['attempt']==1
            denied=await client.get('/api/sessions/s/snapshot',headers=headers(2))
            assert denied.status_code==403
            clock.advance(181)
            recovered=await client.get('/api/sessions/s/snapshot',headers=headers())
            assert recovered.status_code==200
            status=await client.get('/api/sessions/s/requests/expired',headers=headers())
            assert status.json()['status']=='interrupted' and status.json()['attempt']==2
            replay=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'expired','message':'original'})
            assert replay.json()['status']=='interrupted' and replay.json()['reply']==''
            assert controlled.calls==[]
    dbkit(check)


def test_model_and_summary_have_no_checked_out_connection(dbkit,monkeypatch,controlled):
    async def check(factory,engine):
        await seed(factory)
        checked=set()
        @event.listens_for(engine.sync_engine,'checkout')
        def out(connection,record,proxy):
            checked.add(id(connection))
        @event.listens_for(engine.sync_engine,'checkin')
        def into(connection,record):
            checked.discard(id(connection))
        original=controlled.invoke
        def invoke(messages):
            assert checked==set(), 'LLM invoked while physical DB connection is checked out'
            return original(messages)
        monkeypatch.setattr(controlled,'invoke',invoke)
        async with await api_client(factory,monkeypatch) as client:
            result=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'r','message':'answer'})
            assert result.json()['persisted']
    dbkit(check)


async def raw_asgi(app,path,body,disconnected,*,on_start=None):
    initial=True
    sent=[]
    async def receive():
        nonlocal initial
        if initial:
            initial=False
            return {'type':'http.request','body':json.dumps(body).encode(),'more_body':False}
        await disconnected.wait()
        return {'type':'http.disconnect'}
    async def send(message):
        sent.append(message)
        if message['type']=='http.response.start' and on_start:
            on_start()
    token=headers()['Authorization'].encode()
    scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.0'},'http_version':'1.1',
        'method':'POST','scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'',
        'root_path':'','server':('test',80),'client':('test',1),
        'headers':[(b'content-type',b'application/json'),(b'authorization',token)]}
    await app(scope,receive,send)
    return sent


async def retry_business_state(factory):
    """Business values must survive a cancelled retry byte-for-byte."""
    async with factory() as db:
        session=await db.get(SessionTable,'s')
        result={'session':(session.state_json,session.state_version,session.next_turn_index,session.active_node_id)}
        for table in (MessageTable,ProfileNodeTable,TopicProfileTable,ProfileEvidenceTable):
            rows=(await db.execute(select(table.__table__).order_by(*table.__table__.primary_key.columns))).mappings().all()
            result[table.__tablename__]=[dict(row) for row in rows]
        return result


async def establish_failed_retry(client,service,*,request_id='retry-disconnect'):
    def failed(*args,**kwargs):
        raise RuntimeError('controlled initial failure')
    service.runner=failed
    response=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':request_id,'message':'original answer'})
    assert response.status_code==200 and response.json()['status']=='failed' and response.json()['attempt']==2
    return f'/api/sessions/s/requests/{request_id}/retry'


async def assert_retry_state(factory,status,attempt,active):
    async with factory() as db:
        row=await db.get(ChatRequestTable,(1,'s','retry-disconnect'))
        assert (row.status,row.attempt)==(status,attempt)
        assert (await db.get(SessionTable,'s')).active_request_id==active
        print('ROUND2_RETRY_DB',status,attempt,'active',active,'messages',await db.scalar(select(func.count()).select_from(MessageTable)))


def test_retry_real_asgi_disconnect_interrupts_before_worker_release(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        from app.harness.events import Event
        from app.harness.enums import EventType,EventSource
        await seed(factory)
        release=threading.Event()
        started,finished,disconnected=asyncio.Event(),asyncio.Event(),asyncio.Event()
        loop=asyncio.get_running_loop()
        errors=[]
        previous=loop.get_exception_handler()
        loop.set_exception_handler(lambda loop,context:errors.append(context))
        def runner(sid,uid,text,*,graph,on_event,context):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(15)
            try:
                for _ in range(1000):
                    on_event(Event(type=EventType.TUTOR_ASKED,source=EventSource.TUTOR,session_id=sid,payload={'content':'late retry'}))
                return candidate_runner(score=65)(sid,uid,text,graph=graph,on_event=on_event,context=context)
            finally:
                loop.call_soon_threadsafe(finished.set)
        try:
            async with await api_client(factory,monkeypatch) as client:
                service=app.state.conversation_service
                path=await establish_failed_retry(client,service)
                before=await retry_business_state(factory)
                service.runner=runner
                task=asyncio.create_task(raw_asgi(app,path,{'expected_attempt':2,'expected_state_version':0},disconnected))
                try:
                    await asyncio.wait_for(started.wait(),5)
                    disconnected.set()
                    deadline=loop.time()+1
                    while loop.time()<deadline:
                        async with factory() as db:
                            row=await db.get(ChatRequestTable,(1,'s','retry-disconnect'))
                            if row.status=='interrupted':
                                break
                    await assert_retry_state(factory,'interrupted',4,None)
                    assert not release.is_set()
                    assert await retry_business_state(factory)==before
                    await asyncio.wait_for(task,5)
                    release.set()
                    await asyncio.wait_for(finished.wait(),5)
                    assert await retry_business_state(factory)==before
                    await assert_retry_state(factory,'interrupted',4,None)
                    assert errors==[]
                finally:
                    release.set()
                    await asyncio.gather(task,return_exceptions=True)
        finally:
            release.set()
            loop.set_exception_handler(previous)
    dbkit(check)


def test_retry_disconnected_before_generation_never_starts_runner(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        await seed(factory)
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            path=await establish_failed_retry(client,service)
            before=await retry_business_state(factory)
            calls=[]
            def runner(*args,**kwargs):
                calls.append(True)
                return candidate_runner(score=65)(*args,**kwargs)
            service.runner=runner
            disconnected=asyncio.Event()
            disconnected.set()
            await raw_asgi(app,path,{'expected_attempt':2,'expected_state_version':0},disconnected)
            await assert_retry_state(factory,'interrupted',4,None)
            assert calls==[]
            assert await retry_business_state(factory)==before
    dbkit(check)


def test_retry_task_cancel_after_management_commit_before_run_claim(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        await seed(factory)
        entered,release=asyncio.Event(),asyncio.Event()
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            path=await establish_failed_retry(client,service)
            before=await retry_business_state(factory)
            calls=[]
            service.runner=lambda *a,**kw:calls.append(True)
            original=service.run_claim
            async def entry(prepared,**kwargs):
                entered.set()
                await release.wait()
                return await original(prepared,**kwargs)
            monkeypatch.setattr(service,'run_claim',entry)
            task=asyncio.create_task(raw_asgi(app,path,{'expected_attempt':2,'expected_state_version':0},asyncio.Event()))
            try:
                await asyncio.wait_for(entered.wait(),5)
                await assert_retry_state(factory,'running',3,'retry-disconnect')
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await assert_retry_state(factory,'interrupted',4,None)
                assert calls==[] and await retry_business_state(factory)==before
            finally:
                release.set()
                await asyncio.gather(task,return_exceptions=True)
    dbkit(check)


@pytest.mark.parametrize('after_real_commit',[False,True])
def test_retry_management_commit_unknown_then_cancel(dbkit,monkeypatch,after_real_commit):
    async def check(factory,engine):
        from app.main import app
        from sqlalchemy.ext.asyncio import AsyncSession
        await seed(factory)
        entered,release=asyncio.Event(),asyncio.Event()
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            path=await establish_failed_retry(client,service)
            before=await retry_business_state(factory)
            calls=[]
            service.runner=lambda *a,**kw:calls.append(True)
            original=AsyncSession.commit
            armed=True
            async def commit(db):
                nonlocal armed
                if not armed:
                    return await original(db)
                armed=False
                if after_real_commit:
                    await original(db)
                entered.set()
                await release.wait()
                if not after_real_commit:
                    await original(db)
            monkeypatch.setattr(AsyncSession,'commit',commit)
            task=asyncio.create_task(raw_asgi(app,path,{'expected_attempt':2,'expected_state_version':0},asyncio.Event()))
            try:
                await asyncio.wait_for(entered.wait(),5)
                await assert_retry_state(factory,'running' if after_real_commit else 'failed',3 if after_real_commit else 2,'retry-disconnect' if after_real_commit else None)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await assert_retry_state(factory,'interrupted' if after_real_commit else 'failed',4 if after_real_commit else 2,None)
                assert calls==[] and await retry_business_state(factory)==before
            finally:
                release.set()
                await asyncio.gather(task,return_exceptions=True)
    dbkit(check)


def test_initial_disconnect_probe_propagates_parent_task_cancel_before_business():
    async def check():
        from starlette.requests import Request
        from app.api._disconnect import observe_http_disconnect
        loop=asyncio.get_running_loop()
        never=asyncio.Event()
        parent_task=None
        calls=0
        active,maximum=0,0
        cancel_requests,business_entered,receive_tasks=[],[],[]
        async def receive():
            nonlocal calls,active,maximum
            calls+=1
            if calls==1:
                return {'type':'http.request','body':b'{}','more_body':False}
            active+=1
            maximum=max(maximum,active)
            receive_tasks.append(asyncio.current_task())
            if calls==2:
                # 显式取消已捕获的父HTTP任务；修复后current_task是子probe。
                loop.call_soon(lambda:cancel_requests.append(parent_task.cancel()))
            try:
                await never.wait()
            finally:
                active-=1
        request=Request({'type':'http','method':'POST','path':'/test','headers':[]},receive)
        assert await request.body()==b'{}'
        async def handler():
            nonlocal parent_task
            parent_task=asyncio.current_task()
            async with observe_http_disconnect(request):
                business_entered.append(True)
                return 'business body ran'
        handler_task=asyncio.create_task(handler())
        rescue_used=False
        try:
            done,_=await asyncio.wait([handler_task],timeout=1)
            if handler_task not in done:
                rescue_used=True
                never.set()
                handler_task.cancel()
                done,_=await asyncio.wait([handler_task],timeout=1)
                assert handler_task in done, 'bounded parent rescue did not finish'
            outcome=(await asyncio.gather(handler_task,return_exceptions=True))[0]
        finally:
            pending={task for task in receive_tasks if not task.done()}
            if pending:
                rescue_used=True
                never.set()
                for task in pending:
                    task.cancel()
                _,pending=await asyncio.wait(pending,timeout=1)
                assert not pending, 'bounded receive-task rescue did not finish'
        print('ROUND3_INITIAL_CANCEL','cancel_requests',cancel_requests,'business_entered',business_entered,
            'outcome',type(outcome).__name__,'owned_done',all(task.done() for task in receive_tasks),
            'single_receive',maximum,'rescue_used',rescue_used)
        assert cancel_requests==[True]
        assert isinstance(outcome,asyncio.CancelledError), 'parent cancellation was swallowed before business entry'
        assert business_entered==[]
        assert receive_tasks and all(task.done() for task in receive_tasks)
        assert maximum==1 and active==0 and rescue_used is False
    asyncio.run(check())


@pytest.mark.parametrize('mode',['error','disconnected'])
def test_initial_disconnect_probe_failure_and_already_disconnected(mode):
    async def check():
        from starlette.requests import Request
        from app.api._disconnect import observe_http_disconnect
        calls=0
        active,maximum=0,0
        receive_tasks,business_entered=[],[]
        failure=ValueError('initial probe failed')
        async def receive():
            nonlocal calls,active,maximum
            calls+=1
            if calls==1:
                return {'type':'http.request','body':b'{}','more_body':False}
            active+=1
            maximum=max(maximum,active)
            receive_tasks.append(asyncio.current_task())
            try:
                if mode=='error':
                    raise failure
                return {'type':'http.disconnect'}
            finally:
                active-=1
        request=Request({'type':'http','method':'POST','path':'/test','headers':[]},receive)
        assert await request.body()==b'{}'
        async def handler():
            async with observe_http_disconnect(request) as disconnected:
                business_entered.append(disconnected.is_set())
                return 'body entered after observation'
        handler_task=asyncio.create_task(handler())
        rescue_used=False
        try:
            done,_=await asyncio.wait([handler_task],timeout=1)
            if handler_task not in done:
                rescue_used=True
                handler_task.cancel()
                done,_=await asyncio.wait([handler_task],timeout=1)
                assert handler_task in done, 'initial probe case did not finish after rescue'
            outcome=(await asyncio.gather(handler_task,return_exceptions=True))[0]
        finally:
            pending={task for task in receive_tasks if not task.done()}
            if pending:
                rescue_used=True
                for task in pending:
                    task.cancel()
                _,pending=await asyncio.wait(pending,timeout=1)
                assert not pending, 'initial probe owned task did not finish after rescue'
        if mode=='error':
            assert outcome is failure and business_entered==[]
        else:
            assert outcome=='body entered after observation' and business_entered==[True]
        assert calls==2 and len(set(receive_tasks))==1
        assert handler_task not in receive_tasks and all(task.done() for task in receive_tasks)
        assert maximum==1 and active==0 and rescue_used is False
        print('ROUND3_INITIAL_PROBE',mode,'business_entered',business_entered,'owned_done',True,
            'single_receive',maximum,'rescue_used',rescue_used)
    asyncio.run(check())


@pytest.mark.parametrize('mode',['normal','error','cancel'])
def test_http_disconnect_observer_awaits_watcher_with_single_receive(mode,monkeypatch):
    async def check():
        from starlette.requests import Request
        import app.api._disconnect as observer
        polled,stopped,never=asyncio.Event(),asyncio.Event(),asyncio.Event()
        loop=asyncio.get_running_loop()
        active,maximum=0,0
        samples=[]
        tasks=[]
        observed=[]
        receive_tasks=[]
        parent_task=None
        first=True
        async def receive():
            nonlocal first,active,maximum
            if first:
                first=False
                return {'type':'http.request','body':b'{}','more_body':False}
            active+=1
            maximum=max(maximum,active)
            samples.append(loop.time())
            receive_tasks.append(asyncio.current_task())
            if len(samples)>=3:
                polled.set()
            try:
                await never.wait()
            finally:
                active-=1
        request=Request({'type':'http','method':'POST','path':'/test','headers':[]},receive)
        assert await request.body()==b'{}'
        original=observer.watch_disconnect
        async def watched(request,event):
            tasks.append(asyncio.current_task())
            observed.append(event)
            try:
                await original(request,event)
            finally:
                stopped.set()
        monkeypatch.setattr(observer,'watch_disconnect',watched)
        async def work():
            nonlocal parent_task
            parent_task=asyncio.current_task()
            async with observer.observe_http_disconnect(request) as disconnected:
                assert not disconnected.is_set()
                await polled.wait()
                if mode=='error':
                    raise ValueError('business error survives observer cleanup')
                if mode=='cancel':
                    await never.wait()
                return 'done'
        task=asyncio.create_task(work())
        await asyncio.wait_for(polled.wait(),2)
        if mode=='cancel':
            task.cancel()
        done,_=await asyncio.wait([task],timeout=0.5)
        exited_before_rescue=task in done
        if not exited_before_rescue:
            # 只在观测失败之后救援，不能用退出信号伪造被测finally成功。
            observed[0].set()
            done,_=await asyncio.wait([task],timeout=2)
            assert task in done, 'observer rescue did not release the original task'
        if mode=='cancel':
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode=='error':
            with pytest.raises(ValueError,match='business error'):
                await task
        else:
            assert await task=='done'
        assert exited_before_rescue, 'watcher did not exit after cancellation; rescue event was required'
        assert stopped.is_set() and len(tasks)==1 and tasks[0].done()
        assert parent_task not in receive_tasks and len(set(receive_tasks))==2
        assert all(task.done() for task in receive_tasks)
        assert maximum==1 and active==0
        assert samples[2]-samples[1]>=0.08
        print('ROUND2_OBSERVER',mode,'single_receive',maximum,'watcher_done',tasks[0].done(),'poll_gap',samples[2]-samples[1])
        print('ROUND3_OBSERVER_OWNERS',mode,'owned_done',True,'rescue_used',not exited_before_rescue)
    asyncio.run(check())


def test_retry_connected_completes_once_and_replay_is_exact(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        await seed(factory)
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            path=await establish_failed_retry(client,service)
            calls=[]
            def runner(*args,**kwargs):
                calls.append(True)
                return candidate_runner(score=65)(*args,**kwargs)
            service.runner=runner
            response=await client.post(path,headers=headers(),json={'expected_attempt':2,'expected_state_version':0})
            saved=response.json()
            assert response.status_code==200 and saved['persisted'] is True and saved['attempt']==3
            assert saved['status']=='completed' and saved['turn_count']==2
            async with factory() as db:
                row=await db.get(ChatRequestTable,(1,'s','retry-disconnect'))
                assert row.response_json==saved and row.request_payload['message']=='original answer'
                assert await db.scalar(select(func.count()).select_from(MessageTable))==4
                assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable))==1
            replay=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'retry-disconnect','message':'original answer'})
            assert replay.json()==saved and calls==[True]
    dbkit(check)


@pytest.mark.parametrize('case,expected',[('anonymous',401),('foreign',403),('attempt',409),('base',409),('busy',409)])
def test_retry_precheck_errors_never_start_generation(dbkit,monkeypatch,case,expected):
    async def check(factory,engine):
        from app.main import app
        import app.api.sessions as route
        from contextlib import asynccontextmanager
        await seed(factory)
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            path=await establish_failed_retry(client,service)
            if case=='base':
                async with factory() as db:
                    session=await db.get(SessionTable,'s')
                    session.state_version=1
                    await db.commit()
            if case=='busy':
                async with factory() as db:
                    session=await db.get(SessionTable,'s')
                    session.active_request_id='retry-disconnect'
                    await db.commit()
            before=await retry_business_state(factory)
            observed,calls=[],[]
            original=route.observe_http_disconnect
            @asynccontextmanager
            async def observe(request):
                observed.append(True)
                async with original(request) as event:
                    yield event
            monkeypatch.setattr(route,'observe_http_disconnect',observe)
            service.runner=lambda *a,**kw:calls.append(True)
            response=await client.post(path,headers={} if case=='anonymous' else headers(2 if case=='foreign' else 1),
                json={'expected_attempt':1 if case=='attempt' else 2,'expected_state_version':0})
            assert response.status_code==expected
            assert calls==[] and observed==[]
            assert await retry_business_state(factory)==before
            async with factory() as db:
                row=await db.get(ChatRequestTable,(1,'s','retry-disconnect'))
                assert row.status=='failed' and row.attempt==2
                assert (await db.get(SessionTable,'s')).active_request_id==('retry-disconnect' if case=='busy' else None)
    dbkit(check)


@pytest.mark.parametrize('winner',['completed','new_attempt'])
def test_retry_cancel_cleanup_rechecks_after_read_before_session_lock(dbkit,monkeypatch,winner):
    async def check(factory,engine):
        from app.main import app
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.infrastructure.storage.chat_request_store import ChatRequestStore
        await seed(factory)
        entered,recheck,release=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            path=await establish_failed_retry(client,service)
            service.runner=candidate_runner(score=65)
            original_run,original_owned,original_exit=service.run_claim,service._owned,AsyncSession.__aexit__
            captured=[]
            async def entry(prepared,**kwargs):
                captured.append(prepared)
                entered.set()
                await asyncio.Event().wait()
            async def owned(db,*args,**kwargs):
                result=await original_owned(db,*args,**kwargs)
                if asyncio.current_task().get_coro().__qualname__.endswith('.cleanup'):
                    db.info['round2_cleanup_read']=True
                return result
            async def exited(db,*args):
                await original_exit(db,*args)
                if db.info.pop('round2_cleanup_read',False):
                    recheck.set()
                    await release.wait()
            monkeypatch.setattr(service,'run_claim',entry)
            monkeypatch.setattr(service,'_owned',owned)
            monkeypatch.setattr(AsyncSession,'__aexit__',exited)
            task=asyncio.create_task(raw_asgi(app,path,{'expected_attempt':2,'expected_state_version':0},asyncio.Event()))
            try:
                await asyncio.wait_for(entered.wait(),5)
                task.cancel()
                await asyncio.wait_for(recheck.wait(),5)
                if winner=='completed':
                    result=await original_run(captured[0])
                    assert result.persisted and result.attempt==3
                else:
                    async with factory() as db:
                        store=ChatRequestStore(db)
                        await store.interrupt(1,'s','retry-disconnect',3)
                        await store.retry(1,'s','retry-disconnect',4,0)
                        await db.commit()
                before=await retry_business_state(factory)
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await assert_retry_state(factory,'completed' if winner=='completed' else 'running',3 if winner=='completed' else 5,None if winner=='completed' else 'retry-disconnect')
                assert await retry_business_state(factory)==before
            finally:
                release.set()
                await asyncio.gather(task,return_exceptions=True)
    dbkit(check)


@pytest.mark.parametrize('path',['/api/chat','/api/chat/stream'])
def test_real_asgi_disconnect_interrupts_and_closes_late_worker_events(dbkit,monkeypatch,path):
    async def check(factory,engine):
        from app.main import app
        from app.harness.events import Event
        from app.harness.enums import EventType,EventSource
        await seed(factory)
        release=threading.Event()
        started,finished,disconnected=asyncio.Event(),asyncio.Event(),asyncio.Event()
        loop=asyncio.get_running_loop()
        errors=[]
        previous=loop.get_exception_handler()
        loop.set_exception_handler(lambda loop,context:errors.append(context))
        def runner(sid,uid,text,*,graph,on_event,context):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(15)
            try:
                for _ in range(1000):
                    on_event(Event(type=EventType.TUTOR_ASKED,source=EventSource.TUTOR,session_id=sid,payload={'content':'late'}))
                return candidate_runner()(sid,uid,text,graph=graph,on_event=on_event,context=context)
            finally:
                loop.call_soon_threadsafe(finished.set)
        try:
            async with await api_client(factory,monkeypatch):
                app.state.conversation_service.runner=runner
                task=asyncio.create_task(raw_asgi(app,path,{'session_id':'s','request_id':'disconnect','message':'answer'},disconnected))
                await asyncio.wait_for(started.wait(),5)
                disconnected.set()
                await asyncio.wait_for(task,5)
                release.set()
                await finished.wait()
                async with factory() as db:
                    request=await db.get(ChatRequestTable,(1,'s','disconnect'))
                    assert request.status=='interrupted' and request.attempt==2
                    assert (await db.get(SessionTable,'s')).active_request_id is None
                    assert await db.scalar(select(func.count()).select_from(MessageTable))==2
                assert errors==[]
        finally:
            release.set()
            loop.set_exception_handler(previous)
    dbkit(check)


@pytest.mark.parametrize('duplicate',[False,True])
def test_sse_disconnect_before_first_yield_fences_only_owned_execution(dbkit,monkeypatch,controlled,duplicate):
    async def check(factory,engine):
        from app.main import app
        await seed(factory)
        disconnected=asyncio.Event()
        async with await api_client(factory,monkeypatch):
            service=app.state.conversation_service
            body={'session_id':'s','request_id':'early','message':'answer'}
            owned=await service.prepare_request(1,ChatRequest(**body)) if duplicate else None
            await raw_asgi(app,'/api/chat/stream',body,disconnected,on_start=disconnected.set)
            async with factory() as db:
                row=await db.get(ChatRequestTable,(1,'s','early'))
                assert row.status==('running' if duplicate else 'interrupted')
                assert row.attempt==(1 if duplicate else 2)
                assert await db.scalar(select(func.count()).select_from(MessageTable))==2
            if owned:
                await service.cancel_owned(owned)
                assert controlled.calls==[]
    dbkit(check)


def test_summary_failure_metadata_is_persisted_and_http_sse_replay_is_exact(dbkit,monkeypatch,controlled):
    async def check(factory,engine):
        from app.main import app
        await seed(factory)
        async with factory() as db:
            row=await db.get(SessionTable,'s')
            row.next_turn_index=8
            await db.flush()
            for i in range(1,8):
                db.add_all([MessageTable(session_id='s',turn_index=i,role='user',content=f'user{i}'),
                    MessageTable(session_id='s',turn_index=i,role='assistant',content=f'assistant{i}')])
            await db.commit()
        original=controlled.invoke
        summary_calls=[]
        def invoke(messages):
            if '仅总结所提供' in messages[0].content:
                summary_calls.append(messages)
                raise RuntimeError('controlled summary failure')
            return original(messages)
        monkeypatch.setattr(controlled,'invoke',invoke)
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            service.llm.config.max_retries=0
            service.llm.config.fallback_model=service.llm.config.primary_model
            body={'session_id':'s','request_id':'reduced','message':'now'}
            response=(await client.post('/api/chat',headers=headers(),json=body)).json()
            assert response['persisted'] and response['context_reduced'] is True
            assert 'summary_failed' in response['reduction_reasons'] and len(summary_calls)==1
            async with factory() as db:
                request=await db.get(ChatRequestTable,(1,'s','reduced'))
                assert request.response_json==response
                assert json.loads((await db.get(SessionTable,'s')).state_json)['summary_until_message_id'] is None
            await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'new','message':'next'})
            count=len(controlled.calls),len(summary_calls)
            assert (await client.post('/api/chat',headers=headers(),json=body)).json()==response
            stream=await client.post('/api/chat/stream',headers=headers(),json=body)
            assert [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]==[{'type':'final',**response}]
            assert (len(controlled.calls),len(summary_calls))==count
    dbkit(check)


def test_legacy_first_turn_has_history_but_never_old_node_assessment(dbkit,monkeypatch,controlled):
    controlled.responses['critic_assess']={'mastery_score':65,'mastery_level':'partial'}
    async def check(factory,engine):
        _,aid,_=await seed(factory,state={'stage':'awaiting_response','last_question':'A question'})
        async with factory() as db:
            row=await db.get(SessionTable,'s')
            row.next_turn_index=4
            await db.flush()
            db.add(MessageTable(session_id='s',turn_index=3,role='user',content='orphan original'))
            await db.commit()
        async with await api_client(factory,monkeypatch) as client:
            first=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'legacy','message':'old answer'})
            assert first.json()['persisted'] and first.json()['turn_count']==2 and first.json()['mastery_score'] is None
            assert any('A question' in item[1].content for item in controlled.calls)
        async with factory() as db:
            assert (await db.get(ProfileNodeTable,aid)).practice_count==0
            assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable))==0
            recent=list((await db.scalars(select(MessageTable).where(MessageTable.turn_index==4))).all())
            assert len(recent)==2
    dbkit(check)


def test_sse_disconnect_before_generation_with_explicit_loaded_barrier(dbkit,monkeypatch,controlled):
    async def check(factory,engine):
        from app.main import app
        await seed(factory)
        entered,release,disconnected=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async with await api_client(factory,monkeypatch):
            service=app.state.conversation_service
            original=service.load_turn_context
            async def loaded(prepared):
                value=await original(prepared)
                entered.set()
                await release.wait()
                return value
            monkeypatch.setattr(service,'load_turn_context',loaded)
            task=asyncio.create_task(raw_asgi(app,'/api/chat/stream',{'session_id':'s','request_id':'before-generation','message':'answer'},disconnected))
            try:
                await entered.wait()
                disconnected.set()
                for _ in range(100):
                    async with factory() as db:
                        request=await db.get(ChatRequestTable,(1,'s','before-generation'))
                        interrupted=request.status=='interrupted'
                    if interrupted:
                        break
                assert interrupted
                release.set()
                await task
                assert controlled.calls==[]
            finally:
                release.set()
                await asyncio.gather(task,return_exceptions=True)
    dbkit(check)


def test_retry_rechecks_real_state_race_and_returns_conflict_http(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        _,_,bid=await seed(factory)
        def failed(*args,**kwargs):
            raise RuntimeError('failed generation')
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            service.runner=failed
            result=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'retry-race','message':'answer'})
            assert result.json()['status']=='failed' and result.json()['attempt']==2
            original=service.retry_turn
            watchers=[]
            async def raced(**kwargs):
                watchers.extend(task for task in asyncio.all_tasks() if task.get_coro().__name__=='watch_disconnect')
                async with factory() as db:
                    await SessionService(db).set_active_node(1,'s',0,bid)
                    await db.commit()
                return await original(**kwargs)
            monkeypatch.setattr(service,'retry_turn',raced)
            response=await client.post('/api/sessions/s/requests/retry-race/retry',headers=headers(),json={'expected_attempt':2,'expected_state_version':0})
            assert watchers and all(task.done() for task in watchers)
            assert response.status_code==409 and response.json()['detail']['code']=='stale_context'
    dbkit(check)


def test_payload_hash_uses_exact_original_utf8_canonical_json():
    import hashlib
    from app.orchestration.conversation_service import normalize_payload
    payload,digest=normalize_payload('  中文\n原文  ','11111111-1111-1111-1111-111111111111',None,7)
    literal='{"active_node_id":null,"base_state_version":7,"message":"  中文\\n原文  ","profile_id":"11111111-1111-1111-1111-111111111111"}'
    assert payload=={'message':'  中文\n原文  ','profile_id':'11111111-1111-1111-1111-111111111111','active_node_id':None,'base_state_version':7}
    assert digest==hashlib.sha256(literal.encode('utf-8')).hexdigest()


def test_duplicate_node_delta_uses_final_item_and_one_evidence(dbkit):
    async def check(factory,engine):
        _,aid,_=await seed(factory)
        service=ConversationService(factory,runner=candidate_runner(score=25.5,duplicate=True))
        response=await service.submit_turn(1,ChatRequest(session_id='s',request_id='double',message='answer'))
        assert response.persisted and response.mastery_score==100
        async with factory() as db:
            node=await db.get(ProfileNodeTable,aid)
            assert node.mastery==100 and node.practice_count==1 and node.revision==1
            assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable))==1
    dbkit(check)


def test_graph_full_nodes_are_loaded_but_prompt_shows_only_twenty(dbkit):
    async def check(factory,engine):
        pid,_,_=await seed(factory)
        async with factory() as db:
            db.add_all([ProfileNodeTable(id=str(uuid4()),profile_id=pid,title=f'node{i}') for i in range(28)])
            await db.commit()
        def runner(sid,uid,text,*,graph,on_event,context):
            assert len(graph.nodes)==30 and len(context.valid_node_ids)==30 and len(context.profile_nodes)==20
            return candidate_runner()(sid,uid,text,graph=graph,on_event=on_event,context=context)
        service=ConversationService(factory,runner=runner)
        assert (await service.submit_turn(1,ChatRequest(session_id='s',request_id='all-nodes',message='answer'))).persisted
    dbkit(check)


def test_pending_text_and_draft_never_enter_actual_llm_prompt(dbkit,monkeypatch,controlled):
    async def check(factory,engine):
        pid,_,_=await seed(factory)
        async with factory() as db:
            db.add(SessionViewStateTable(user_id=1,session_id='s',draft='DRAFT SECRET',version=4))
            db.add(ChatRequestTable(user_id=1,session_id='s',request_id='old-failed',profile_id=pid,
                payload_hash='old',request_payload={'message':'PENDING SECRET'},base_state_version=0,status='failed'))
            await db.commit()
        async with await api_client(factory,monkeypatch) as client:
            response=await client.post('/api/chat',headers=headers(),json={'session_id':'s','request_id':'now','message':'answer'})
            assert response.json()['persisted']
        assert all('DRAFT SECRET' not in pair[1].content and 'PENDING SECRET' not in pair[1].content for pair in controlled.calls)
        async with factory() as db:
            view=await db.get(SessionViewStateTable,(1,'s'))
            assert view.draft=='DRAFT SECRET' and view.version==4
    dbkit(check)


def test_final_business_commit_cannot_cross_300_second_deadline(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.orchestration import turn_commit
        await seed(factory)
        clock=ManualClock()
        entered,release=asyncio.Event(),asyncio.Event()
        original=turn_commit.commit_turn
        async def held(db,**kwargs):
            result=await original(db,**kwargs)
            entered.set()
            await release.wait()
            return result
        monkeypatch.setattr(turn_commit,'commit_turn',held)
        service=ConversationService(factory,runner=candidate_runner(score=65),clock=clock)
        task=asyncio.create_task(service.submit_turn(1,ChatRequest(session_id='s',request_id='commit-deadline',message='answer')))
        try:
            await entered.wait()
            clock.advance(300)
            release.set()
            response=await task
            assert not response.persisted and response.status=='interrupted' and response.error_code=='deadline_exceeded'
            async with factory() as db:
                assert await db.scalar(select(func.count()).select_from(MessageTable))==2
                assert await db.scalar(select(func.count()).select_from(ProfileEvidenceTable))==0
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
            await service.aclose()
    dbkit(check)


def test_final_store_lease_validation_uses_clock_after_actual_database_wait(dbkit):
    async def check(factory,engine):
        from sqlalchemy.util.concurrency import await_only
        await seed(factory)
        clock=ManualClock()
        entered,release=asyncio.Event(),asyncio.Event()
        gate=[]
        @event.listens_for(engine.sync_engine,'before_cursor_execute')
        def wait_inside_final_transaction(conn,cursor,statement,params,context,many):
            if statement.startswith('INSERT INTO messages'):
                conn.info['business']=True
            if conn.info.get('business') and 'FROM chat_requests' in statement and not gate:
                gate.append(True)
                entered.set()
                await_only(release.wait())
        service=ConversationService(factory,runner=candidate_runner(score=65),clock=clock)
        task=asyncio.create_task(service.submit_turn(1,ChatRequest(session_id='s',request_id='commit-lease',message='answer')))
        try:
            await entered.wait()
            clock.advance(181)
            release.set()
            with pytest.raises(__import__('fastapi').HTTPException) as caught:
                await task
            assert caught.value.status_code==409 and caught.value.detail['code']=='lease_expired'
            async with factory() as db:
                assert await db.scalar(select(func.count()).select_from(MessageTable))==2
                assert (await db.get(ChatRequestTable,(1,'s','commit-lease'))).status=='failed'
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
            await service.aclose()
    dbkit(check)


def test_context_load_crossing_deadline_never_dispatches_generation(dbkit,monkeypatch):
    async def check(factory,engine):
        await seed(factory)
        clock=ManualClock()
        entered,release=asyncio.Event(),asyncio.Event()
        service=ConversationService(factory,runner=candidate_runner(),clock=clock)
        original=service.load_turn_context
        async def held(prepared):
            value=await original(prepared)
            entered.set()
            await release.wait()
            return value
        monkeypatch.setattr(service,'load_turn_context',held)
        original_thread=asyncio.to_thread
        dispatched=[]
        async def thread(*args,**kwargs):
            dispatched.append(clock.value)
            return await original_thread(*args,**kwargs)
        monkeypatch.setattr(asyncio,'to_thread',thread)
        task=asyncio.create_task(service.submit_turn(1,ChatRequest(session_id='s',request_id='load-deadline',message='answer')))
        try:
            await entered.wait()
            clock.advance(300)
            release.set()
            result=await task
            assert result.status=='interrupted' and result.error_code=='deadline_exceeded'
            assert dispatched==[], 'expired context dispatched generation'
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
            await service.aclose()
    dbkit(check)


def test_context_load_rejects_old_attempt_even_same_active_request(dbkit):
    async def check(factory,engine):
        from app.infrastructure.storage.chat_request_store import ChatRequestStore
        await seed(factory)
        service=ConversationService(factory,runner=candidate_runner())
        old=await service.prepare_request(1,ChatRequest(session_id='s',request_id='reused',message='answer'))
        await service.cancel_owned(old)
        async with factory() as db:
            newer=await ChatRequestStore(db).retry(1,'s','reused',2,0)
            await db.commit()
        assert newer.attempt==3
        with pytest.raises(WorkspaceConflict,match='attempt_conflict'):
            await service.load_turn_context(old)
        await service.aclose()
    dbkit(check)


@pytest.mark.parametrize('case,status,code',[
    ('stale',409,'stale_context'),('other_profile',409,'profile_context_mismatch'),
    ('missing_profile',404,None),('foreign_profile',404,None),
    ('archived_node',409,'graph_context_mismatch'),('schema',409,'unsupported_teaching_schema')])
def test_preflight_profile_version_schema_graph_errors_are_before_model(dbkit,monkeypatch,controlled,case,status,code):
    async def check(factory,engine):
        _,aid,_=await seed(factory)
        body={'session_id':'s','request_id':'preflight','message':'answer'}
        async with factory() as db:
            if case=='stale':
                body['expected_state_version']=99
            if case in {'other_profile','foreign_profile'}:
                other=str(uuid4())
                db.add(TopicProfileTable(id=other,user_id=2 if case=='foreign_profile' else 1,name='other'))
                body['profile_id']=other
            if case=='missing_profile':
                body['profile_id']=str(uuid4())
            if case=='archived_node':
                (await db.get(ProfileNodeTable,aid)).archived=True
            if case=='schema':
                (await db.get(SessionTable,'s')).state_json='{"schema_version":99}'
            await db.commit()
        async with await api_client(factory,monkeypatch) as client:
            response=await client.post('/api/chat',headers=headers(),json=body)
            assert response.status_code==status,response.text
            if code:
                assert response.json()['detail']['code']==code
            assert controlled.calls==[]
    dbkit(check)


def test_strict_legacy_invalid_json_is_never_reset_or_written(dbkit):
    async def check(factory,engine):
        from app.api._persist import persist_turn
        await seed(factory,state={},bound=False)
        async with factory() as db:
            (await db.get(SessionTable,'s')).state_json='broken-json'
            await db.commit()
        writes=[]
        @event.listens_for(engine.sync_engine,'before_cursor_execute')
        def trace(conn,cursor,statement,params,context,many):
            if statement.lstrip().split()[0].upper() in {'INSERT','UPDATE','DELETE'}:
                writes.append(statement)
        class Graph:
            async def save(self):
                raise AssertionError('invalid JSON must not reach old full graph save')
        async with factory() as db:
            assert await persist_turn(db,'s',1,'new','reply',Graph()) is None
        assert writes==[]
        async with factory() as db:
            assert (await db.get(SessionTable,'s')).state_json=='broken-json'
            assert await db.scalar(select(func.count()).select_from(MessageTable))==2
    dbkit(check)
