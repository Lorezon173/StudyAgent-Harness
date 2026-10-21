"""Real Docker migration checks: opt in with DOCKER_VERIFY_IMAGE, never fake a pass."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_candidate_migration_upgrade_and_data_preservation(tmp_path):
    image = os.environ.get('DOCKER_VERIFY_IMAGE')
    if not image:
        pytest.skip('DOCKER_VERIFY_IMAGE is required for real candidate-image migrations')
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / 'migration'
    process = subprocess.run(
        [sys.executable, str(root / 'scripts/verify_docker_image.py'),
         '--image', image, '--phase', 'migration', '--output', str(output)],
        cwd=root, capture_output=True, text=True, timeout=1800,
    )
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert process.returncode == 0, manifest
    assert manifest['status'] == 'passed'
    checks = {c['name']: c['status'] for c in manifest['checks']}
    for name in ('pg_empty_and_repeat', 'pg_historical_preservation',
                 'pg_reject_missing_mastery', 'pg_reject_nonnumeric_user',
                 'pg_reject_orphan_user', 'sqlite_upgrade'):
        assert checks[name] == 'passed'
