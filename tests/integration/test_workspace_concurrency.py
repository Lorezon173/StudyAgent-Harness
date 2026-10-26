"""Task8: dedicated PostgreSQL databases, real row/unique locks and transactions."""
import asyncio
import json
import os
import threading
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import event,select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.util.concurrency import await_only

from app.core.database import Base
from app.models.tables import SessionTable,MessageTable,UserTable
from app.models.workspace_tables import TopicProfileTable,ProfileNodeTable,ChatRequestTable,ProfileEvidenceTable
from app.models.schemas import ChatRequest
from app.harness.teaching_context import TeachingState
from app.orchestration.conversation_service import ConversationService
from app.infrastructure.storage.chat_request_store import WorkspaceConflict
from tests.api.test_conversation_transactions import seed,candidate_runner,api_client,headers

pytestmark=pytest.mark.integration


@pytest.fixture
def pg_database():
    configured=os.environ.get('WORKSPACE_TEST_DATABASE_URL')
    assert configured,'Task8真实PG必须设置WORKSPACE_TEST_DATABASE_URL'
    url=make_url(configured)
    assert url.host in {'127.0.0.1','localhost'} and url.port==55440 and url.username=='goal_test' and url.database=='goal_workspace'
    name='workspace_task8_'+uuid4().hex
    maintenance=sa.create_engine(url.set(drivername='postgresql+psycopg'),isolation_level='AUTOCOMMIT',poolclass=NullPool)
    with maintenance.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    async def run(check):
        engine=create_async_engine(url.set(database=name),poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))
                await conn.run_sync(Base.metadata.create_all)
            factory=async_sessionmaker(engine,expire_on_commit=False)
            async with factory() as db:
                db.add_all([UserTable(id=i,username=str(i),password_hash='x') for i in (1,2)])
                await db.commit()
            await asyncio.wait_for(check(factory,engine),45)
        finally:
            await engine.dispose()
    try:
        yield lambda check:asyncio.run(run(check))
    finally:
        with maintenance.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE "{name}"'))
        maintenance.dispose()


async def observe_lock(engine,blocked_pids):
    deadline=asyncio.get_running_loop().time()+8
    async with engine.connect() as observer:
        observer_pid=await observer.scalar(sa.text('SELECT pg_backend_pid()'))
        while asyncio.get_running_loop().time()<deadline:
            await observer.execute(sa.text('SELECT pg_stat_clear_snapshot()'))
            rows=(await observer.execute(sa.text("SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) blockers FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"))).mappings().all()
            matches=[row for row in rows if row['pid'] in blocked_pids and row['blockers']]
            if matches:
                locks=(await observer.execute(sa.text('SELECT pid,locktype,mode,granted FROM pg_locks WHERE pid=ANY(:pids)'),{'pids':list(blocked_pids)})).mappings().all()
                print('TASK8_PG_LOCK',engine.url.database,'observer',observer_pid,'waiters',[dict(row) for row in matches],'locks',[dict(row) for row in locks])
                return matches
        raise AssertionError('no real PostgreSQL lock wait observed')


async def second_session(factory,pid,aid,*,sid='second',uid=1):
    async with factory() as db:
        state=TeachingState(active_node_id=aid,stage='awaiting_response',last_question='A question',committed_turn_count=1)
        db.add(SessionTable(id=sid,user_id=uid,profile_id=pid,active_node_id=aid,state_json=json.dumps(state.to_dict()),next_turn_index=1))
        await db.flush()
        db.add_all([MessageTable(session_id=sid,role='user',content='previous',turn_index=0),MessageTable(session_id=sid,role='assistant',content='A question',turn_index=0)])
        await db.commit()


def test_same_profile_parallel_assessments_use_latest_node_and_real_profile_lock(pg_database):
    async def check(factory,engine):
        pid,aid,bid=await seed(factory)
        await second_session(factory,pid,aid)
        release=threading.Event()
        started=asyncio.Event()
        ready=[]
        loop=asyncio.get_running_loop()
        commits=[]
        @event.listens_for(engine.sync_engine,'after_cursor_execute')
        def updates(conn,cursor,statement,params,context,many):
            if statement.startswith('UPDATE profile_nodes'):
                commits.append(params[0])
        def runner(sid,uid,text,*,graph,on_event,context):
            def signal():
                ready.append(sid)
                if len(ready)==2:
                    started.set()
            loop.call_soon_threadsafe(signal)
            return candidate_runner(score=float(text),release=release)(sid,uid,text,graph=graph,on_event=on_event,context=context)
        service=ConversationService(factory,runner=runner)
        async with factory() as db:
            other_before={column.name:getattr(await db.get(ProfileNodeTable,bid),column.name) for column in ProfileNodeTable.__table__.columns}
        tasks=[asyncio.create_task(service.submit_turn(1,ChatRequest(session_id=sid,request_id=sid,message=score))) for sid,score in [('s','25.5'),('second','80.5')]]
        try:
            await started.wait()
            async with factory() as locker:
                blocker=await locker.scalar(sa.text('SELECT pg_backend_pid()'))
                # 两个生成线程均运行时，第三物理连接可以取得session及profile写锁。
                await locker.execute(select(SessionTable).where(SessionTable.id=='s').with_for_update(nowait=True))
                await locker.execute(select(TopicProfileTable).where(TopicProfileTable.id==pid).with_for_update(nowait=True))
                await locker.rollback()
                await locker.execute(select(TopicProfileTable).where(TopicProfileTable.id==pid).with_for_update())
                print('TASK8_GENERATION_NO_DB_LOCK',blocker,ready)
                release.set()
                async with engine.connect() as observer:
                    deadline=loop.time()+8
                    waiting=[]
                    while loop.time()<deadline:
                        await observer.execute(sa.text('SELECT pg_stat_clear_snapshot()'))
                        waiting=list((await observer.scalars(sa.text("SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>:pid"),{'pid':blocker})).all())
                        if waiting:
                            break
                assert waiting
                await observe_lock(engine,set(waiting))
                await locker.commit()
            results=await asyncio.gather(*tasks)
            assert all(result.persisted for result in results)
            async with factory() as db:
                node=await db.get(ProfileNodeTable,aid)
                assert node.practice_count==2 and node.revision==2 and node.mastery==commits[-1]
                assert (await db.get(TopicProfileTable,pid)).revision==2
                evidence=list((await db.scalars(select(ProfileEvidenceTable))).all())
                assert len(evidence)==2 and len({e.message_id for e in evidence})==2 and len({e.request_id for e in evidence})==2
                other=await db.get(ProfileNodeTable,bid)
                assert {column.name:getattr(other,column.name) for column in ProfileNodeTable.__table__.columns}==other_before
                print('TASK8_PROFILE_SERIALIZED',pid,'count',node.practice_count,'node_revision',node.revision,'scores',commits,'evidence',[(e.request_id,e.message_id) for e in evidence])
        finally:
            release.set()
            await asyncio.gather(*tasks,return_exceptions=True)
            await service.aclose()
    pg_database(check)


def insert_race(engine,table):
    arrived=[]
    both=asyncio.Event()
    inserted=asyncio.Event()
    release=asyncio.Event()
    winner=[]
    prefix='INSERT INTO '+table
    @event.listens_for(engine.sync_engine,'before_cursor_execute')
    def before(conn,cursor,statement,params,context,many):
        if statement.startswith(prefix):
            arrived.append(conn.scalar(sa.text('SELECT pg_backend_pid()')))
            if len(arrived)==2:
                both.set()
            await_only(both.wait())
    @event.listens_for(engine.sync_engine,'after_cursor_execute')
    def after(conn,cursor,statement,params,context,many):
        if statement.startswith(prefix) and not winner:
            winner.append(conn.scalar(sa.text('SELECT pg_backend_pid()')))
            inserted.set()
            await_only(release.wait())
    return arrived,inserted,release


@pytest.mark.parametrize('second_owner,second_request',[(1,'same'),(1,'other'),(2,'same')])
def test_unknown_session_pk_race_rechecks_owner_payload_and_busy(pg_database,second_owner,second_request):
    async def check(factory,engine):
        profiles={}
        async with factory() as db:
            for uid in (1,2):
                row=TopicProfileTable(id=str(uuid4()),user_id=uid,name='same name')
                db.add(row)
                profiles[uid]=row.id
            await db.commit()
        arrived,inserted,release=insert_race(engine,'sessions')
        calls=[]
        def runner(*args,**kwargs):
            calls.append(args)
            return candidate_runner()(*args,**kwargs)
        service=ConversationService(factory,runner=runner)
        requests=[(1,'same'),(second_owner,second_request)]
        tasks=[asyncio.create_task(service.prepare_request(uid,ChatRequest(session_id='unknown',request_id=rid,profile_id=profiles[uid],message='same'))) for uid,rid in requests]
        try:
            await inserted.wait()
            assert len(set(arrived))==2
            await observe_lock(engine,set(arrived))
            release.set()
            results=await asyncio.gather(*tasks,return_exceptions=True)
            acquired=[r for r in results if not isinstance(r,BaseException) and r.claim.acquired]
            assert len(acquired)==1
            loser=next(r for r in results if r is not acquired[0])
            if second_owner!=1:
                assert getattr(loser,'status_code',None)==403
            elif second_request!='same':
                assert isinstance(loser,WorkspaceConflict) and loser.code=='session_busy'
            else:
                assert loser.claim.status=='running' and not loser.claim.acquired
            done=await service.run_claim(acquired[0])
            assert done.persisted and len(calls)==1
            async with factory() as db:
                assert await db.scalar(select(sa.func.count()).select_from(SessionTable))==1
                assert await db.scalar(select(sa.func.count()).select_from(ChatRequestTable))==1
                assert (await db.get(SessionTable,'unknown')).user_id==acquired[0].user_id
        finally:
            release.set()
            await asyncio.gather(*tasks,return_exceptions=True)
            await service.aclose()
    pg_database(check)


def test_default_profile_unique_race_is_separate_from_session_claim(pg_database):
    async def check(factory,engine):
        arrived,inserted,release=insert_race(engine,'topic_profiles')
        service=ConversationService(factory,runner=candidate_runner())
        tasks=[asyncio.create_task(service.prepare_request(1,ChatRequest(session_id=sid,request_id='r',message='first'))) for sid in ('one','two')]
        try:
            await inserted.wait()
            await observe_lock(engine,set(arrived))
            release.set()
            prepared=await asyncio.gather(*tasks)
            assert prepared[0].profile_id==prepared[1].profile_id
            assert all(result.persisted for result in await asyncio.gather(*(service.run_claim(p) for p in prepared)))
            async with factory() as db:
                rows=list((await db.scalars(select(TopicProfileTable))).all())
                assert len(rows)==1 and rows[0].kind=='legacy' and rows[0].user_id==1
        finally:
            release.set()
            await asyncio.gather(*tasks,return_exceptions=True)
            await service.aclose()
    pg_database(check)


def test_real_pg_clock_renew_deadline_and_old_attempt_fence(pg_database):
    from tests.api.test_conversation_transactions import test_renew_30_lease_180_deadline_300_and_late_worker_fence
    test_renew_30_lease_180_deadline_300_and_late_worker_fence(pg_database)


def test_two_jwt_users_same_named_profiles_are_isolated(pg_database,monkeypatch):
    async def check(factory,engine):
        pid,aid,_=await seed(factory)
        p2,n2=str(uuid4()),str(uuid4())
        async with factory() as db:
            db.add(TopicProfileTable(id=p2,user_id=2,name='subject'))
            await db.flush()
            db.add(ProfileNodeTable(id=n2,profile_id=p2,title='A'))
            await db.commit()
        await second_session(factory,p2,n2,sid='user-two',uid=2)
        barrier=threading.Barrier(2)
        def runner(sid,uid,text,**kwargs):
            barrier.wait(10)
            return candidate_runner(score=float(text))(sid,uid,text,**kwargs)
        async with await api_client(factory,monkeypatch) as client:
            from app.main import app
            app.state.conversation_service.runner=runner
            responses=await asyncio.gather(*(client.post('/api/chat',headers=headers(uid),json={'session_id':sid,'request_id':'same','message':score}) for uid,sid,score in [(1,'s','20'),(2,'user-two','80')]))
            assert all(response.json()['persisted'] for response in responses)
            assert (await client.get('/api/sessions/s/messages',headers=headers(2))).status_code==403
            assert (await client.post('/api/chat',headers=headers(2),json={'session_id':'s','message':'intrude'})).status_code==403
            assert (await client.post('/api/sessions/s/requests/same/retry',headers=headers(2),json={'expected_attempt':1,'expected_state_version':0})).status_code==403
        async with factory() as db:
            assert (await db.get(ProfileNodeTable,aid)).mastery==20
            assert (await db.get(ProfileNodeTable,n2)).mastery==80
            assert {(e.user_id,e.profile_id,e.node_id) for e in (await db.scalars(select(ProfileEvidenceTable))).all()}=={(1,pid,aid),(2,p2,n2)}
    pg_database(check)


@pytest.mark.parametrize('path',['/api/chat','/api/chat/stream','retry'])
def test_commit_lock_wins_real_asgi_disconnect_and_completed_is_preserved(pg_database,monkeypatch,path):
    async def check(factory,engine):
        from app.main import app
        from app.orchestration import turn_commit
        from tests.api.test_conversation_transactions import raw_asgi,establish_failed_retry
        await seed(factory)
        entered,release,disconnected=asyncio.Event(),asyncio.Event(),asyncio.Event()
        original=turn_commit.commit_turn
        commit_pid=[]
        async def held(db,**kwargs):
            result=await original(db,**kwargs)
            commit_pid.append(await db.scalar(sa.text('SELECT pg_backend_pid()')))
            entered.set()
            await release.wait()
            return result
        monkeypatch.setattr(turn_commit,'commit_turn',held)
        async with await api_client(factory,monkeypatch) as client:
            service=app.state.conversation_service
            if path=='retry':
                route=await establish_failed_retry(client,service,request_id='race')
                body={'expected_attempt':2,'expected_state_version':0}
            else:
                route,body=path,{'session_id':'s','request_id':'race','message':'answer'}
            service.runner=candidate_runner(score=65)
            task=asyncio.create_task(raw_asgi(app,route,body,disconnected))
            try:
                await entered.wait()
                disconnected.set()
                async with engine.connect() as observer:
                    deadline=asyncio.get_running_loop().time()+8
                    waiters=[]
                    while asyncio.get_running_loop().time()<deadline:
                        await observer.execute(sa.text('SELECT pg_stat_clear_snapshot()'))
                        waiters=list((await observer.scalars(sa.text('SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND :blocker=ANY(pg_blocking_pids(pid))'),{'blocker':commit_pid[0]})).all())
                        if waiters:
                            break
                assert waiters
                await observe_lock(engine,set(waiters))
                release.set()
                await task
                async with factory() as db:
                    request=await db.get(ChatRequestTable,(1,'s','race'))
                    assert request.status=='completed' and request.attempt==(3 if path=='retry' else 1) and request.response_json['persisted'] is True
                    assert await db.scalar(select(sa.func.count()).select_from(MessageTable))==4
                    assert await db.scalar(select(sa.func.count()).select_from(ProfileEvidenceTable))==1
                replay=await service.submit_turn(1,ChatRequest(session_id='s',request_id='race',message='original answer' if path=='retry' else 'answer'))
                assert replay.persisted and replay.status=='completed'
                print('ROUND2_COMMIT_WINS',path,'completed',replay.attempt,'persisted',replay.persisted,'messages',4)
            finally:
                release.set()
                await asyncio.gather(task,return_exceptions=True)
    pg_database(check)


@pytest.mark.parametrize('after_real_commit',[False,True])
def test_commit_connection_error_reads_actual_completed_before_failure(pg_database,monkeypatch,after_real_commit):
    async def check(factory,engine):
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.orchestration import turn_commit
        pid,_,_=await seed(factory)
        original_core,original_commit=turn_commit.commit_turn,AsyncSession.commit
        async def core(db,**kwargs):
            result=await original_core(db,**kwargs)
            db.info['unknown_commit']=True
            return result
        async def commit(db):
            if not db.info.get('unknown_commit'):
                return await original_commit(db)
            if after_real_commit:
                await original_commit(db)
            raise sa.exc.OperationalError('commit',{},Exception('controlled unknown connection result'))
        monkeypatch.setattr(turn_commit,'commit_turn',core)
        monkeypatch.setattr(AsyncSession,'commit',commit)
        service=ConversationService(factory,runner=candidate_runner(score=65))
        response=await service.submit_turn(1,ChatRequest(session_id='s',request_id='unknown-result',message='answer'))
        assert response.persisted is after_real_commit
        from app.infrastructure.storage.dirty_flag import DirtyFlag
        if after_real_commit:
            assert not DirtyFlag.is_dirty(1,profile_id=pid)
        async with factory() as db:
            request=await db.get(ChatRequestTable,(1,'s','unknown-result'))
            assert request.status==('completed' if after_real_commit else 'failed')
            assert await db.scalar(select(sa.func.count()).select_from(MessageTable))==(4 if after_real_commit else 2)
            assert await db.scalar(select(sa.func.count()).select_from(ProfileEvidenceTable))==(1 if after_real_commit else 0)
        await service.aclose()
    pg_database(check)

def test_archived_node_after_generation_rejects_whole_commit(pg_database):
    async def check(factory,engine):
        pid,aid,_=await seed(factory)
        release=threading.Event()
        started=asyncio.Event()
        loop=asyncio.get_running_loop()
        service=ConversationService(factory,runner=candidate_runner(score=65,
            started=lambda:loop.call_soon_threadsafe(started.set),release=release))
        task=asyncio.create_task(service.submit_turn(1,ChatRequest(session_id='s',request_id='archive',message='answer')))
        try:
            await started.wait()
            async with factory() as db:
                await db.execute(select(TopicProfileTable).where(TopicProfileTable.id==pid).with_for_update())
                node=await db.get(ProfileNodeTable,aid)
                node.archived=True
                await db.commit()
            release.set()
            with pytest.raises(__import__('fastapi').HTTPException) as caught:
                await task
            assert caught.value.status_code==409
            async with factory() as db:
                assert await db.scalar(select(sa.func.count()).select_from(MessageTable))==2
                assert await db.scalar(select(sa.func.count()).select_from(ProfileEvidenceTable))==0
                assert (await db.get(ProfileNodeTable,aid)).practice_count==0
                assert (await db.get(ChatRequestTable,(1,'s','archive'))).status=='failed'
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
            await service.aclose()
    pg_database(check)


def test_real_pg_final_business_deadline_after_locked_core(pg_database,monkeypatch):
    from tests.api.test_conversation_transactions import test_final_business_commit_cannot_cross_300_second_deadline
    test_final_business_commit_cannot_cross_300_second_deadline(pg_database,monkeypatch)


def test_real_pg_final_lease_after_actual_database_wait(pg_database):
    from tests.api.test_conversation_transactions import test_final_store_lease_validation_uses_clock_after_actual_database_wait
    test_final_store_lease_validation_uses_clock_after_actual_database_wait(pg_database)


def test_retry_attempt_cas_and_old_owner_cannot_interrupt_new_attempt(pg_database):
    async def check(factory,engine):
        await seed(factory)
        def fail(*args,**kwargs):
            raise RuntimeError('first attempt failed')
        service=ConversationService(factory,runner=fail)
        original=await service.prepare_request(1,ChatRequest(session_id='s',request_id='retry',message='original'))
        failed=await service.run_claim(original)
        assert failed.status=='failed' and failed.attempt==2
        release=threading.Event()
        started=asyncio.Event()
        loop=asyncio.get_running_loop()
        service.runner=candidate_runner(started=lambda:loop.call_soon_threadsafe(started.set),release=release)
        task=asyncio.create_task(service.retry_turn(user_id=1,session_id='s',request_id='retry',expected_attempt=2,expected_state_version=0))
        try:
            await started.wait()
            with pytest.raises(WorkspaceConflict) as caught:
                await service.retry_turn(user_id=1,session_id='s',request_id='retry',expected_attempt=2,expected_state_version=0)
            assert caught.value.code=='attempt_conflict'
            stale_cancel=await service.cancel_owned(original)
            assert stale_cancel.status=='running' and stale_cancel.attempt==3
            release.set()
            completed=await task
            assert completed.persisted and completed.attempt==3
            async with factory() as db:
                row=await db.get(ChatRequestTable,(1,'s','retry'))
                assert row.status=='completed' and row.attempt==3
                assert await db.scalar(select(sa.func.count()).select_from(MessageTable))==4
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
            await service.aclose()
    pg_database(check)


def test_two_users_default_legacy_profiles_do_not_conflict(pg_database):
    async def check(factory,engine):
        service=ConversationService(factory,runner=candidate_runner())
        prepared=await asyncio.gather(*(service.prepare_request(uid,ChatRequest(session_id=f'default-{uid}',request_id='r',message='hello')) for uid in (1,2)))
        assert prepared[0].profile_id!=prepared[1].profile_id
        completed=await asyncio.gather(*(service.run_claim(p) for p in prepared))
        assert all(result.persisted and result.mastery_score is None for result in completed)
        async with factory() as db:
            profiles=list((await db.scalars(select(TopicProfileTable))).all())
            assert len(profiles)==2 and {p.user_id for p in profiles}=={1,2} and all(p.kind=='legacy' for p in profiles)
        await service.aclose()
    pg_database(check)


@pytest.mark.parametrize('path',['/api/chat','/api/chat/stream','retry'])
def test_real_pg_interruption_wins_before_old_worker_returns(pg_database,monkeypatch,path):
    from tests.api.test_conversation_transactions import (test_real_asgi_disconnect_interrupts_and_closes_late_worker_events,
        test_retry_real_asgi_disconnect_interrupts_before_worker_release)
    if path=='retry':
        test_retry_real_asgi_disconnect_interrupts_before_worker_release(pg_database,monkeypatch)
    else:
        test_real_asgi_disconnect_interrupts_and_closes_late_worker_events(pg_database,monkeypatch,path)
