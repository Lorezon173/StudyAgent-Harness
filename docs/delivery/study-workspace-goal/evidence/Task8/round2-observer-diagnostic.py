import asyncio
import pytest
import app.api._disconnect as observer
from tests.api.test_conversation_transactions import test_http_disconnect_observer_awaits_watcher_with_single_receive
saved_run=asyncio.run
captured=[]
original=observer.watch_disconnect
async def capture(request,event):
    captured.append(event)
    return await original(request,event)
def chain(coro):
    result=[]
    while coro is not None:
        frame=getattr(coro,'cr_frame',None) or getattr(coro,'gi_frame',None)
        if frame:
            events={k:v.is_set() for k,v in frame.f_locals.items() if isinstance(v,asyncio.Event)}
            result.append((frame.f_code.co_name,frame.f_lineno,events))
        coro=getattr(coro,'cr_await',None) or getattr(coro,'gi_yieldfrom',None)
    return result
def bounded(coro):
    loop=asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    root=loop.create_task(coro)
    done,pending=loop.run_until_complete(asyncio.wait([root],timeout=2))
    print('DIAGNOSTIC_ROOT_DONE_BEFORE_RELEASE',root.done(),flush=True)
    for task in asyncio.all_tasks(loop):
        print('DIAGNOSTIC_TASK',task.get_name(),'cancelling',task.cancelling(),'chain',chain(task.get_coro()),flush=True)
    print('DIAGNOSTIC_CAPTURED_EVENT',len(captured),[event.is_set() for event in captured],flush=True)
    for event in captured:
        event.set()
    done,pending=loop.run_until_complete(asyncio.wait([root],timeout=2))
    print('DIAGNOSTIC_ROOT_DONE_AFTER_EVENT_RELEASE',root.done(),'remaining',len(asyncio.all_tasks(loop)),flush=True)
    if root.done():
        root.result()
    else:
        raise RuntimeError('diagnostic own loop still pending')
    loop.close()
try:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(observer,'watch_disconnect',capture)
        patch.setattr(asyncio,'run',bounded)
        test_http_disconnect_observer_awaits_watcher_with_single_receive('normal',patch)
finally:
    asyncio.run=saved_run
