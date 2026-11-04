import asyncio
import json

import httpx

from acceptance_harness import create_fault_app

TOKEN = "a" * 64

class Dummy:
    def __init__(self):
        self.calls = []
        self.saved = False
        self.body = b'{"status":"completed","persisted":true}'
        self.status = 200
        self.parts = None
        self.error = False
        self.scopes = []

    async def __call__(self, scope, receive, send):
        self.scopes.append(scope["type"])
        if scope["type"] != "http":
            message = await receive()
            await send(message)
            return
        self.calls.append((scope["method"], scope["path"]))
        if self.error:
            raise RuntimeError("inner failure")
        if scope["path"] == "/api/chat":
            self.saved = True
            body = self.body
        else:
            body = json.dumps({"saved": self.saved}).encode()
        await send({"type": "http.response.start", "status": self.status, "headers": [(b"content-type", b"application/json")]})
        parts = self.parts if self.parts is not None else [body]
        for index, part in enumerate(parts):
            await send({"type": "http.response.body", "body": part, "more_body": index < len(parts) - 1})

def run(scenario):
    return asyncio.run(scenario)

def test_auth_schema_counts_and_exact_routes():
    async def scenario():
        inner = Dummy()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_fault_app(inner, TOKEN)), base_url="http://127.0.0.1") as client:
            assert (await client.post("/__acceptance__/faults", json={"view_failures": 1})).status_code == 401
            headers = {"X-Acceptance-Control": TOKEN}
            assert (await client.post("/__acceptance__/faults", headers=headers, json={"view_failures": True})).status_code == 400
            assert (await client.post("/__acceptance__/faults", headers=headers, json={"view_failures": 1})).status_code == 200
            assert (await client.patch("/api/sessions/A/view-state")).status_code == 503
            assert inner.calls == []
            assert (await client.patch("/api/sessions/A/view-state")).status_code == 200
            for method, path in [("GET", "/api/sessions/A/view-state"), ("PATCH", "/api/sessions/A/nested/view-state"), ("POST", "/api/sessions/A/requests/r/retry"), ("PATCH", "/api/workspace-state/extra")]:
                assert (await client.request(method, path)).status_code == 200
    run(scenario())


def test_control_rejects_remote_unknown_bounds_and_oversize():
    async def scenario():
        inner = Dummy()
        app = create_fault_app(inner, TOKEN)
        headers = {"X-Acceptance-Control": TOKEN}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            for value in [{"token": "secret"}, {"view_failures": -1}, {"view_failures": 11}, {"workspace_failures": 1.2}, {"drop_chat_responses": 4}, [], {}]:
                assert (await client.post("/__acceptance__/faults", headers=headers, json=value)).status_code == 400
            assert (await client.post("/__acceptance__/faults", headers=headers, content=b" " * 1025)).status_code == 400
            assert (await client.post("/__acceptance__/faults", headers=headers, content=b'{"view_failures":1,"view_failures":2}')).status_code == 400
            assert (await client.get("/__acceptance__/faults", headers=headers)).json() == dict.fromkeys(["view_failures", "workspace_failures", "drop_chat_responses"], 0)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("203.0.113.4", 4)), base_url="http://127.0.0.1") as remote:
            assert (await remote.post("/__acceptance__/faults", headers=headers, json={"view_failures": 1})).status_code == 401
        assert inner.calls == []
    run(scenario())

def test_completed_response_loss_follows_real_completion_and_readback():
    async def scenario():
        inner = Dummy()
        app = create_fault_app(inner, TOKEN)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            headers = {"X-Acceptance-Control": TOKEN}
            await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": 1, "workspace_failures": 1})
            assert (await client.patch("/api/workspace-state")).status_code == 503
            assert (await client.patch("/api/workspace-state")).status_code == 200
            inner.parts = [b'{"status":"completed",', b'"persisted":true}']
            assert (await client.post("/api/chat")).status_code == 503
            assert inner.saved
            inner.parts = None
            assert (await client.get("/api/sessions/A/requests/r")).json() == {"saved": True}
            assert (await client.post("/api/chat")).status_code == 200
    run(scenario())

def test_failed_nonpersisted_and_oversized_response_do_not_consume():
    async def scenario():
        inner = Dummy()
        app = create_fault_app(inner, TOKEN)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            headers = {"X-Acceptance-Control": TOKEN}
            await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": 1})
            for status, body in [(500, b'{"status":"completed","persisted":true}'), (200, b'{"status":"failed","persisted":false}'), (200, b'{"status":"completed","persisted":false}'), (200, b"invalid")]:
                inner.status, inner.body = status, body
                result = await client.post("/api/chat")
                assert result.status_code == status and result.content == body
                assert (await client.get("/__acceptance__/faults", headers=headers)).json()["drop_chat_responses"] == 1
            inner.status = 200
            inner.parts = [b"x" * (1024 * 1024), b"y" * (1024 * 1024), b"z", b"tail"]
            result = await client.post("/api/chat")
            assert result.status_code == 200 and result.content == b"".join(inner.parts)
            assert (await client.get("/__acceptance__/faults", headers=headers)).json()["drop_chat_responses"] == 1
    run(scenario())

def test_concurrent_completion_consumes_only_configured_count():
    async def scenario():
        inner = Dummy()
        gate = asyncio.Event()
        async def delayed(scope, receive, send):
            if scope["path"] == "/api/chat":
                await gate.wait()
            await inner(scope, receive, send)
        app = create_fault_app(delayed, TOKEN)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            await client.post("/__acceptance__/faults", headers={"X-Acceptance-Control": TOKEN}, json={"drop_chat_responses": 1})
            tasks = [asyncio.create_task(client.post("/api/chat")) for _ in range(4)]
            gate.set()
            results = await asyncio.gather(*tasks)
            assert sorted(result.status_code for result in results) == [200, 200, 200, 503]
    run(scenario())

def test_lifespan_receive_and_inner_exceptions_pass_through():
    async def scenario():
        received = []
        sent = []
        async def receive():
            return {"type": "lifespan.startup"}
        async def send(event):
            sent.append(event)
        async def inner(scope, incoming, outgoing):
            assert incoming is receive
            received.append(scope["type"])
            assert (await incoming())["type"] == "lifespan.startup"
            await outgoing({"type": "lifespan.startup.complete"})
        await create_fault_app(inner, TOKEN)({"type": "lifespan"}, receive, send)
        assert received == ["lifespan"] and sent == [{"type": "lifespan.startup.complete"}]
        dummy = Dummy()
        app = create_fault_app(dummy, TOKEN)
        app.counts["drop_chat_responses"] = 1
        dummy.error = True
        import pytest
        with pytest.raises(RuntimeError, match="inner failure"):
            await app({"type": "http", "path": "/api/chat", "method": "POST"}, receive, send)
        assert app.counts["drop_chat_responses"] == 1
        async def disconnect_inner(scope, incoming, outgoing):
            assert incoming is receive_disconnect
            assert await incoming() == {"type": "http.disconnect"}
            await outgoing({"type": "http.response.start", "status": 204, "headers": []})
            await outgoing({"type": "http.response.body", "body": b""})
        async def receive_disconnect():
            return {"type": "http.disconnect"}
        await create_fault_app(disconnect_inner, TOKEN)({"type": "http", "path": "/api/chat", "method": "POST"}, receive_disconnect, send)
    run(scenario())

def test_path_validation_reuse_and_credentials_without_overwrite(tmp_path, monkeypatch):
    import acceptance_harness as harness
    import pytest
    # Simulate the module's fixed project anchor under an isolated test directory.
    fake_file = tmp_path / "docs/delivery/study-workspace-goal/evidence/Task10/acceptance_harness.py"
    monkeypatch.setattr(harness, "__file__", str(fake_file))
    root = tmp_path / ".superpowers/runtime/task10-acceptance"
    monkeypatch.setattr(harness, "RUNTIME_ROOT", root)
    outside = tmp_path / "outside.db"
    for database, control in [(outside, root / "control.json"), (root / ".." / "outside.db", root / "control.json"), (root / "study_agent.db", root / "control.json"), (root / "same", root / "same")]:
        with pytest.raises(ValueError):
            harness.validate_runtime_paths(database, control)
    assert not root.exists() and not outside.exists()
    root.mkdir(parents=True)
    database = root / "acceptance.db"
    database.write_bytes(b"existing database")
    control = root / "control.json"
    control.write_text('{"token":"weak"}')
    with pytest.raises(ValueError):
        harness.load_control_token(control)
    assert control.read_text() == '{"token":"weak"}'
    control.unlink()
    token = harness.load_control_token(control)
    assert len(token) == 64 and harness.load_control_token(control) == token
    assert harness.validate_runtime_paths(database, control) == (database.resolve(), control.resolve())
    assert database.read_bytes() == b"existing database"

def test_configuration_rejects_missing_model_without_creating_runtime(tmp_path, monkeypatch):
    import acceptance_harness as harness
    import pytest
    monkeypatch.setattr(harness, "__file__", str(tmp_path / "docs/delivery/study-workspace-goal/evidence/Task10/acceptance_harness.py"))
    root = tmp_path / ".superpowers/runtime/task10-acceptance"
    monkeypatch.setattr(harness, "RUNTIME_ROOT", root)
    config = tmp_path / "model.env"
    config.write_text("OPENAI_MODEL=unused\n")
    with pytest.raises(ValueError, match="incomplete"):
        harness.load_runtime_configuration(config, root / "acceptance.db", root / "control.json")
    assert not root.exists()

def test_chat_buffer_preserves_reused_asgi_body_events():
    async def scenario():
        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            event = {"type": "http.response.body", "body": b'{"status":"completed",', "more_body": True}
            await send(event)
            event.update(body=b'"persisted":true}', more_body=False)
            await send(event)
        app = create_fault_app(inner, TOKEN)
        app.counts["drop_chat_responses"] = 1
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            assert (await client.post("/api/chat")).status_code == 503
            assert app.counts["drop_chat_responses"] == 0
    run(scenario())

def test_runtime_rejects_real_hardlink_aliases(tmp_path, monkeypatch):
    import os
    import acceptance_harness as harness
    import pytest
    root = tmp_path / ".superpowers/runtime/task10-acceptance"
    monkeypatch.setattr(harness, "__file__", str(tmp_path / "docs/delivery/study-workspace-goal/evidence/Task10/acceptance_harness.py"))
    monkeypatch.setattr(harness, "RUNTIME_ROOT", root)
    root.mkdir(parents=True)
    # All samples are new empty files owned by this test, never actual user data.
    outside = tmp_path / "study_agent.db"
    outside.touch()
    database = root / "acceptance.db"
    control = root / "control.json"
    os.link(outside, database)
    assert database.stat().st_nlink == 2 and os.path.samefile(outside, database)
    with pytest.raises(ValueError):
        harness.validate_runtime_paths(database, control)
    assert outside.read_bytes() == b"" and database.read_bytes() == b""
    database.unlink()
    database.touch()
    os.link(database, control)
    assert os.path.samefile(database, control)
    with pytest.raises(ValueError):
        harness.validate_runtime_paths(database, control)
    control.unlink()
    database.unlink()
    database.touch()
    control.touch()
    alias = tmp_path / "control-alias.json"
    os.link(control, alias)
    with pytest.raises(ValueError):
        harness.validate_runtime_paths(database, control)
    assert control.read_bytes() == b"" and alias.read_bytes() == b""

def test_delayed_chat_cannot_consume_reconfigured_response_loss():
    async def scenario():
        for updates in ([0, 1], [1]):
            entered, release = asyncio.Event(), asyncio.Event()
            inner = Dummy()
            async def delayed(scope, receive, send):
                if scope["path"] == "/api/chat" and not entered.is_set():
                    entered.set()
                    await release.wait()
                await inner(scope, receive, send)
            app = create_fault_app(delayed, TOKEN)
            headers = {"X-Acceptance-Control": TOKEN}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": 1})
                old = asyncio.create_task(client.post("/api/chat"))
                await entered.wait()
                for count in updates:
                    await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": count})
                release.set()
                assert (await old).status_code == 200
                assert (await client.get("/__acceptance__/faults", headers=headers)).json()["drop_chat_responses"] == 1
                assert (await client.post("/api/chat")).status_code == 503
                assert (await client.get("/__acceptance__/faults", headers=headers)).json()["drop_chat_responses"] == 0
    run(scenario())

def test_identity_checks_fail_closed_when_metadata_cannot_be_confirmed(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import stat
    import acceptance_harness as harness
    import pytest
    root = tmp_path / ".superpowers/runtime/task10-acceptance"
    monkeypatch.setattr(harness, "__file__", str(tmp_path / "docs/delivery/study-workspace-goal/evidence/Task10/acceptance_harness.py"))
    monkeypatch.setattr(harness, "RUNTIME_ROOT", root)
    root.mkdir(parents=True)
    database, control = root / "acceptance.db", root / "control.json"
    database.touch()
    control.touch()
    original_stat = Path.stat
    for links in (None, 0, 2, True):
        with monkeypatch.context() as patch:
            def uncertain(path, *args, **kwargs):
                if path == database:
                    return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=links)
                return original_stat(path, *args, **kwargs)
            patch.setattr(Path, "stat", uncertain)
            with pytest.raises(ValueError):
                harness.validate_runtime_paths(database, control)
    with monkeypatch.context() as patch:
        def blocked(path, *args, **kwargs):
            if path == database:
                raise PermissionError("test metadata unavailable")
            return original_stat(path, *args, **kwargs)
        patch.setattr(Path, "stat", blocked)
        with pytest.raises((ValueError, OSError)):
            harness.validate_runtime_paths(database, control)
    with monkeypatch.context() as patch:
        patch.setattr(harness.os.path, "samefile", lambda *_: True)
        with pytest.raises(ValueError):
            harness.validate_runtime_paths(database, control)
    with monkeypatch.context() as patch:
        def blocked_samefile(*_):
            raise OSError("test identity unavailable")
        patch.setattr(harness.os.path, "samefile", blocked_samefile)
        with pytest.raises(ValueError):
            harness.validate_runtime_paths(database, control)
    assert database.read_bytes() == b"" and control.read_bytes() == b""

def test_configuration_rechecks_links_before_sensitive_initialization(tmp_path, monkeypatch):
    import os
    import dotenv
    import acceptance_harness as harness
    import pytest
    root = tmp_path / ".superpowers/runtime/task10-acceptance"
    monkeypatch.setattr(harness, "__file__", str(tmp_path / "docs/delivery/study-workspace-goal/evidence/Task10/acceptance_harness.py"))
    monkeypatch.setattr(harness, "RUNTIME_ROOT", root)
    root.mkdir(parents=True)
    database, control = root / "acceptance.db", root / "control.json"
    database.touch()
    alias = tmp_path / "new-empty-alias.db"
    def changed_during_configuration(_):
        os.link(database, alias)
        return {"OPENAI_API_KEY": "dummy-not-used", "OPENAI_BASE_URL": "http://127.0.0.1", "OPENAI_MODEL": "dummy-not-used"}
    monkeypatch.setattr(dotenv, "dotenv_values", changed_during_configuration)
    original_env = dict(os.environ)
    with pytest.raises(ValueError):
        harness.load_runtime_configuration(tmp_path / "unused.env", database, control)
    assert dict(os.environ) == original_env
    assert not control.exists() and database.read_bytes() == b"" and alias.read_bytes() == b""

def test_non_chat_configuration_does_not_invalidate_current_chat():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        dummy = Dummy()
        async def delayed(scope, receive, send):
            if scope["path"] == "/api/chat":
                entered.set()
                await release.wait()
            await dummy(scope, receive, send)
        app = create_fault_app(delayed, TOKEN)
        headers = {"X-Acceptance-Control": TOKEN}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": 1})
            current = asyncio.create_task(client.post("/api/chat"))
            await entered.wait()
            await client.post("/__acceptance__/faults", headers=headers, json={"view_failures": 1, "workspace_failures": 1})
            release.set()
            assert (await current).status_code == 503
            assert (await client.get("/__acceptance__/faults", headers=headers)).json()["drop_chat_responses"] == 0
    run(scenario())

def test_old_generation_failed_response_preserves_new_generation():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        dummy = Dummy()
        async def delayed(scope, receive, send):
            if scope["path"] == "/api/chat" and not entered.is_set():
                entered.set()
                await release.wait()
            await dummy(scope, receive, send)
        app = create_fault_app(delayed, TOKEN)
        headers = {"X-Acceptance-Control": TOKEN}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": 1})
            current = asyncio.create_task(client.post("/api/chat"))
            await entered.wait()
            await client.post("/__acceptance__/faults", headers=headers, json={"drop_chat_responses": 1})
            dummy.body = b'{"status":"failed","persisted":false}'
            release.set()
            assert (await current).status_code == 200
            assert (await client.get("/__acceptance__/faults", headers=headers)).json()["drop_chat_responses"] == 1
            dummy.body = b'{"status":"completed","persisted":true}'
            assert (await client.post("/api/chat")).status_code == 503
    run(scenario())
