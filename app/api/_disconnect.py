"""HTTP body解析完成后的单一断连观察与局部任务清理。"""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anyio import CancelScope
from fastapi import Request


async def watch_disconnect(request: Request, event: asyncio.Event) -> None:
    while not event.is_set():
        if await request.is_disconnected():
            event.set()
            return
        try:
            await asyncio.wait_for(event.wait(), timeout=0.1)
        except TimeoutError:
            pass


@asynccontextmanager
async def observe_http_disconnect(request: Request) -> AsyncIterator[asyncio.Event]:
    disconnected = asyncio.Event()
    probe = None
    watcher = None
    try:
        # Request内部取消域只作用于子任务，父handler的外部取消仍须传播。
        probe = asyncio.create_task(request.is_disconnected())
        if await asyncio.shield(probe):
            disconnected.set()
        else:
            watcher = asyncio.create_task(watch_disconnect(request, disconnected))
        yield disconnected
    finally:
        # is_disconnected内部取消域可能合并cancel；退出信号确保循环仍会结束。
        disconnected.set()
        owned = [task for task in (probe, watcher) if task is not None]
        for task in owned:
            if not task.done():
                task.cancel()
        with CancelScope(shield=True):
            await asyncio.gather(*owned, return_exceptions=True)
