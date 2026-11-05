"""Same-run, real HTTP/PG/model acceptance; no scenario creation or mocks.

Requires an existing browser manifest and an isolated task13_acceptance_* database.
TASK13_PHASE is baseline, app_restarted, pg_restarted or isolation.  Baseline
is frozen to TASK13_BASELINE_PATH for subsequent independent invocations.
"""
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def required(name):
    value = os.environ.get(name)
    assert value, f"missing {name}; a real run cannot be reconstructed"
    return value


def runtime_file(name):
    target = Path(required(name)).resolve()
    root = (Path.cwd() / ".superpowers" / "runtime" / "task13").resolve()
    assert root in target.parents, f"{name} must be in the private Task13 runtime"
    return target


@pytest.fixture
def run():
    manifest = json.loads(runtime_file("TASK13_MANIFEST_PATH").read_text(encoding="utf-8"))
    assert manifest["format_version"] == 1
    assert manifest["run_id"] == required("TASK13_RUN_ID")
    assert manifest["candidate_commit"] == required("TASK13_CANDIDATE_COMMIT")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert head == manifest["candidate_commit"]
    assert manifest["users"]["a"]["id"] != manifest["users"]["b"]["id"]
    url = make_url(required("TASK13_DATABASE_URL"))
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"localhost", "127.0.0.1"} and url.database.startswith("task13_acceptance_")
    assert url.database == required("TASK13_DATABASE_NAME")
    api = urlsplit(required("TASK13_API_URL"))
    assert api.scheme == "http" and api.hostname in {"localhost", "127.0.0.1"} and api.port and api.path in {"", "/"} and not api.query
    for key in ("initial", "s2", "s3", "resume", "draft"):
        assert manifest["markers"][key + "_sha256"] == digest(required("TASK13_MARKER_" + key.upper()))
    phase = required("TASK13_PHASE")
    assert phase in {"baseline", "app_restarted", "pg_restarted", "isolation"}
    engine = sa.create_engine(url.set(drivername="postgresql+psycopg"))
    clients = {}
    try:
        for user in ("a", "b"):
            client = httpx.Client(base_url=required("TASK13_API_URL"), timeout=30, trust_env=False)
            response = client.post("/api/auth/login", json={
                "username": required("TASK13_" + user.upper() + "_USERNAME"),
                "password": required("TASK13_" + user.upper() + "_PASSWORD"),
            })
            assert response.status_code == 200
            auth = response.json()
            assert auth["user_id"] == manifest["users"][user]["id"] and auth["token"]
            client.headers["Authorization"] = "Bearer " + auth["token"]
            clients[user] = client
        yield manifest, phase, engine, clients
    finally:
        for client in clients.values():
            client.close()
        engine.dispose()


def get(client, path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response.json()


def establish_interrupted(client, session_id):
    """Disconnect a real HTTP request only after its claimed state is visible."""
    target = urlsplit(required("TASK13_API_URL"))
    assert target.scheme == "http" and target.hostname in {"127.0.0.1", "localhost"}
    assert target.port and target.path in {"", "/"} and not target.query
    for _ in range(3):
        snapshot = get(client, f"/api/sessions/{session_id}/snapshot")
        assert snapshot["session"]["active_request_id"] is None
        request_id = "task13-disconnect-" + uuid4().hex
        payload = json.dumps({"session_id": session_id, "request_id": request_id,
            "expected_state_version": snapshot["session"]["state_version"],
            "message": "Task13 隔离账号断连正对照"}, ensure_ascii=False).encode("utf-8")
        request_path = f"/api/sessions/{session_id}/requests/{request_id}"
        headers = (f"POST /api/chat HTTP/1.1\r\nHost: {target.hostname}:{target.port}\r\n"
            f"Authorization: {client.headers['Authorization']}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n").encode("ascii")
        deadline = time.monotonic() + 60
        claimed = False
        with socket.create_connection((target.hostname, target.port), timeout=10) as stream:
            stream.sendall(headers + payload)
            while time.monotonic() < deadline:
                response = client.get(request_path)
                if response.status_code == 404:
                    continue
                assert response.status_code == 200
                status = response.json()["status"]
                if status == "running":
                    claimed = True
                    break
                if status in {"completed", "failed", "interrupted"}:
                    break
                raise AssertionError("unexpected request status")
            if claimed:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    # Completion may race the disconnect; only persisted interruption counts.
                    pass
        while time.monotonic() < deadline:
            response = client.get(request_path)
            if response.status_code == 404:
                continue
            assert response.status_code == 200
            result = response.json()
            if result["status"] == "interrupted" and claimed and result["error_code"] == "client_disconnected":
                return result
            if result["status"] in {"completed", "failed", "interrupted"}:
                break
        # A request that is still running is not safe to replace with another.
        assert get(client, f"/api/sessions/{session_id}/snapshot")["session"]["active_request_id"] is None
    raise AssertionError("unable to observe a claimed request interrupted by the HTTP disconnect")


def collect(manifest, engine, client):
    user = manifest["users"]["a"]["id"]
    ids = {name: manifest["sessions"][name]["id"] for name in ("s1", "s2", "s3")}
    profiles = {name: manifest["profiles"][name]["id"] for name in ("t1", "t2")}
    assert len(set(ids.values())) == 3 and len(set(profiles.values())) == 2
    workspace = get(client, "/api/workspace-state")
    assert workspace["last_session_id"] == ids["s1"]
    assert workspace["version"] == manifest["versions"]["final_workspace_version"]
    snapshots = {name: get(client, f"/api/sessions/{sid}/snapshot") for name, sid in ids.items()}
    detail = {name: get(client, f"/api/topic-profiles/{pid}") for name, pid in profiles.items()}
    summaries = {name: get(client, f"/api/topic-profiles/{pid}/summary") for name, pid in profiles.items()}
    library = get(client, f"/api/knowledge/{manifest['library']['a']['id']}")
    assert library["user_id"] == user
    for name, profile in (("s1", "t1"), ("s2", "t1"), ("s3", "t2")):
        snap = snapshots[name]
        assert snap["session"]["user_id"] == user and snap["session"]["profile_id"] == profiles[profile]
        assert snap["profile_summary"]["profile_revision"] == detail[profile]["profile_revision"] == summaries[profile]["profile_revision"]
    s1 = snapshots["s1"]
    assert s1["session"]["active_node_id"] == manifest["nodes"]["s1"]["id"]
    assert s1["session"]["state_version"] == manifest["versions"]["s1_state"]
    assert s1["view_state"]["version"] == manifest["versions"]["final_view_version"]
    assert digest(s1["view_state"]["draft"]) == manifest["versions"]["final_draft_sha256"]
    assert detail["t1"]["profile_revision"] == manifest["versions"]["t1_revision"]
    assert detail["t2"]["profile_revision"] == manifest["versions"]["t2_revision"]
    assert manifest["versions"]["before_t1_revision"] < manifest["versions"]["t1_revision"]
    assert manifest["versions"]["before_t2_revision"] == manifest["versions"]["t2_revision"]
    requests = {}
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        assert conn.scalar(sa.text("SELECT current_database()")) == required("TASK13_DATABASE_NAME")
        pg_started = conn.scalar(sa.text("SELECT pg_postmaster_start_time()::text"))
        migration = conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
        assert migration == required("TASK13_ALEMBIC_HEAD")
        workspace_row = conn.execute(sa.text("SELECT last_session_id, version FROM user_workspace_states WHERE user_id=:u"), {"u": user}).mappings().one()
        assert dict(workspace_row) == {"last_session_id": workspace["last_session_id"], "version": workspace["version"]}
        for name, pid in profiles.items():
            profile_row = conn.execute(sa.text("SELECT user_id, revision FROM topic_profiles WHERE id=:p"), {"p": pid}).mappings().one()
            assert profile_row["user_id"] == user and profile_row["revision"] == detail[name]["profile_revision"]
        library_row = conn.execute(sa.text("SELECT user_id, profile_id, name, description, content_text FROM library_items WHERE id=:id"), {"id": manifest["library"]["a"]["id"]}).mappings().one()
        library_row = dict(library_row)
        assert library_row == {key: library[key] for key in library_row}
        for turn, session in (("s1_initial", "s1"), ("s2", "s2"), ("s3", "s3"), ("s1_resume", "s1")):
            expected = manifest["turns"][turn]
            sid = ids[session]
            marker = {"s1_initial": "initial", "s2": "s2", "s3": "s3", "s1_resume": "resume"}[turn]
            assert expected["persisted"] is True and expected["status"] == "completed"
            request = get(client, f"/api/sessions/{sid}/requests/{expected['request_id']}")
            assert request["user_id"] == user and request["status"] == "completed"
            assert request["attempt"] == expected["attempt"] and request["response_json"]["persisted"] is True
            assert digest(request["request_payload"]["message"]) == manifest["markers"][marker + "_sha256"]
            assert request["response_json"]["reply"] and digest(request["response_json"]["reply"]) == expected["reply_sha256"]
            row = conn.execute(sa.text("SELECT status, attempt, response_json, active_node_id FROM chat_requests WHERE user_id=:u AND session_id=:s AND request_id=:r"), {"u": user, "s": sid, "r": expected["request_id"]}).mappings().one()
            assert row["status"] == request["status"] and row["attempt"] == request["attempt"]
            assert row["response_json"] == request["response_json"]
            messages = get(client, f"/api/sessions/{sid}/messages?limit=100")["items"]
            selected = [m for m in messages if m["id"] in (expected["user_message_id"], expected["assistant_message_id"])]
            assert len(selected) == 2 and {m["role"] for m in selected} == {"user", "assistant"}
            assert len({m["turn_index"] for m in selected}) == 1
            assistant = next(m for m in selected if m["role"] == "assistant")
            answer = next(m for m in selected if m["role"] == "user")
            assert answer["content"] == request["request_payload"]["message"]
            assert assistant["content"] == request["response_json"]["reply"]
            database_messages = conn.execute(sa.text("SELECT id, role, content, turn_index FROM messages WHERE session_id=:s AND id IN (:u, :a) ORDER BY id"), {"s": sid, "u": expected["user_message_id"], "a": expected["assistant_message_id"]}).mappings().all()
            assert [{k: m[k] for k in ("id", "role", "content", "turn_index")} for m in selected] == [dict(m) for m in database_messages]
            requests[turn] = {"request_id": expected["request_id"], "attempt": request["attempt"], "message_ids": sorted(m["id"] for m in selected), "reply_sha256": expected["reply_sha256"]}
        resume = manifest["turns"]["s1_resume"]
        evidence = conn.execute(sa.text("SELECT node_id, message_id FROM profile_evidence WHERE user_id=:u AND session_id=:s AND request_id=:r"), {"u": user, "s": ids["s1"], "r": resume["request_id"]}).mappings().all()
        assert len(evidence) == 1 and evidence[0]["node_id"] == manifest["nodes"]["s1"]["id"]
        assert evidence[0]["message_id"] == resume["user_message_id"]
        session_rows = conn.execute(sa.text("SELECT id, user_id, profile_id, active_node_id, state_version, state_json FROM sessions WHERE id IN (:s1,:s2,:s3) ORDER BY id"), ids).mappings().all()
        assert len(session_rows) == 3
        for row in session_rows:
            snap = next(value for value in snapshots.values() if value["session"]["session_id"] == row["id"])
            assert row["user_id"] == user and row["profile_id"] == snap["session"]["profile_id"]
            assert row["active_node_id"] == snap["session"]["active_node_id"] and row["state_version"] == snap["session"]["state_version"]
            assert json.loads(row["state_json"]) == snap["teaching_state"]
        view = conn.execute(sa.text("SELECT draft, version FROM session_view_states WHERE user_id=:u AND session_id=:s"), {"u": user, "s": ids["s1"]}).mappings().one()
        assert view["version"] == s1["view_state"]["version"] and digest(view["draft"]) == manifest["versions"]["final_draft_sha256"]
    return {"requests": requests, "snapshots_sha256": {k: digest(json.dumps(v, sort_keys=True, ensure_ascii=False)) for k, v in snapshots.items()}, "profiles_sha256": {k: digest(json.dumps(v, sort_keys=True, ensure_ascii=False)) for k, v in detail.items()}, "library_sha256": digest(json.dumps(library, sort_keys=True, ensure_ascii=False)), "pg_started": pg_started, "migration": migration}


def test_real_readback_and_model_witness(run):
    manifest, phase, engine, clients = run
    if phase == "isolation":
        pytest.skip("readback is verified in the restart phases")
    observed = collect(manifest, engine, clients["a"])
    witness = [json.loads(line) for line in runtime_file("TASK13_WITNESS_PATH").read_text(encoding="utf-8").splitlines()]
    turn = manifest["turns"]["s1_resume"]
    matches = [w for w in witness if w["run_id"] == manifest["run_id"] and w["context"] and w["context"]["user_id"] == manifest["users"]["a"]["id"] and w["context"]["session_id"] == manifest["sessions"]["s1"]["id"] and w["context"]["request_id"] == turn["request_id"] and w["context"]["attempt"] == turn["attempt"] and w["node"] in {"tutor", "critic"}]
    assert matches, "no matching successful model invocation"
    assert any(w["real_client"] and w["call_session_matches"] and w["context"]["stage"] == "awaiting_response" and w["context"]["question_message_id"] == manifest["turns"]["s1_initial"]["assistant_message_id"] and w["question_sha256"] == manifest["markers"]["question_sha256"] and w["question_matches_previous_assistant"] and w["question_in_history"] and w["initial_in_history"] and w["resume_is_current_input"] and w["s2_absent_both_prompts"] and w["s3_absent_both_prompts"] for w in matches)
    baseline_path = runtime_file("TASK13_BASELINE_PATH")
    stage = json.loads(runtime_file("TASK13_STAGE_EVIDENCE_PATH").read_text(encoding="utf-8"))
    assert stage["run_id"] == manifest["run_id"] and stage["phase"] == phase
    assert stage["database"] == required("TASK13_DATABASE_NAME")
    assert stage["pg_started"] == observed["pg_started"]
    assert all(stage[key] for key in ("container_id", "volume_id", "app_identity"))
    if phase == "baseline":
        assert not baseline_path.exists(), "never overwrite the frozen baseline"
        baseline_path.write_text(json.dumps({"run_id": manifest["run_id"], "stage": stage, "observed": observed}, ensure_ascii=False), encoding="utf-8")
    else:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        assert baseline["run_id"] == manifest["run_id"]
        assert stage["app_identity"] != baseline["stage"]["app_identity"]
        if phase == "app_restarted":
            assert stage["container_id"] == baseline["stage"]["container_id"]
        assert stage["volume_id"] == baseline["stage"]["volume_id"]
        previous = baseline["observed"]
        assert {k: v for k, v in observed.items() if k != "pg_started"} == {k: v for k, v in previous.items() if k != "pg_started"}
        assert (observed["pg_started"] != previous["pg_started"]) == (phase == "pg_restarted")
        if phase == "pg_restarted":
            app_checkpoint = json.loads(baseline_path.with_suffix(".app_restarted.json").read_text(encoding="utf-8"))
            assert app_checkpoint["run_id"] == manifest["run_id"] and app_checkpoint["phase"] == "app_restarted"
        checkpoint = baseline_path.with_suffix(f".{phase}.json")
        with checkpoint.open("x", encoding="utf-8") as stream:
            json.dump(stage, stream, ensure_ascii=False)


def test_cross_account_isolation(run):
    manifest, phase, engine, clients = run
    if phase != "isolation":
        pytest.skip("isolation runs only after both restart stages")
    checkpoint = runtime_file("TASK13_BASELINE_PATH").with_suffix(".pg_restarted.json")
    restarted = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert restarted["run_id"] == manifest["run_id"] and restarted["phase"] == "pg_restarted"
    a, b = clients["a"], clients["b"]
    before = collect(manifest, engine, a)
    assert before["pg_started"] == restarted["pg_started"]
    a_sid, b_sid = (manifest["sessions"][name]["id"] for name in ("s1", "b"))
    a_pid, b_pid = (manifest["profiles"][name]["id"] for name in ("t1", "b"))
    a_node, b_node = (manifest["nodes"][name]["id"] for name in ("s1", "b"))
    a_library, b_library = (manifest["library"][name]["id"] for name in ("a", "b"))
    a_request = manifest["turns"]["s1_resume"]["request_id"]
    b_snapshot = get(b, f"/api/sessions/{b_sid}/snapshot")
    assert b_snapshot["session"]["user_id"] == manifest["users"]["b"]["id"]
    b_profile = get(b, f"/api/topic-profiles/{b_pid}")
    assert any(node["id"] == b_node for node in b_profile["nodes"])
    get(b, f"/api/topic-profiles/{b_pid}/summary")
    get(b, f"/api/knowledge/{b_library}")
    get(b, f"/api/sessions/{b_sid}/messages?limit=100")
    b_request = establish_interrupted(b, b_sid)
    assert b_request["request_id"] != a_request
    assert b_request["error_code"] == "client_disconnected"
    state_version = get(b, f"/api/sessions/{b_sid}/snapshot")["session"]["state_version"]
    assert b_request["base_state_version"] == state_version
    before_messages = get(b, f"/api/sessions/{b_sid}/messages?limit=100")["items"]
    positive = b.post(f"/api/sessions/{b_sid}/requests/{b_request['request_id']}/retry", json={"expected_attempt": b_request["attempt"], "expected_state_version": state_version}, timeout=360)
    assert positive.status_code == 200
    assert positive.json()["persisted"] is True and positive.json()["status"] == "completed"
    assert positive.json()["attempt"] == b_request["attempt"] + 1
    after_messages = get(b, f"/api/sessions/{b_sid}/messages?limit=100")["items"]
    assert len(after_messages) == len(before_messages) + 2
    assert after_messages[-1]["role"] == "assistant" and after_messages[-1]["content"] == positive.json()["reply"]
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        row = conn.execute(sa.text("SELECT status, attempt, response_json FROM chat_requests WHERE user_id=:u AND session_id=:s AND request_id=:r"), {"u": manifest["users"]["b"]["id"], "s": b_sid, "r": b_request["request_id"]}).mappings().one()
        assert row["status"] == "completed" and row["attempt"] == positive.json()["attempt"]
        assert row["response_json"] == positive.json()
        for message in after_messages[-2:]:
            stored = conn.execute(sa.text("SELECT role, content, turn_index FROM messages WHERE session_id=:s AND id=:id"), {"s": b_sid, "id": message["id"]}).mappings().one()
            stored = dict(stored)
            assert stored == {key: message[key] for key in stored}
    b_snapshot = get(b, f"/api/sessions/{b_sid}/snapshot")
    valid_node = b.patch(f"/api/sessions/{b_sid}/active-node", json={"expected_state_version": b_snapshot["session"]["state_version"], "node_id": b_node})
    assert valid_node.status_code == 200 and valid_node.json()["active_node_id"] == b_node
    b_snapshot = get(b, f"/api/sessions/{b_sid}/snapshot")
    matrix = [
        ("GET", f"/api/sessions/{a_sid}/snapshot", None, 403),
        ("GET", f"/api/sessions/{a_sid}/messages?limit=100", None, 403),
        ("GET", f"/api/topic-profiles/{a_pid}", None, 404),
        ("GET", f"/api/topic-profiles/{a_pid}/summary", None, 404),
        ("PATCH", f"/api/topic-profiles/{a_pid}", {"expected_revision": manifest["versions"]["t1_revision"], "name": "task13-denied"}, 404),
        ("PATCH", f"/api/topic-profiles/{b_pid}/nodes/{a_node}", {"expected_revision": b_profile["profile_revision"], "title": "task13-denied"}, 404),
        ("PATCH", f"/api/sessions/{b_sid}/active-node", {"expected_state_version": b_snapshot["session"]["state_version"], "node_id": a_node}, 404),
        ("GET", f"/api/knowledge/{a_library}", None, 404),
        ("PATCH", f"/api/knowledge/{a_library}", {"name": "task13-denied"}, 404),
        ("GET", f"/api/sessions/{a_sid}/requests/{a_request}", None, 403),
        ("GET", f"/api/sessions/{b_sid}/requests/{a_request}", None, 404),
        ("POST", f"/api/sessions/{a_sid}/requests/{a_request}/retry", {"expected_attempt": manifest["turns"]["s1_resume"]["attempt"], "expected_state_version": manifest["versions"]["s1_state"]}, 403),
        ("POST", f"/api/sessions/{b_sid}/requests/{a_request}/retry", {"expected_attempt": 1, "expected_state_version": b_snapshot["session"]["state_version"]}, 404),
    ]
    markers = [required("TASK13_MARKER_" + name) for name in ("INITIAL", "S2", "S3", "RESUME", "DRAFT")]
    for method, path, payload, status in matrix:
        response = b.request(method, path, json=payload)
        assert response.status_code == status, (method, path, response.status_code, status)
        assert all(marker not in response.text for marker in markers)
    assert collect(manifest, engine, a) == before
