"""Two process PostgreSQL container restart probe, only its random database."""
import asyncio,json,os,re,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[5]))
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.database import Base
from app.models.tables import UserTable,SessionTable
from app.models.workspace_tables import ChatRequestTable,ProfileEvidenceTable
from app.models.schemas import ChatRequest
from app.orchestration.conversation_service import ConversationService
from app.orchestration.session_service import SessionService
from tests.api.test_conversation_transactions import seed,candidate_runner
from tests.integration.test_workspace_concurrency import second_session

checkpoint=Path(__file__).with_name('restart-checkpoint.json')
url=make_url(os.environ['WORKSPACE_TEST_DATABASE_URL'])
assert url.host=='127.0.0.1' and url.port==55440 and url.username=='goal_test' and url.database=='goal_workspace'
mode=sys.argv[1]
maintenance=sa.create_engine(url.set(drivername='postgresql+psycopg'),isolation_level='AUTOCOMMIT',poolclass=NullPool)
if mode=='prepare':
    assert not checkpoint.exists(), 'retain existing checkpoint for investigation'
    name='workspace_task8_'+uuid4().hex
    with maintenance.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
else:
    stored=json.loads(checkpoint.read_text(encoding='utf-8'))
    name=stored['database']
assert re.fullmatch(r'workspace_task8_[0-9a-f]{32}',name)

async def run():
    engine=create_async_engine(url.set(database=name),poolclass=NullPool)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    try:
        if mode=='prepare':
            async with engine.begin() as conn:
                await conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))
                await conn.run_sync(Base.metadata.create_all)
            async with factory() as db:
                db.add_all([UserTable(id=i,username=str(i),password_hash='x') for i in (1,2)])
                await db.commit()
            pid,aid,_=await seed(factory)
            service=ConversationService(factory,runner=candidate_runner(score=65.25))
            completed=await service.submit_turn(1,ChatRequest(session_id='s',request_id='completed',message='persist across restart'))
            assert completed.persisted
            for sid in ('expired','unexpired'):
                await second_session(factory,pid,aid,sid=sid)
                await service.prepare_request(1,ChatRequest(session_id=sid,request_id='pending',message='pending original'))
            async with factory() as db:
                epoch=datetime.now(timezone.utc).replace(tzinfo=None)
                expired=await db.get(ChatRequestTable,(1,'expired','pending'))
                live=await db.get(ChatRequestTable,(1,'unexpired','pending'))
                expired.lease_until=epoch-timedelta(seconds=1)
                # Future fixture lease keeps this branch unexpired across tool approval latency.
                live.lease_until=epoch+timedelta(hours=24)
                await db.commit()
                before=await db.scalar(sa.text('SELECT pg_postmaster_start_time()::text'))
            metadata={'database':name,'response':completed.model_dump(mode='json'),'before_start':before,'fixture_future_lease_hours':24,'fixture_live_lease_until':live.lease_until.isoformat()}
            checkpoint.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            await service.aclose()
            print('TASK8_RESTART_READY',name,before,'connections will be closed')
        else:
            def forbidden(*args,**kwargs):
                raise AssertionError('restart replay must never generate')
            service=ConversationService(factory,runner=forbidden)
            async with factory() as db:
                after=await db.scalar(sa.text('SELECT pg_postmaster_start_time()::text'))
                assert after!=stored['before_start'], 'real container/server restart not observed'
            response=await service.submit_turn(1,ChatRequest(session_id='s',request_id='completed',message='persist across restart'))
            assert response.model_dump(mode='json')==stored['response']
            await service.recover_session_requests(1,'expired')
            await service.recover_session_requests(1,'unexpired')
            async with factory() as db:
                messages=await SessionService(db).load_messages(1,'s')
                assert len(messages)==4 and messages[-2].content=='persist across restart'
                assert await db.scalar(sa.select(sa.func.count()).select_from(ProfileEvidenceTable))==1
                expired=await db.get(ChatRequestTable,(1,'expired','pending'))
                live=await db.get(ChatRequestTable,(1,'unexpired','pending'))
                assert expired.status=='interrupted' and expired.attempt==2
                assert live.status=='running' and live.attempt==1
                assert (await db.get(SessionTable,'expired')).active_request_id is None
                assert (await db.get(SessionTable,'unexpired')).active_request_id=='pending'
            try:
                await service.submit_turn(2,ChatRequest(session_id='s',request_id='completed',message='persist across restart'))
            except Exception as error:
                assert getattr(error,'status_code',None)==403
            else:
                raise AssertionError('foreign user replay was accepted')
            await service.aclose()
            print('TASK8_REAL_CONTAINER_RESTART_VERIFIED',name,'before',stored['before_start'],'after',after,
                'messages',len(messages),'persisted',response.persisted,'expired',expired.status,'unexpired',live.status,'foreign_user',403)
    finally:
        await engine.dispose()
asyncio.run(run())
if mode=='verify':
    with maintenance.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE "{name}"'))
    checkpoint.rename(checkpoint.with_name('restart-checkpoint-verified.json'))
    print('TASK8_RESTART_DATABASE_DROPPED',name)
maintenance.dispose()
