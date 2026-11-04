Reconstructed pre-fix source, not a contemporaneously measured snapshot. Reversed only the recorded minimal patch; original test log is harness-native-red.log.
SHA256: 36BAEA690D65DB2B257CA9903627B6B0FB65A35A35E60D1A61F8EE720782E972

"""Loopback-only, isolated Task10 acceptance helper. No work occurs on import."""
import argparse
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import urlsplit, urlunsplit

LIMIT = 2 * 1024 * 1024
CONTROL_PATH = "/__acceptance__/faults"
RUNTIME_ROOT = Path(__file__).resolve().parents[5] / ".superpowers/runtime/task10-acceptance"
LIMITS = {"view_failures": 10, "workspace_failures": 10, "drop_chat_responses": 3}


async def respond(send, status, value):
    body = json.dumps(value).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class FaultMiddleware:
    def __init__(self, app, token):
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
            raise ValueError("invalid control token")
        self.app = app
        self.token = token
        self.counts = dict.fromkeys(LIMITS, 0)

    async def control(self, scope, receive, send):
        try:
            local = ipaddress.ip_address(scope.get("client", ("", 0))[0]).is_loopback
        except ValueError:
            local = False
        tokens = [value for key, value in scope.get("headers", []) if key.lower() == b"x-acceptance-control"]
        authorized = len(tokens) == 1 and hmac.compare_digest(tokens[0], self.token.encode())
        if not local or not authorized:
            await respond(send, 401, {"error": "unauthorized"})
            return
        if scope["method"] == "GET":
            await respond(send, 200, self.counts.copy())
            return
        if scope["method"] != "POST":
            await respond(send, 405, {"error": "method_not_allowed"})
            return
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > 1024:
                await respond(send, 400, {"error": "invalid_configuration"})
                return
            if not event.get("more_body", False):
                break
        try:
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError()
                    result[key] = value
                return result
            value = json.loads(body, object_pairs_hook=unique)
            if not isinstance(value, dict) or not value or any(
                key not in LIMITS or type(count) is not int or not 0 <= count <= LIMITS[key]
                for key, count in value.items()
            ):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            await respond(send, 400, {"error": "invalid_configuration"})
            return
        self.counts.update(value)
        await respond(send, 200, self.counts.copy())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        if path == CONTROL_PATH:
            await self.control(scope, receive, send)
            return
        failure = None
        if method == "PATCH":
            if path == "/api/workspace-state":
                failure = "workspace_failures"
            elif re.fullmatch(r"/api/sessions/[^/]+/view-state", path):
                # ASGI path is decoded. Encoded slashes cannot create a nested match.
                failure = "view_failures"
        if failure and self.counts[failure]:
            self.counts[failure] -= 1
            await respond(send, 503, {"error": "acceptance_injected_failure"})
            return
        if method != "POST" or path != "/api/chat" or not self.counts["drop_chat_responses"]:
            await self.app(scope, receive, send)
            return
        events = []
        size = 0
        passthrough = False

        async def capture(event):
            nonlocal size, passthrough
            if passthrough:
                await send(event)
                return
            size += len(event.get("body", b""))
            events.append(event)
            if size > LIMIT:
                passthrough = True
                for buffered in events:
                    await send(buffered)
                events.clear()

        # Do not replace until the inner application actually returns successfully.
        await self.app(scope, receive, capture)
        if passthrough:
            return
        starts = [event for event in events if event["type"] == "http.response.start"]
        bodies = [event for event in events if event["type"] == "http.response.body"]
        completed = False
        if len(starts) == 1 and 200 <= starts[0]["status"] < 300 and bodies and not bodies[-1].get("more_body", False):
            try:
                value = json.loads(b"".join(event.get("body", b"") for event in bodies))
                completed = isinstance(value, dict) and value.get("status") == "completed" and value.get("persisted") is True
            except (ValueError, UnicodeDecodeError):
                pass
        # Recheck and consume synchronously after success, including concurrent completions.
        if completed and self.counts["drop_chat_responses"]:
            self.counts["drop_chat_responses"] -= 1
            await respond(send, 503, {"error": "acceptance_injected_response_loss"})
        else:
            for event in events:
                await send(event)


def create_fault_app(real_app, control_token):
    return FaultMiddleware(real_app, control_token)


def validate_runtime_paths(database_path, control_file):
    root = RUNTIME_ROOT.resolve()
    # Refuse a relocated runtime root itself as well as child symlink escapes.
    expected = Path(__file__).resolve().parents[5].resolve() / ".superpowers/runtime/task10-acceptance"
    if root != expected:
        raise ValueError("runtime root escapes project")
    paths = []
    for raw in (database_path, control_file):
        path = Path(raw)
        if ".." in path.parts:
            raise ValueError("path traversal is not allowed")
        path = path.resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError("path must stay inside isolated runtime")
        if path.name.lower() == "study_agent.db" or (path.exists() and not path.is_file()):
            raise ValueError("invalid runtime file")
        paths.append(path)
    if paths[0] == paths[1]:
        raise ValueError("database and control file must differ")
    return tuple(paths)


def load_control_token(path):
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or set(value) != {"schema", "token"} or type(value["schema"]) is not int or value["schema"] != 1 or not isinstance(value["token"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["token"]):
                raise ValueError()
            return value["token"]
        except (ValueError, OSError):
            raise ValueError("invalid existing control file") from None
    token = secrets.token_hex(32)
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"schema": 1, "token": token}, stream)
    return token


def load_runtime_configuration(env_file, database_path, control_file, port=8001):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("invalid loopback port")
    if any(name in sys.modules for name in ("app.main", "app.core.config", "app.core.database")):
        raise RuntimeError("real application already imported; use a fresh isolated process")
    database, control = validate_runtime_paths(database_path, control_file)
    # Validate existing credentials before creating directories or changing environment.
    if control.exists():
        load_control_token(control)
    from dotenv import dotenv_values
    values = dotenv_values(env_file)
    model = {name: values.get(name) for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")}
    if any(not isinstance(value, str) or not value.strip() for value in model.values()):
        raise ValueError("model configuration is incomplete")
    parsed = urlsplit(model["OPENAI_BASE_URL"])
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid model endpoint")
    if parsed.hostname in ("host.docker.internal", "gateway.docker.internal"):
        host = "127.0.0.1" + (f":{parsed.port}" if parsed.port else "")
        model["OPENAI_BASE_URL"] = urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))
    database.parent.mkdir(parents=True, exist_ok=True)
    control.parent.mkdir(parents=True, exist_ok=True)
    token = load_control_token(control)
    os.environ.update(model)
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + database.as_posix()
    os.environ["RAG_ENABLED"] = "false"
    from app.core.database import engine
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    from app.main import app
    return create_fault_app(app, token), {"host": "127.0.0.1", "port": port}


def main():
    parser = argparse.ArgumentParser(description="Isolated Task10 acceptance helper")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--database-path", default=str(RUNTIME_ROOT / "acceptance.db"))
    parser.add_argument("--control-file", default=str(RUNTIME_ROOT / "control.json"))
    arguments = parser.parse_args()
    try:
        app, options = load_runtime_configuration(arguments.env_file, arguments.database_path, arguments.control_file, arguments.port)
    except (ValueError, OSError, RuntimeError):
        parser.exit(2, "Isolated acceptance configuration invalid; no service started.\n")
    import uvicorn
    uvicorn.run(app, **options)


if __name__ == "__main__":
    main()
