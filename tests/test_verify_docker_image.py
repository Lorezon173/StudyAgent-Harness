"""Pure gate tests: no mocked result is evidence of a real Docker run."""
import importlib.util
import json
from contextlib import nullcontext
from email.message import Message
from http.client import RemoteDisconnected
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

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


class ReadinessClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def monotonic(self):
        return self.now

    def wait(self, timeout):
        assert 0 < timeout <= 0.5
        assert timeout <= 120 - self.now
        self.waits.append(timeout)
        self.now += timeout


class HealthResponse:
    def __init__(self, status=200):
        self.status = status
        self.closed = False
        self.reads = 0
        self.headers = Message()
        self.headers['Content-Type'] = 'application/json'

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def read(self):
        self.reads += 1
        return b'{}'


def readiness_clock(module, monkeypatch):
    clock = ReadinessClock()
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(module, 'Event', lambda: clock, raising=False)
    return clock


@pytest.mark.parametrize('error_type', [RemoteDisconnected, ConnectionResetError])
def test_readiness_recovers_from_startup_disconnect_without_reading_body(monkeypatch, error_type):
    m = verifier()
    clock = readiness_clock(m, monkeypatch)
    response = HealthResponse()
    attempts = []

    def open_health(request, *, timeout):
        assert request.full_url == 'http://127.0.0.1:1234/health'
        assert request.get_method() == 'GET'
        attempts.append(timeout)
        if len(attempts) == 1:
            raise error_type('startup connection interrupted')
        return response

    monkeypatch.setattr(m, 'urlopen', open_health)
    assert m.wait_http('http://127.0.0.1:1234') is None
    assert len(attempts) == 2
    assert all(timeout <= 5 for timeout in attempts)
    assert clock.waits == [0.5]
    assert response.closed and response.reads == 0


@pytest.mark.parametrize('error_type', [RemoteDisconnected, ConnectionResetError, URLError, TimeoutError])
def test_readiness_persistent_network_error_stops_at_deadline(monkeypatch, error_type):
    m = verifier()
    clock = readiness_clock(m, monkeypatch)
    attempts = []

    def open_health(request, *, timeout):
        assert 0 < timeout <= min(5, 120 - clock.now)
        attempts.append(clock.now)
        clock.now += min(0.125, timeout)
        raise error_type('http://secret-user:secret-password@host/health')

    monkeypatch.setattr(m, 'urlopen', open_health)
    with pytest.raises(m.VerificationError) as failure:
        m.wait_http('http://127.0.0.1:1234')
    assert failure.value.status == 'blocked'
    assert 120 <= clock.now <= 120.000001
    assert attempts and clock.waits
    assert error_type.__name__ in str(failure.value)
    assert 'secret-password' not in str(failure.value)


def test_readiness_request_uses_only_remaining_budget(monkeypatch):
    m = verifier()
    clock = readiness_clock(m, monkeypatch)
    timeouts = []

    def open_health(request, *, timeout):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            clock.now = 119.25
        else:
            clock.now += timeout
        raise URLError('startup')

    monkeypatch.setattr(m, 'urlopen', open_health)
    with pytest.raises(m.VerificationError):
        m.wait_http('http://127.0.0.1:1234')
    assert timeouts == [5, 0.25]
    assert clock.waits == [0.5]
    assert clock.now == 120


def test_readiness_poll_wait_uses_only_remaining_budget(monkeypatch):
    m = verifier()
    clock = readiness_clock(m, monkeypatch)

    def open_health(request, *, timeout):
        assert clock.now < 119.75, 'probe repeated without bounded polling wait'
        clock.now = 119.75
        raise URLError('startup')

    monkeypatch.setattr(m, 'urlopen', open_health)
    with pytest.raises(m.VerificationError):
        m.wait_http('http://127.0.0.1:1234')
    assert clock.waits == [0.25]
    assert clock.now == 120


def test_readiness_rejects_success_arriving_after_deadline(monkeypatch):
    m = verifier()
    clock = readiness_clock(m, monkeypatch)
    response = HealthResponse()

    def open_health(request, *, timeout):
        clock.now = 120.01
        return response

    monkeypatch.setattr(m, 'urlopen', open_health)
    with pytest.raises(m.VerificationError) as failure:
        m.wait_http('http://127.0.0.1:1234')
    assert failure.value.status == 'blocked'
    assert response.closed and response.reads == 0


@pytest.mark.parametrize('status_as_exception', [False, True])
def test_readiness_retries_unhealthy_status_and_closes_response(monkeypatch, status_as_exception):
    m = verifier()
    clock = readiness_clock(m, monkeypatch)
    unhealthy = HealthResponse(status=503)
    healthy = HealthResponse()
    attempts = []
    http_error = HTTPError('http://127.0.0.1:1234/health', 503, 'starting', {}, None)
    closed_errors = []
    monkeypatch.setattr(http_error, 'close', lambda: closed_errors.append(True))

    def open_health(request, *, timeout):
        attempts.append(timeout)
        if len(attempts) == 1:
            if status_as_exception:
                raise http_error
            return unhealthy
        return healthy

    monkeypatch.setattr(m, 'urlopen', open_health)
    m.wait_http('http://127.0.0.1:1234')
    assert len(attempts) == 2 and clock.waits == [0.5]
    assert healthy.closed and healthy.reads == 0
    assert closed_errors if status_as_exception else unhealthy.closed


def test_readiness_does_not_swallow_unexpected_errors(monkeypatch):
    m = verifier()
    readiness_clock(m, monkeypatch)
    failure = ValueError('invalid probe setup')

    def open_health(request, *, timeout):
        raise failure

    monkeypatch.setattr(m, 'urlopen', open_health)
    with pytest.raises(ValueError) as caught:
        m.wait_http('http://127.0.0.1:1234')
    assert caught.value is failure


@pytest.mark.parametrize('error', [HTTPError('http://localhost/api/auth/login', 500, 'error', {}, None),
                                  RemoteDisconnected('business disconnected'),
                                  ConnectionResetError('business reset')])
def test_business_http_errors_are_not_retried(monkeypatch, error):
    m = verifier()
    attempts = []

    def open_business(request, *, timeout):
        attempts.append(request.full_url)
        raise error

    monkeypatch.setattr(m, 'urlopen', open_business)
    expected = m.VerificationError if isinstance(error, HTTPError) else type(error)
    with pytest.raises(expected):
        m.http('http://localhost', '/api/auth/login', payload={'username': 'verify'})
    assert attempts == ['http://localhost/api/auth/login']


@pytest.mark.parametrize('diagnostic_failure', [None, 'inspect', 'logs', 'note'])
def test_sandbox_failure_collects_sanitized_evidence_before_cleanup(tmp_path, monkeypatch, diagnostic_failure):
    m = verifier()
    runner = m.Runner(tmp_path)
    box = m.Sandbox(runner, 'candidate')
    commands = []
    failure = m.VerificationError('blocked', 'original readiness timeout')
    private = 'sk-private-model-key'
    runner.secrets.append(private)

    def run(args, **kwargs):
        commands.append(args)
        action = args[1]
        if action == diagnostic_failure:
            raise OSError('diagnostic unavailable ' + private)
        output = '1' if action == 'exec' else ''
        if action in ('inspect', 'logs'):
            output = (f'{private} password={box.password} jwt_secret_key={box.jwt} '
                      'postgresql://verify:db-private@pg/verify Bearer eyJ.private.token')
        return SimpleNamespace(stdout=output, stderr='', returncode=0)

    monkeypatch.setattr(m.subprocess, 'run', run)
    original_note = runner.note

    def note(value):
        if diagnostic_failure == 'note' and ('diagnostic' in str(value) or private in str(value)):
            raise OSError('log unavailable')
        original_note(value)

    monkeypatch.setattr(runner, 'note', note)
    with pytest.raises(m.VerificationError) as caught:
        with box:
            box.containers.append(box.app)
            raise failure
    assert caught.value is failure
    diagnostic_commands = [args for args in commands if args[1] in ('inspect', 'logs')]
    assert len(diagnostic_commands) == 4
    first_cleanup = next(i for i, args in enumerate(commands) if args[1] == 'rm')
    assert all(commands.index(args) < first_cleanup for args in diagnostic_commands)
    assert [args[-1] for args in diagnostic_commands].count(box.app) == 2
    assert [args[-1] for args in diagnostic_commands].count(box.pg) == 2
    for args in diagnostic_commands:
        if args[1] == 'logs':
            assert args[2:-1] == ['--tail', '100', '--timestamps']
        else:
            assert args[2] == '--format'
            assert args[3] == ('status={{.State.Status}} exit_code={{.State.ExitCode}} '
                               'oom_killed={{.State.OOMKilled}} restart_count={{.RestartCount}}')
    assert ['docker', 'rm', '-f', box.app] in commands
    assert ['docker', 'rm', '-f', box.pg] in commands
    assert ['docker', 'network', 'rm', box.network] in commands
    log = runner.log.read_text(encoding='utf-8')
    assert all(secret not in log for secret in (private, box.password, box.jwt, 'db-private', 'eyJ.private.token'))
    if diagnostic_failure is None:
        assert '[REDACTED]' in log


def test_sandbox_success_does_not_collect_failure_diagnostics(tmp_path, monkeypatch):
    m = verifier()
    runner = m.Runner(tmp_path)
    commands = []

    def run(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(stdout='1' if args[1] == 'exec' else '', stderr='', returncode=0)

    monkeypatch.setattr(m.subprocess, 'run', run)
    with m.Sandbox(runner, 'candidate'):
        pass
    assert not any(args[1] in ('inspect', 'logs') for args in commands)


@pytest.mark.parametrize('original_failure', [False, True])
@pytest.mark.parametrize('cleanup_failure', [None, 'app_io', 'pg_io', 'network_io', 'app_exit', 'network_exit'])
def test_cleanup_survives_persistent_log_io_failure_and_attempts_all_resources(
        tmp_path, monkeypatch, original_failure, cleanup_failure):
    m = verifier()
    runner = m.Runner(tmp_path)
    box = m.Sandbox(runner, 'candidate')
    commands = []
    failure = m.VerificationError('blocked', 'original readiness timeout')

    def run(args, **kwargs):
        commands.append(args)
        resource = ('app' if args == ['docker', 'rm', '-f', box.app] else
                    'pg' if args == ['docker', 'rm', '-f', box.pg] else
                    'network' if args == ['docker', 'network', 'rm', box.network] else None)
        if resource is not None and cleanup_failure == resource + '_io':
            raise OSError('Docker cleanup pipe unavailable')
        return SimpleNamespace(stdout='1' if args[1] == 'exec' else '', stderr='',
                               returncode=7 if resource is not None and cleanup_failure == resource + '_exit' else 0)

    def unavailable_log(value):
        raise OSError('verification log persistently unavailable')

    monkeypatch.setattr(m.subprocess, 'run', run)
    with (pytest.raises(m.VerificationError) if original_failure else nullcontext()) as caught:
        with box:
            box.containers.append(box.app)
            monkeypatch.setattr(runner, 'note', unavailable_log)
            if original_failure:
                raise failure
    if original_failure:
        assert caught.value is failure
    # Keep Runner.command real: successful subprocesses must not need log I/O to clean up.
    assert [args for args in commands if args[1] == 'rm' or args[1:3] == ['network', 'rm']] == [
        ['docker', 'rm', '-f', box.app],
        ['docker', 'rm', '-f', box.pg],
        ['docker', 'network', 'rm', box.network],
    ]
    if cleanup_failure is None:
        assert runner.checks == []
    else:
        resource = cleanup_failure.split('_')[0]
        expected_name = ('cleanup_' + box.app if resource == 'app' else
                         'cleanup_' + box.pg if resource == 'pg' else 'cleanup_network')
        assert len(runner.checks) == 1
        assert runner.checks[0]['name'] == expected_name
        assert runner.checks[0]['status'] == 'failed'
        assert 'cleanup failed' in runner.checks[0]['reason']
