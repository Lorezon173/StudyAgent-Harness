"""Candidate publication must fail closed for incomplete or altered evidence."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/docker_candidate.py"
EXPECTED = {
    "structure": ["runtime_resources"],
    "migration": ["pg_empty_and_repeat", "pg_historical_preservation", "pg_reject_missing_mastery",
                  "pg_reject_nonnumeric_user", "pg_reject_orphan_user", "sqlite_upgrade"],
    "api-auth": ["effective_jwt_valid", "health_frontend_auth"],
    "api-teaching": ["effective_jwt_valid", "health_frontend_auth", "real_teaching_restart_ownership"],
    "all": ["structure", "migration", "api-auth", "api-teaching", "candidate_identity"],
}


def helper():
    assert MODULE.exists(), "candidate validation helper is not implemented"
    spec = importlib.util.spec_from_file_location("docker_candidate", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate(tmp_path):
    (tmp_path / "image.tar").write_bytes(b"saved image")
    data = {"version": 1, "image_ref": "candidate:test", "image_id": "sha256:" + "a" * 64,
            "source_sha": "b" * 40, "dirty": False, "archive": "image.tar",
            "archive_sha256": hashlib.sha256(b"saved image").hexdigest()}
    (tmp_path / "candidate.json").write_text(json.dumps(data))
    for phase in ("structure", "migration", "api-auth", "api-teaching", "all"):
        folder = tmp_path / phase
        folder.mkdir()
        checks = [{"name": name, "status": "passed"} for name in EXPECTED[phase]]
        manifest = {"source_sha": data["source_sha"], "image_id": data["image_id"],
                    "dirty": False, "source_diff_hash": "", "phase": phase,
                    "status": "passed", "exit_code": 0,
                    "required_checks": EXPECTED[phase], "checks": checks}
        if phase == "all":
            manifest["archive_sha256"] = data["archive_sha256"]
        (folder / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path, data


def change(root, phase, **updates):
    path = root / phase / "manifest.json"
    data = json.loads(path.read_text())
    data.update(updates)
    path.write_text(json.dumps(data))


def test_complete_candidate_is_accepted(candidate):
    root, data = candidate
    assert helper().gate(root, data["source_sha"], root)["image_id"] == data["image_id"]


@pytest.mark.parametrize("phase", ["structure", "migration", "api-auth", "api-teaching", "all"])
def test_missing_phase_blocks_publication(candidate, phase):
    root, data = candidate
    (root / phase / "manifest.json").unlink()
    with pytest.raises(ValueError):
        helper().gate(root, data["source_sha"], root)


@pytest.mark.parametrize("phase", list(EXPECTED))
def test_arbitrary_self_reported_check_cannot_replace_canonical_checks(candidate, phase):
    root, data = candidate
    change(root, phase, required_checks=["invented"], checks=[{"name": "invented", "status": "passed"}])
    with pytest.raises(ValueError):
        helper().gate(root, data["source_sha"], root)


@pytest.mark.parametrize("missing", EXPECTED["all"])
def test_all_requires_every_phase_and_candidate_identity(candidate, missing):
    root, data = candidate
    names = [name for name in EXPECTED["all"] if name != missing]
    change(root, "all", required_checks=names,
           checks=[{"name": name, "status": "passed"} for name in names])
    with pytest.raises(ValueError):
        helper().gate(root, data["source_sha"], root)


@pytest.mark.parametrize("archive_hash", [None, "0" * 64, 42])
def test_all_must_bind_the_same_archive(candidate, archive_hash):
    root, data = candidate
    change(root, "all", archive_sha256=archive_hash)
    with pytest.raises(ValueError):
        helper().gate(root, data["source_sha"], root)


@pytest.mark.parametrize("updates", [
    {"status": "blocked", "exit_code": 2}, {"status": "not_run", "exit_code": 3},
    {"source_sha": "c" * 40}, {"image_id": "sha256:" + "d" * 64},
    {"dirty": True}, {"dirty": "false"}, {"required_checks": []},
    {"checks": []}, {"checks": [{"name": "verified", "status": "failed"}]},
])
def test_invalid_teaching_blocks_publication(candidate, updates):
    root, data = candidate
    change(root, "api-teaching", **updates)
    with pytest.raises(ValueError):
        helper().gate(root, data["source_sha"], root)


def test_archive_tampering_blocks_load(candidate):
    root, data = candidate
    (root / "image.tar").write_bytes(b"altered")
    with pytest.raises(ValueError):
        helper().verify(root, data["source_sha"])


@pytest.mark.parametrize("updates", [{"archive": "../image.tar"}, {"version": True},
                                    {"image_id": None}, {"source_sha": "c" * 40}])
def test_invalid_candidate_metadata_rejected(candidate, updates):
    root, data = candidate
    path = root / "candidate.json"
    path.write_text(json.dumps(data | updates))
    with pytest.raises(ValueError):
        helper().verify(root, data["source_sha"])


def test_loaded_wrong_revision_is_rejected(candidate, monkeypatch):
    _, data = candidate
    module = helper()
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: json.dumps([
        {"Id": data["image_id"], "Config": {"Labels": {"org.opencontainers.image.revision": "c" * 40}}}
    ]))
    with pytest.raises(ValueError):
        module.check_image(data)


def test_corrupt_archive_is_rejected_before_docker_load(candidate, monkeypatch):
    root, data = candidate
    (root / "image.tar").write_bytes(b"corrupt")
    module = helper()
    monkeypatch.setattr(sys, "argv", ["docker_candidate.py", "load", "--directory", str(root),
                                    "--source-sha", data["source_sha"]])
    def forbidden_load(*args, **kwargs):
        pytest.fail("unverified archive must never reach Docker")
    monkeypatch.setattr(module.subprocess, "run", forbidden_load)
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 1
