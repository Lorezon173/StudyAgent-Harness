import json
from tests.api.test_conversation_transactions import dbkit,api_client,headers,candidate_runner
from app.harness.events import Event
from app.harness.enums import EventType,EventSource


def test_chat_stream_emits_incremental_agent_events(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        def runner(sid,uid,message,*,graph,on_event,context):
            on_event(Event(type=EventType.TUTOR_ASKED,source=EventSource.TUTOR,session_id=sid,payload={'content':'Q?'}))
            result=candidate_runner()(sid,uid,message,graph=graph,on_event=on_event,context=context)
            result.reply='最终回答'
            result.turn_count=11
            return result
        async with await api_client(factory,monkeypatch) as client:
            app.state.conversation_service.runner=runner
            response=await client.post('/api/chat/stream',headers=headers(),json={'message':'hi','session_id':'st1'})
            assert 'agent_event' in response.text and 'TutorAsked' in response.text
            events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            final=next(e for e in events if e['type']=='final')
            assert final['reply']=='最终回答' and final['turn_count']==1 and final['persisted'] is True
    dbkit(check)
