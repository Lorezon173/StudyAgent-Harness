"""Pure gate tests: no mocked result is evidence of a real Docker run."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'verify_docker_image.py'


def verifier():
    assert SCRIPT.exists(), 'Docker verification entry point is missing'
    spec = importlib.util.spec_from_file_location('verify_docker_image', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(tmp_path, phase, **changes):
    data = dict(source_sha='abc', image_id='sha256:test', dirty=False,
                source_diff_hash='clean', phase=phase, status='passed', exit_code=0,
                required_checks=list(verifier().REQUIRED[phase]),
                checks=[dict(name=name, status='passed', reason='ok') for name in verifier().REQUIRED[phase]])
    data.update(changes)
    folder = tmp_path / phase
    folder.mkdir()
    (folder / 'manifest.json').write_text(json.dumps(data))


def test_missing_evidence_is_not_run(tmp_path):
    m = verifier()
    assert m.aggregate(tmp_path, 'abc', 'sha256:test')[0] == 'not_run'


@pytest.mark.parametrize('phase,status', [('api-teaching', 'blocked'), ('api-auth', 'failed')])
def test_auth_does_not_override_teaching_or_failure(tmp_path, phase, status):
    m = verifier()
    for name in m.PHASES:
        evidence(tmp_path, name, status=status if name == phase else 'passed',
                 exit_code=m.EXIT[status] if name == phase else 0,
                 checks=[dict(name=check, status=status if name == phase else 'passed', reason='safe') for check in m.REQUIRED[name]])
    assert m.aggregate(tmp_path, 'abc', 'sha256:test')[0] == status


@pytest.mark.parametrize('changes', [dict(source_sha='other'), dict(image_id='other'),
                                      dict(dirty=True), dict(checks=[]), dict(exit_code=1)])
def test_gate_rejects_untrusted_identity_or_incomplete_checks(tmp_path, changes):
    m = verifier()
    for phase in m.PHASES:
        evidence(tmp_path, phase, **(changes if phase == 'structure' else {}))
    assert m.aggregate(tmp_path, 'abc', 'sha256:test')[0] == 'failed'


@pytest.mark.parametrize('value', ['', ' ', 'dev-secret-change-me-in-production'])
def test_effective_jwt_rejects_default_and_empty(value):
    assert verifier().jwt_valid(value) is False


def test_jwt_random_secret_and_redaction():
    m = verifier()
    secret = 'random-private-value-1234567890'
    assert m.jwt_valid(secret)
    output = m.sanitize(f'{secret} postgresql://u:dbpass@db/db Authorization: Bearer eyJ.abc.def', [secret])
    assert secret not in output and 'dbpass' not in output and 'eyJ.abc.def' not in output


def test_missing_model_config_is_blocked():
    assert verifier().teaching_ready({}) is False


def test_status_priority():
    m = verifier()
    assert m.overall(['blocked', 'failed', 'not_run']) == 'failed'
    assert m.overall(['passed', 'not_run']) == 'not_run'


def test_command_failure_is_failed_not_passed(tmp_path):
    import sys
    m = verifier()
    runner = m.Runner(tmp_path)
    runner.check('child_exit', lambda: runner.command([sys.executable, '-c', 'raise SystemExit(7)']))
    assert runner.checks[0]['status'] == 'failed'


def test_missing_executable_is_blocked(tmp_path):
    m = verifier()
    runner = m.Runner(tmp_path)
    runner.check('missing_runtime', lambda: runner.command(['sa-no-such-executable-924322']))
    assert runner.checks[0]['status'] == 'blocked'


def test_failed_assertion_resources_is_failed(tmp_path):
    m = verifier()
    runner = m.Runner(tmp_path)
    def missing_resource():
        assert (tmp_path / 'missing.ini').is_file()
    runner.check('runtime_resources', missing_resource)
    assert runner.checks[0]['status'] == 'failed'


def test_gate_rejects_missing_candidate_checksum(tmp_path):
    m = verifier()
    for phase in m.PHASES:
        evidence(tmp_path, phase)
    status, _ = m.aggregate(tmp_path, 'abc', 'sha256:test',
                            dict(source_sha='abc', image_id='sha256:test', dirty=False))
    assert status == 'failed'


def test_gate_rejects_arbitrary_passed_check_in_place_of_runtime_checks(tmp_path):
    m = verifier()
    for phase in m.PHASES:
        evidence(tmp_path, phase, required_checks=['arbitrary'], checks=[dict(name='arbitrary', status='passed')])
    status, _ = m.aggregate(tmp_path, 'abc', 'sha256:test')
    assert status == 'failed'


def test_malformed_manifest_is_failed_and_does_not_crash(tmp_path):
    m = verifier()
    (tmp_path / 'structure').mkdir()
    (tmp_path / 'structure' / 'manifest.json').write_text('[]')
    assert m.aggregate(tmp_path, 'abc', 'sha256:test')[0] == 'failed'


def test_candidate_checksum_invalid_type_is_failed(tmp_path):
    m = verifier()
    for phase in m.PHASES:
        evidence(tmp_path, phase)
    status, _ = m.aggregate(tmp_path, 'abc', 'sha256:test',
                            dict(source_sha='abc', image_id='sha256:test', dirty=False, archive_sha256=123))
    assert status == 'failed'


@pytest.mark.parametrize('first_result', ['connection_refused', '0'])
def test_pg_socket_ready_does_not_finish_before_tcp_select_one(tmp_path, monkeypatch, first_result):
    """Only the Docker boundary is simulated; exercise actual sandbox readiness."""
    m = verifier()
    runner = m.Runner(tmp_path)
    box = m.Sandbox(runner, 'candidate')
    sql_calls = []
    cleanup = []

    def docker(*args, **kwargs):
        if args[0] == 'exec' and 'pg_isready' in args:
            return ''  # Official init server's socket can already be available.
        if args[0] == 'exec' and 'psql' in args:
            sql_calls.append((args, kwargs))
            if len(sql_calls) == 1:
                if first_result == 'connection_refused':
                    raise m.VerificationError('failed', 'TCP connection refused during init')
                return first_result
            return '1'
        if args[0] in ('rm', 'network'):
            cleanup.append(args)
        return ''

    monkeypatch.setattr(runner, 'docker', docker)
    with box:
        assert len(sql_calls) == 2, 'socket availability is insufficient for readiness'
        for args, kwargs in sql_calls:
            assert args[args.index('-h') + 1] == '127.0.0.1'
            assert args[args.index('-U') + 1] == 'verify'
            assert args[args.index('-d') + 1] == 'verify'
            assert args[-1] == 'SELECT 1'
            assert 'PGPASSWORD' in args and box.password not in args
            assert kwargs['env']['PGPASSWORD'] == box.password
            assert kwargs['timeout'] <= 10
    assert ('rm', '-f', box.pg) in cleanup
    assert ('network', 'rm', box.network) in cleanup


def test_pg_tcp_probe_timeout_cleans_owned_resources(tmp_path, monkeypatch):
    m = verifier()
    runner = m.Runner(tmp_path)
    box = m.Sandbox(runner, 'candidate')
    cleanup = []

    def docker(*args, **kwargs):
        if args[0] == 'exec' and 'pg_isready' in args:
            return ''
        if args[0] == 'exec' and 'psql' in args:
            raise m.VerificationError('blocked', 'Docker client timed out')
        if args[0] in ('rm', 'network'):
            cleanup.append(args)
        return ''

    monkeypatch.setattr(runner, 'docker', docker)
    with pytest.raises(m.VerificationError, match='timed out') as failure:
        with box:
            pytest.fail('sandbox entered despite TCP probe timeout')
    assert failure.value.status == 'blocked'
    assert ('rm', '-f', box.pg) in cleanup
    assert ('network', 'rm', box.network) in cleanup
