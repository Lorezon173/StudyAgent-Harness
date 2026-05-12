from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat-stream"])
_graph = build_learning_graph()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    from app.harness.enums import Stage

    async def generate():
        state = {
            "user_input": req.message,
            "routing": {}, "teaching": {}, "retrieval": {},
            "evaluation": {}, "memory": {},
            "meta": {"session_id": req.session_id, "stage": Stage.INIT, "branch_trace": []},
        }
        config = {"configurable": {"thread_id": req.session_id}}
        async for event in _graph.astream_events(state, config=config, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chain_end":
                data = event.get("data", {}).get("output", {})
                if isinstance(data, dict) and "teaching" in data:
                    reply = data["teaching"].get("reply", "") or data["teaching"].get("summary", "")
                    if reply:
                        yield f"data: {reply}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
