"""真实共享服务失败时SSE只投影error，不泄露未提交回复。"""
import json
from tests.api.test_conversation_transactions import dbkit,api_client,headers


def test_chat_stream_yields_error_event_on_agent_failure(dbkit,monkeypatch):
    async def check(factory,engine):
        from app.main import app
        def crash(*args,**kwargs):
            raise RuntimeError('agent boom')
        async with await api_client(factory,monkeypatch) as client:
            app.state.conversation_service.runner=crash
            response=await client.post('/api/chat/stream',headers=headers(),json={'message':'hi','session_id':'st-err'})
            assert response.status_code==200
            events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            errors=[e for e in events if e.get('type')=='error']
            assert len(errors)==1
            error=errors[0]
            assert error['code']=='AGENT_ERROR'
            assert error['message']=='处理过程中发生错误'
            assert error['retryable'] is False
            assert error['persisted'] is False and error['status']=='failed' and error['attempt']==2
            assert [e for e in events if e.get('type')=='final']==[]
    dbkit(check)
