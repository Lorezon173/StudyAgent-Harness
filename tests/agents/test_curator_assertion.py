"""Tests for CuratorBase __init_subclass__ assertion (Task 6 / P0-⑦).

Verifies:
- Synchronous handle: import succeeds
- Async handle: TypeError raised at class definition time
- Existing Curator: handle is synchronous
"""
import inspect

import pytest

from app.agents.base import CuratorBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState


def test_curator_base_allows_sync_handle():
    """CuratorBase subclass with synchronous handle defines without error."""

    class GoodCurator(CuratorBase):
        source = EventSource.CURATOR
        subscriptions = [EventType.MASTERY_ASSESSED]
        emittable_types = set()

        def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
            return []

    assert not inspect.iscoroutinefunction(GoodCurator.handle)


def test_curator_base_rejects_async_handle():
    """CuratorBase subclass with async handle raises TypeError at class body."""

    with pytest.raises(TypeError, match="must be synchronous"):

        class BadCurator(CuratorBase):  # noqa: F841
            source = EventSource.CURATOR
            subscriptions = [EventType.MASTERY_ASSESSED]
            emittable_types = set()

            async def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
                return []


def test_existing_curator_handle_is_sync():
    """Existing Curator.handle is synchronous (P0-⑦ contract)."""
    from app.agents.curator import Curator
    assert not inspect.iscoroutinefunction(Curator.handle)
    assert Curator.__mro__[1] is CuratorBase  # 验证继承链
