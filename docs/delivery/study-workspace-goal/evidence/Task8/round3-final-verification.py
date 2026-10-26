"""Record final scope/whitespace/syntax/database checks; never edits product or tests."""
from pathlib import Path
from datetime import datetime, timezone
import difflib
import hashlib
import json
import py_compile
import subprocess
import psycopg

root=Path.cwd()
evidence=root/'docs/delivery/study-workspace-goal/evidence/Task8'
allowed={'app/api/_disconnect.py','tests/api/test_conversation_transactions.py'}
prior=json.loads((evidence/'round2-code-freeze-manifest.json').read_text(encoding='utf-8-sig'))
assert len(prior['files'])==26
base=root/'.superpowers/sdd/2026-10-23-study-workspace-core/task8-round3-base'
if not (base/'app/api/_disconnect.py').is_file():
    inventory=subprocess.check_output(['rg','--files','--hidden','--no-ignore','.superpowers','-g','_disconnect.py'],text=True)
    matches=[Path(line) for line in inventory.splitlines() if '/task8-round3-base/app/api/_disconnect.py' in line.replace('\\','/')]
    assert len(matches)==1,matches
    base=root/matches[0].parents[2]
print('ROUND3_SNAPSHOT',base)
entries=[]
changed=[]
for record in prior['files']:
    name=record['path']
    digest=hashlib.sha256((root/name).read_bytes()).hexdigest()
    if digest!=record['sha256']:
        changed.append(name)
        assert name in allowed,('out of scope source change',name)
    if name in allowed:
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==record['sha256'],('snapshot mismatch',name)
        py_compile.compile(str(root/name),doraise=True)
        check=subprocess.run(['git','diff','--no-index','--check','--',str(base/name),str(root/name)],capture_output=True,text=True)
        print('ROUND3_NO_INDEX_CHECK',name,'exit',check.returncode,'stdout',check.stdout,'stderr',check.stderr)
        assert check.returncode in {0,1} and not check.stdout.strip()
        assert not check.stderr.strip() or all(line.startswith('warning:') for line in check.stderr.splitlines() if line.strip())
        delta=difflib.unified_diff((base/name).read_text(encoding='utf-8-sig').splitlines(),(root/name).read_text(encoding='utf-8-sig').splitlines())
        for line in delta:
            if line.startswith('+') and not line.startswith('+++'):
                assert line[1:]==line[1:].rstrip(' \t'),('introduced trailing whitespace',name,line)
    entries.append({**record,'sha256':digest})
assert set(changed)==allowed,changed
print('ROUND3_COMPILE_OK',len(allowed),'ONLY_ALLOWED_CHANGED',changed,'UNCHANGED_OTHER_FILES',26-len(changed))
with psycopg.connect(host='127.0.0.1',port=55440,user='goal_test',password='goal_test_local_only',dbname='goal_workspace') as db:
    rows=db.execute("SELECT datname FROM pg_database WHERE datname LIKE 'workspace_task8_%' ORDER BY datname").fetchall()
print('ROUND3_REMAINING_TASK8_DATABASES',rows)
assert rows==[]
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()
assert head=='75be6015c331185dea34dc8910e5646c6663f29e' and branch=='codex/frontend-ui-optimization'
brief_sha=hashlib.sha256((root/'.superpowers/sdd/2026-10-23-study-workspace-core/task8-round3-brief.md').read_bytes()).hexdigest()
assert brief_sha=='437df2114f1ed3f8791f6cd7ae1e19e16b0f1af27ced3e6f4b3806213a7dafcc'
manifest=dict(frozen_at=datetime.now(timezone.utc).isoformat(),head=head,branch=branch,brief_sha256=brief_sha,round3_allowed_files=sorted(allowed),round3_changed_existing=changed,files=entries)
(evidence/'round3-code-freeze-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('ROUND3_ALL_SOURCE_AND_TESTS_FROZEN',manifest['frozen_at'],'files',len(entries))
print('ROUND3_UNTRACKED_PRODUCT_TESTS',[record['path'] for record in entries if not record['git_tracked']])
