"""Run isolated, real candidate-image checks; never load a local .env file.

Unit tests of the gate are separate from the Docker evidence produced here.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PHASES = ('structure', 'migration', 'api-auth', 'api-teaching')
EXIT = {'passed': 0, 'failed': 1, 'blocked': 2, 'not_run': 3}
REQUIRED = {
    'structure': ('runtime_resources',),
    'migration': ('pg_empty_and_repeat', 'pg_historical_preservation',
                  'pg_reject_missing_mastery', 'pg_reject_nonnumeric_user',
                  'pg_reject_orphan_user', 'sqlite_upgrade'),
    'api-auth': ('effective_jwt_valid', 'health_frontend_auth'),
    'api-teaching': ('effective_jwt_valid', 'health_frontend_auth', 'real_teaching_restart_ownership'),
}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JWT = 'dev-secret-change-me-in-production'


def overall(statuses):
    return next((s for s in ('failed', 'blocked', 'not_run') if s in statuses), 'passed')


def jwt_valid(value):
    return bool(value and value.strip() and value.strip() != DEFAULT_JWT)


def teaching_ready(env):
    return (env.get('DOCKER_VERIFY_MODEL_TESTS') == '1'
            and all(env.get(k, '').strip() for k in
                    ('OPENAI_API_KEY', 'OPENAI_MODEL', 'EMBEDDING_MODEL', 'EMBEDDING_DIM'))
            and env.get('RAG_BACKEND') == 'pgvector')


def sanitize(value, secret_values=()):
    value = str(value)
    for secret in sorted((s for s in secret_values if s), key=len, reverse=True):
        value = value.replace(secret, '[REDACTED]')
    value = re.sub(r'(\w+(?:\+\w+)?://[^\s:/]+:)[^\s@]+@', r'\1[REDACTED]@', value)
    value = re.sub(r'(?i)(Bearer\s+)\S+', r'\1[REDACTED]', value)
    value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', value)
    value = re.sub(r'(?i)(["\x27]?(?:token|password|api_key|jwt_secret_key)["\x27]?\s*[:=]\s*)[^,\s}]+',
                   r'\1[REDACTED]', value)
    return value


def aggregate(evidence_root, source_sha, image_id, candidate=None):
    checks = []
    for phase in PHASES:
        path = Path(evidence_root) / phase / 'manifest.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            checks.append(dict(name=phase, status='not_run', reason='missing phase evidence'))
            continue
        except (ValueError, OSError):
            checks.append(dict(name=phase, status='failed', reason='unreadable phase evidence'))
            continue
        if not isinstance(data, dict):
            checks.append(dict(name=phase, status='failed', reason='phase evidence must be an object'))
            continue
        valid = (data.get('source_sha') == source_sha and data.get('image_id') == image_id
                 and data.get('dirty') is False and data.get('phase') == phase)
        items = data.get('checks', [])
        required = data.get('required_checks', [])
        if not isinstance(items, list) or not isinstance(required, list):
            checks.append(dict(name=phase, status='failed', reason='invalid check lists'))
            continue
        if (any(not isinstance(c, dict) or not isinstance(c.get('name'), str)
                or not isinstance(c.get('status'), str) for c in items)
                or any(not isinstance(name, str) for name in required)):
            checks.append(dict(name=phase, status='failed', reason='invalid check entry types'))
            continue
        statuses = {c['name']: c['status'] for c in items}
        status = data.get('status')
        if (not valid or status not in EXIT or not required or not items
                or any(k not in statuses for k in required)
                or any(s not in EXIT for s in statuses.values())
                or (status == 'passed' and not set(REQUIRED[phase]) <= statuses.keys())
                or len(statuses) != len(items)
                or overall(list(statuses.values())) != status
                or data.get('exit_code') != EXIT.get(status)):
            status = 'failed'
        checks.append(dict(name=phase, status=status, reason='phase evidence validated' if valid else 'identity/clean-source mismatch'))
    if candidate is not None:
        valid = (isinstance(candidate, dict) and candidate.get('source_sha') == source_sha and candidate.get('image_id') == image_id
                 and candidate.get('dirty') is False
                 and isinstance(candidate.get('archive_sha256'), str)
                 and bool(re.fullmatch(r'[a-fA-F0-9]{64}', candidate['archive_sha256'])))
        checks.append(dict(name='candidate_identity', status='passed' if valid else 'failed',
                           reason='candidate archive identity checked'))
    return overall([c['status'] for c in checks]), checks


class VerificationError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.detail = ''


class Runner:
    def __init__(self, output):
        self.output = output
        self.env = os.environ.copy()
        self.secrets = [v for k, v in self.env.items() if any(s in k.upper() for s in ('KEY', 'SECRET', 'TOKEN', 'PASSWORD'))]
        self.checks = []
        self.log = output / 'verification.log'
        self.log.touch()

    def note(self, value):
        with self.log.open('a', encoding='utf-8') as stream:
            stream.write(sanitize(value, self.secrets) + '\n')

    def command(self, args, *, timeout=120, env=None, expect=0, log=True):
        try:
            p = subprocess.run(args, cwd=ROOT, env=env or self.env, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise VerificationError('blocked', f'{args[0]} unavailable or timed out') from exc
        if log:
            self.note(p.stdout)
            self.note(p.stderr)
        if p.returncode != expect:
            error = VerificationError('failed', f'{args[0]} exited {p.returncode}; see sanitized log')
            error.detail = sanitize(p.stderr + p.stdout, self.secrets)
            raise error
        return p.stdout.strip()

    def docker(self, *args, **kwargs):
        return self.command(['docker', *args], **kwargs)

    def check(self, name, operation):
        try:
            operation()
            self.checks.append(dict(name=name, status='passed', reason='verified'))
        except VerificationError as exc:
            self.checks.append(dict(name=name, status=exc.status, reason=sanitize(exc, self.secrets)))
        except (AssertionError, ValueError, KeyError, OSError, URLError) as exc:
            self.note(f'{name}: {type(exc).__name__}: {exc}')
            self.checks.append(dict(name=name, status='failed', reason=f'{name}: {type(exc).__name__}; see sanitized log'))

    def transient(self, flags, image, command, *, env=None, timeout=120):
        name = 'sa-verify-task-' + secrets.token_hex(10)
        try:
            return self.docker('run', '--rm', '--name', name, *flags, image, *command,
                               env=env, timeout=timeout)
        except BaseException:
            # A timed-out Docker client can leave its container running.
            # This UUID name belongs exclusively to this invocation.
            try:
                self.docker('rm', '-f', name, timeout=30)
            except VerificationError as exc:
                self.note('transient cleanup: ' + str(exc))
            raise

    def python(self, image, code, *, network='none', env=None):
        flags = []
        for key in (env or {}):
            flags.extend(['--env', key])
        process_env = self.env | (env or {})
        return self.transient(['--network', network, *flags, '--entrypoint', 'python'],
                              image, ['-c', code], env=process_env)


def structure(runner, image):
    code = """
import os
from pathlib import Path
import subprocess
assert os.getuid() != 0, 'runtime must not run as root'
assert os.getcwd() == '/app'
for name in ('alembic.ini','alembic/env.py','alembic/script.py.mako','web/dist/index.html'):
    assert Path(name).is_file(), name
assert list(Path('alembic/versions').glob('*.py'))
for name in ('tests','.git','artifacts/docker','superpowers'):
    assert not Path(name).exists(), name
import psycopg
import app.main
p = subprocess.run(['alembic','heads'], capture_output=True, text=True, check=True)
assert len([line for line in p.stdout.splitlines() if '(head)' in line]) == 1, p.stdout
print('resources/imports/nonroot/unique-head verified')
"""
    runner.check('runtime_resources', lambda: runner.python(image, code))


class Sandbox:
    """Track only this invocation's resource names; no shared volumes or down -v."""
    def __init__(self, runner, image):
        self.r = runner
        self.image = image
        self.prefix = 'sa-verify-' + secrets.token_hex(6)
        self.network = self.prefix + '-net'
        self.pg = self.prefix + '-pg'
        self.app = self.prefix + '-app'
        self.containers = []
        self.network_created = False
        self.password = secrets.token_urlsafe(24)
        self.jwt = secrets.token_urlsafe(48)
        self.r.secrets.extend([self.password, self.jwt])
        self.env = {'POSTGRES_PASSWORD': self.password, 'POSTGRES_USER': 'verify',
                    'POSTGRES_DB': 'verify', 'JWT_SECRET_KEY': self.jwt}

    def __enter__(self):
        try:
            self.r.docker('network', 'create', self.network)
            self.network_created = True
            self.containers.append(self.pg)
            self.r.docker('run', '-d', '--name', self.pg, '--network', self.network,
                          '--env', 'POSTGRES_PASSWORD', '--env', 'POSTGRES_USER',
                          '--env', 'POSTGRES_DB', '--tmpfs', '/var/lib/postgresql/data',
                          'pgvector/pgvector:pg16', env=self.r.env | self.env, timeout=300)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                try:
                    ready = self.r.docker(
                        'exec', '--env', 'PGPASSWORD', self.pg,
                        'psql', '-h', '127.0.0.1', '-U', 'verify', '-d', 'verify',
                        '-tAc', 'SELECT 1',
                        env=self.r.env | {'PGPASSWORD': self.password}, timeout=10,
                    )
                    if ready == '1':
                        return self
                except VerificationError as exc:
                    if exc.status == 'blocked':
                        raise
            raise VerificationError('blocked', 'isolated PostgreSQL readiness deadline exceeded')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for name in reversed(self.containers):
            try:
                self.r.docker('rm', '-f', name, timeout=30)
            except VerificationError as exc:
                self.r.checks.append(dict(name='cleanup_' + name, status=exc.status, reason='owned container cleanup failed'))
        if self.network_created:
            try:
                self.r.docker('network', 'rm', self.network, timeout=30)
            except VerificationError as exc:
                self.r.checks.append(dict(name='cleanup_network', status=exc.status, reason='owned network cleanup failed'))

    def database(self, name):
        self.r.docker('exec', self.pg, 'createdb', '-U', 'verify', name)
        return f'postgresql+asyncpg://verify:{self.password}@{self.pg}:5432/{name}'

    def migrate(self, url, revision='head', expected_failure=None):
        try:
            self.r.transient(['--network', self.network, '--env', 'DATABASE_URL',
                              '--entrypoint', 'alembic'], self.image, ['upgrade', revision],
                             env=self.r.env | {'DATABASE_URL': url}, timeout=180)
        except VerificationError as exc:
            if expected_failure and exc.status == 'failed' and re.search(expected_failure, exc.detail, re.IGNORECASE):
                return
            raise
        if expected_failure:
            raise VerificationError('failed', 'invalid historical sample unexpectedly upgraded')

    def sql(self, url, code):
        prelude = "from sqlalchemy import create_engine,text,inspect\nfrom app.core.database_url import build_sync_database_url\nimport os,json\ne=create_engine(build_sync_database_url(os.environ['DATABASE_URL']))\n"
        return self.r.python(self.image, prelude + code, network=self.network, env={'DATABASE_URL': url})


SEED = """
with e.begin() as c:
 c.execute(text("INSERT INTO users(id,username,password_hash) VALUES (1,'verify_user','not-a-real-password')"))
 c.execute(text("INSERT INTO sessions(id,user_id,state_json,title) VALUES ('verify-session',1,'{}','preserve')"))
 c.execute(text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('verify-session','user','preserve message',0)"))
 c.execute(text("INSERT INTO mastery_nodes(user_id,topic_id,topic_name,mastery,last_practiced_at,practice_count,confusion_with,rationale) VALUES ('1','verify-topic','topic',0.5,0,1,'[]','preserve rationale')"))
 c.execute(text("INSERT INTO mastery_edges(user_id,from_topic,to_topic,type,weight,confidence,source) VALUES ('1','a','b','related',0.5,0.8,'verify')"))
"""
SNAPSHOT = """
with e.connect() as c:
 result={}
 for table in ('users','sessions','messages','mastery_nodes','mastery_edges'):
  rows=[dict(row) for row in c.execute(text('SELECT * FROM '+table)).mappings()]
  for row in rows:
   row.pop('password_hash',None)
   if 'user_id' in row: row['user_id']=str(row['user_id'])
  result[table]=rows
 print(json.dumps(result,sort_keys=True,default=str))
"""
SCHEMA = """
i=inspect(e)
assert set(('users','sessions','messages','mastery_nodes','mastery_edges','vector_chunks')) <= set(i.get_table_names())
for table in ('mastery_nodes','mastery_edges'):
 col=next(c for c in i.get_columns(table) if c['name']=='user_id')
 assert 'INT' in str(col['type']).upper()
 assert any(f['referred_table']=='users' and f['constrained_columns']==['user_id'] for f in i.get_foreign_keys(table))
assert 'chunk_id' in {c['name'] for c in i.get_columns('vector_chunks')}
with e.connect() as c:
 from alembic.config import Config
 from alembic.script import ScriptDirectory
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar() == ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
print('schema/revision/constraints verified')
"""


def migration(runner, image):
    with Sandbox(runner, image) as box:
        def empty():
            url = box.database('empty')
            box.migrate(url)
            box.sql(url, SCHEMA)
            box.sql(url, SEED)
            before = box.sql(url, SNAPSHOT)
            box.migrate(url)
            assert before == box.sql(url, SNAPSHOT), 'repeat upgrade changed data'
        runner.check('pg_empty_and_repeat', empty)

        def historical():
            url = box.database('historical')
            box.migrate(url, 'd50dd837b8e6')
            box.sql(url, SEED)
            before = box.sql(url, SNAPSHOT)
            box.migrate(url)
            box.sql(url, SCHEMA)
            assert before == box.sql(url, SNAPSHOT), 'historical upgrade changed data'
        runner.check('pg_historical_preservation', historical)

        for case, mutation in (
            ('missing_mastery', 'DROP TABLE mastery_edges; DROP TABLE mastery_nodes'),
            ('nonnumeric_user', "UPDATE mastery_nodes SET user_id='invalid'"),
            ('orphan_user', "UPDATE mastery_nodes SET user_id='999'"),
        ):
            def invalid(case=case, mutation=mutation):
                url = box.database(case)
                box.migrate(url, 'd50dd837b8e6')
                box.sql(url, SEED)
                box.sql(url, 'with e.begin() as c:\n' + '\n'.join(' c.execute(text(' + repr(sql) + '))' for sql in mutation.split(';') if sql.strip()))
                patterns = {'missing_mastery': r'UndefinedTable|does not exist',
                            'nonnumeric_user': r'non.numeric|非数字',
                            'orphan_user': r'ForeignKeyViolation|foreign key constraint'}
                box.migrate(url, expected_failure=patterns[case])
            runner.check('pg_reject_' + case, invalid)

    sqlite = """
import os,subprocess,tempfile,sys
from pathlib import Path
from sqlalchemy import create_engine,text
import json
with tempfile.TemporaryDirectory() as directory:
 env=dict(os.environ,DATABASE_URL='sqlite+aiosqlite:///'+str(Path(directory)/'verify.db'))
 before=None
 for revision in ('d50dd837b8e6','head','head'):
  p=subprocess.run([sys.executable,'-m','alembic','upgrade',revision],env=env,capture_output=True,text=True,timeout=90)
  print(p.stdout); print(p.stderr)
  assert p.returncode == 0, 'SQLite migration compatibility failure'
  e=create_engine(env['DATABASE_URL'].replace('sqlite+aiosqlite:', 'sqlite:'))
  if before is None:
   exec(SEED)
  from contextlib import redirect_stdout
  from io import StringIO
  capture=StringIO()
  with redirect_stdout(capture): exec(SNAPSHOT)
  current=capture.getvalue()
  assert before is None or before==current, 'SQLite data changed during upgrade'
  before=current
  e.dispose()
print('SQLite temporary database upgrade verified')
"""
    sqlite = 'SEED=' + repr(SEED) + '\nSNAPSHOT=' + repr(SNAPSHOT) + '\n' + sqlite
    runner.check('sqlite_upgrade', lambda: runner.python(image, sqlite))


def http(base, path, *, payload=None, token=None, expected=200):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers=headers)
    try:
        response = urlopen(request, timeout=180)
    except HTTPError as exc:
        if exc.code == expected:
            return None
        raise VerificationError('failed', f'HTTP {path} returned {exc.code}, expected {expected}') from None
    with response:
        if response.status != expected:
            raise VerificationError('failed', f'HTTP status mismatch for {path}')
        body = response.read()
        return json.loads(body) if response.headers.get_content_type() == 'application/json' else body.decode()


def wait_http(base):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            http(base, '/health')
            return
        except (URLError, TimeoutError, VerificationError):
            continue
    raise VerificationError('blocked', 'isolated application readiness deadline exceeded')


def api(runner, image, teaching=False):
    if teaching and not teaching_ready(runner.env):
        raise VerificationError('blocked', 'explicit model test opt-in and process model/embedding/pgvector configuration required')
    with Sandbox(runner, image) as box:
        url = box.database('api')
        box.migrate(url)
        env = {'DATABASE_URL': url, 'JWT_SECRET_KEY': box.jwt, 'RAG_BACKEND': 'pgvector'}
        if teaching:
            env.update({key: runner.env[key] for key in ('OPENAI_API_KEY','OPENAI_MODEL','EMBEDDING_MODEL','EMBEDDING_DIM')})
            if runner.env.get('OPENAI_BASE_URL'):
                env['OPENAI_BASE_URL'] = runner.env['OPENAI_BASE_URL']
        flags = [arg for key in env for arg in ('--env', key)]
        box.containers.append(box.app)
        runner.docker('run', '-d', '--name', box.app, '--network', box.network,
                      '-p', '127.0.0.1::8000', *flags, image, env=runner.env | env)
        # Query Settings inside the live container; only booleans leave it.
        effective = runner.docker('exec', box.app, 'python', '-c',
            "from app.core.config import settings; import json; v=settings.jwt_secret_key; print(json.dumps(bool(v.strip()) and v.strip()!='dev-secret-change-me-in-production'))")
        if effective != 'true':
            raise VerificationError('failed', 'effective JWT preflight rejected')
        runner.checks.append(dict(name='effective_jwt_valid', status='passed', reason='true'))
        port = runner.docker('port', box.app, '8000/tcp').splitlines()[0].rsplit(':', 1)[1]
        base = 'http://127.0.0.1:' + port
        wait_http(base)
        assert '<html' in http(base, '/').lower(), 'frontend entry missing'
        username = 'verify_' + secrets.token_hex(6)
        password = secrets.token_urlsafe(18)
        runner.secrets.append(password)
        registered = http(base, '/api/auth/register', payload=dict(username=username, password=password))
        assert registered.get('token')
        runner.secrets.append(registered['token'])
        login = http(base, '/api/auth/login', payload=dict(username=username, password=password))
        token = login['token']
        runner.secrets.append(token)
        assert token and login['user_id'] == registered['user_id']
        http(base, '/api/auth/login', payload=dict(username=username, password=password + '_wrong'), expected=401)
        runner.checks.append(dict(name='health_frontend_auth', status='passed', reason='health/frontend/register/login/wrong-password verified'))
        if not teaching:
            return
        session = 'verify-' + secrets.token_hex(10)
        message = '请用简短的问题帮助我学习牛顿第一定律。'
        result = http(base, '/api/chat', payload=dict(message=message, session_id=session), token=token)
        assert result['persisted'] is True and result['session_id'] == session and result['reply'].strip()
        def saved():
            data = http(base, '/api/sessions/' + session, token=token)
            assert data['session_id'] == session and data['user_id'] == registered['user_id']
            messages = http(base, '/api/sessions/' + session + '/messages', token=token)
            assert any(m['role']=='user' and m['content']==message for m in messages)
            assert any(m['role']=='assistant' and m['content']==result['reply'] for m in messages)
            return messages
        before = saved()
        runner.docker('restart', box.app, timeout=60)
        wait_http(base)
        assert saved() == before, 'restart changed persisted conversation'
        other = http(base, '/api/auth/register', payload=dict(username=username + '_other', password=password))['token']
        runner.secrets.append(other)
        for path in ('/api/sessions/' + session, '/api/sessions/' + session + '/messages'):
            http(base, path, token=other, expected=403)
        http(base, '/api/chat', payload=dict(message='forbidden', session_id=session), token=other, expected=403)
        assert saved() == before, 'cross-user write changed conversation'
        runner.checks.append(dict(name='real_teaching_restart_ownership', status='passed', reason='real reply, persisted messages, restart and cross-user denial verified'))


def source_identity(runner):
    sha = runner.command(['git', 'rev-parse', 'HEAD'])
    status = runner.command(['git', 'status', '--porcelain', '--untracked-files=normal'])
    diff = runner.command(['git', 'diff', 'HEAD', '--binary'], log=False)
    return sha, bool(status), hashlib.sha256((status + '\n' + diff).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--phase', choices=(*PHASES, 'all'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path)
    parser.add_argument('--candidate-manifest', type=Path)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    runner = Runner(args.output)
    manifest = dict(source_sha=None, dirty=True, source_diff_hash=None, image_id=None,
                    registry_digest=None, phase=args.phase, required_checks=[], checks=[],
                    timestamp=datetime.now(UTC).isoformat(), log_path='verification.log')
    try:
        sha, dirty, diff_hash = source_identity(runner)
        manifest.update(source_sha=sha, dirty=dirty, source_diff_hash=diff_hash)
        try:
            runner.docker('version', '--format', '{{.Server.Version}}', timeout=30)
        except VerificationError as exc:
            raise VerificationError('blocked', 'Docker engine unavailable; see sanitized log') from exc
        image_id = runner.docker('image', 'inspect', '--format', '{{.Id}}', args.image, timeout=30)
        if not image_id.startswith('sha256:'):
            raise VerificationError('failed', 'Docker image identity missing')
        manifest['image_id'] = image_id
        # Always execute by immutable ID after resolving the supplied tag.
        if args.phase == 'all':
            if not args.evidence_root or not args.candidate_manifest:
                raise VerificationError('not_run', 'all requires evidence-root and candidate-manifest')
            candidate = json.loads(args.candidate_manifest.read_text(encoding='utf-8'))
            if not isinstance(candidate, dict):
                raise ValueError('candidate manifest must be an object')
            _, runner.checks = aggregate(args.evidence_root, sha, image_id, candidate)
            manifest['archive_sha256'] = candidate.get('archive_sha256')
            if dirty:
                runner.checks.append(dict(name='clean_source', status='failed', reason='working tree is dirty'))
        elif args.phase == 'structure':
            structure(runner, image_id)
        elif args.phase == 'migration':
            migration(runner, image_id)
        else:
            api(runner, image_id, teaching=args.phase == 'api-teaching')
    except VerificationError as exc:
        runner.checks.append(dict(name=args.phase, status=exc.status, reason=sanitize(exc, runner.secrets)))
    except (OSError, ValueError, AssertionError, KeyError, URLError) as exc:
        runner.note(f'{type(exc).__name__}: {exc}')
        runner.checks.append(dict(name=args.phase, status='failed', reason=f'{type(exc).__name__}; see sanitized log'))
    if args.phase in REQUIRED:
        observed = {c['name'] for c in runner.checks}
        for name in REQUIRED[args.phase]:
            if name not in observed:
                runner.checks.append(dict(name=name, status='not_run', reason='required check did not execute'))
    manifest['checks'] = runner.checks
    manifest['required_checks'] = [c['name'] for c in runner.checks]
    manifest['status'] = overall([c['status'] for c in runner.checks]) if runner.checks else 'not_run'
    manifest['exit_code'] = EXIT[manifest['status']]
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(phase=args.phase, status=manifest['status'], exit_code=manifest['exit_code'])))
    return manifest['exit_code']


if __name__ == '__main__':
    sys.exit(main())
