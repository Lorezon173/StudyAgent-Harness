from pathlib import Path
import hashlib,json,py_compile,subprocess
from datetime import datetime,timezone
import psycopg
root=Path.cwd()
evidence=root/'docs/delivery/study-workspace-goal/evidence/Task8'
allowed=['app/api/_disconnect.py','app/api/chat.py','app/api/sessions.py','app/orchestration/conversation_service.py','tests/api/test_conversation_transactions.py','tests/integration/test_workspace_concurrency.py','tests/unit/api/test_workspace_sessions_api.py']
for name in allowed:
    py_compile.compile(str(root/name),doraise=True)
print('ROUND2_COMPILE_OK',len(allowed))
checked=subprocess.run(['git','diff','--check','--',*allowed],capture_output=True,text=True)
print('ROUND2_DIFF_CHECK_EXIT',checked.returncode)
print(checked.stdout,checked.stderr)
assert checked.returncode==0
with psycopg.connect(host='127.0.0.1',port=55440,user='goal_test',password='goal_test_local_only',dbname='goal_workspace') as db:
    rows=db.execute("SELECT datname FROM pg_database WHERE datname LIKE 'workspace_task8_%' ORDER BY datname").fetchall()
print('ROUND2_REMAINING_TASK8_DATABASES',rows)
assert rows==[]
prior=json.loads((evidence/'code-freeze-manifest.json').read_text(encoding='utf-8-sig'))
print('ROUND2_PRIOR_MANIFEST_KEYS',list(prior))
records=[]
def find(value):
    if isinstance(value,dict):
        if 'sha256' in value and ('path' in value or 'file' in value):
            records.append(value)
        else:
            for item in value.values():find(item)
    elif isinstance(value,list):
        for item in value:find(item)
find(prior)
assert len(records)==25,len(records)
files={}
changed=[]
for record in records:
    name=record.get('path',record.get('file')).replace('\\','/')
    path=Path(name)
    if path.is_absolute():name=path.relative_to(root).as_posix()
    digest=hashlib.sha256((root/name).read_bytes()).hexdigest()
    if digest.lower()!=record['sha256'].lower():
        changed.append(name)
        assert name in allowed,('source changed outside round2 scope',name)
    files[name]=digest
files['app/api/_disconnect.py']=hashlib.sha256((root/'app/api/_disconnect.py').read_bytes()).hexdigest()
assert len(files)==26
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()
assert head=='75be6015c331185dea34dc8910e5646c6663f29e'
assert branch=='codex/frontend-ui-optimization'
entries=[]
for name,digest in sorted(files.items()):
    tracked=subprocess.run(['git','ls-files','--error-unmatch',name],capture_output=True).returncode==0
    entries.append(dict(path=name,sha256=digest,git_tracked=tracked))
manifest=dict(frozen_at=datetime.now(timezone.utc).isoformat(),head=head,branch=branch,brief_sha256=hashlib.sha256((root/'.superpowers/sdd/2026-10-23-study-workspace-core/task8-round2-brief.md').read_bytes()).hexdigest(),round2_allowed_files=allowed,round2_changed_existing=changed,files=entries)
(evidence/'round2-code-freeze-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('ROUND2_ALL_SOURCE_AND_TESTS_FROZEN',manifest['frozen_at'],'files',len(entries),'existing_changed',changed)
print('ROUND2_UNTRACKED_PRODUCT_TESTS',[record['path'] for record in entries if not record['git_tracked']])
