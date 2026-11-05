"""Task13-only model observer and single-process acceptance launcher.

Run via ``python -m tests.integration.workspace_observer`` with isolated settings.
The file contains only identifiers, hashes and boolean matches, never prompts.
"""
import contextvars
import hashlib
import json
import os
import sys
import threading
from contextlib import suppress
from pathlib import Path

from app.harness.teaching_context import parse_teaching_state
from app.infrastructure.llm import LLMService
from app.orchestration.conversation_service import ConversationService

_current_turn = contextvars.ContextVar("task13_turn", default=None)
_write_lock = threading.Lock()


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def install_observer(path, run_id, markers):
    """Attach read-only wrappers; original parameters and return values remain intact."""
    from langchain_openai import ChatOpenAI

    target = Path(path).resolve()
    runtime = (Path.cwd() / ".superpowers" / "runtime" / "task13").resolve()
    assert runtime in target.parents and target.parent.is_dir() and run_id
    assert all(markers.get(key) for key in ("initial", "s2", "s3", "resume"))
    original_turn = ConversationService.run_turn
    original_call = LLMService._call_with_span

    def run_turn(service, loaded, on_event):
        state = parse_teaching_state(loaded.snapshot, loaded.messages)
        assistant = next((m for m in reversed(loaded.messages) if m.role == "assistant"), None)
        prepared = loaded.prepared
        context = {
            "user_id": prepared.user_id,
            "session_id": prepared.session_id,
            "request_id": prepared.request_id,
            "attempt": prepared.claim.attempt,
            "stage": state.stage,
            "question": state.last_question,
            "question_message_id": assistant.id if assistant and state.last_question == assistant.content else None,
            "question_message": assistant.content if assistant else None,
        }
        token = _current_turn.set(context)
        try:
            return original_turn(service, loaded, on_event)
        finally:
            _current_turn.reset(token)

    def call(service, llm, system_prompt, user_prompt, session_id, node, intent):
        result = original_call(service, llm, system_prompt, user_prompt, session_id, node, intent)
        context = _current_turn.get()
        history, separator, current = user_prompt.partition("【当前输入】\n")
        current_input = current.split("\n【画像】", 1)[0] if separator else ""
        question = context and context["question"]
        message_id = context and context["question_message_id"]
        question_history = bool(question and message_id and (
            (f"上一问题引用={message_id}\n" in history and
             f"消息引用={message_id};角色=assistant\n{question}" in history)
            or ("上一问题=" + question + "\n") in history))
        record = {
            "run_id": run_id,
            "context": {key: context[key] for key in ("user_id", "session_id", "request_id", "attempt", "stage", "question_message_id")} if context else None,
            "question_sha256": _digest(question) if question else None,
            "question_matches_previous_assistant": bool(question and message_id and question == context["question_message"]),
            "question_in_history": question_history,
            "initial_in_history": markers["initial"] in history,
            "resume_is_current_input": current_input == markers["resume"],
            "s2_absent_both_prompts": markers["s2"] not in system_prompt and markers["s2"] not in user_prompt,
            "s3_absent_both_prompts": markers["s3"] not in system_prompt and markers["s3"] not in user_prompt,
            "real_client": isinstance(llm, ChatOpenAI),
            "call_session_matches": bool(context and session_id == context["session_id"]),
            "node": node,
            "intent": intent,
        }
        try:
            with _write_lock, target.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            with suppress(OSError, ValueError):
                print("TASK13_WITNESS_WRITE_FAILED", file=sys.stderr, flush=True)
        return result

    ConversationService.run_turn = run_turn
    LLMService._call_with_span = call


def main():
    import uvicorn

    markers = {key: os.environ[f"TASK13_MARKER_{key.upper()}"] for key in ("initial", "s2", "s3", "resume")}
    install_observer(os.environ["TASK13_WITNESS_PATH"], os.environ["TASK13_RUN_ID"], markers)
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ["TASK13_API_PORT"]), reload=False, workers=1)


if __name__ == "__main__":
    main()
