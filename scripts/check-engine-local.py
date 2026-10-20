"""Run a local engine smoke test with an ephemeral PostgreSQL database.

Requires Docker, a built engine image and a populated Hugging Face cache volume.
No remote endpoints, existing databases or production credentials are used.
"""

import argparse
import sys
import base64
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image', required=True, help='Existing local engine image')
parser.add_argument('--cache-volume', required=True, help='Existing Hugging Face model cache volume')
parser.add_argument('--port', type=int, default=15679)
parser.add_argument('--benchmark-output', type=Path, help='Write real engine span metrics to this JSON file')
parser.add_argument('--min-f1', type=float, default=0.90, help='Minimum exact-span F1 when running the benchmark')
parser.add_argument('--cloud-root', type=Path, help='Optional local Cloud repository for PHP integration tests')
args = parser.parse_args()
if not 0 <= args.min_f1 <= 1:
    parser.error('--min-f1 must be between 0 and 1')
ROOT = Path(__file__).resolve().parents[1] / 'api'
PREFIX = 'pseudora-check-' + secrets.token_hex(3)
PG, API = PREFIX + '-db', PREFIX + '-api'
ENV = os.environ.copy()
ENV.update({
    'POSTGRES_PASSWORD': secrets.token_hex(20),
    'ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'ADMIN_INITIAL_KEY': secrets.token_hex(24),
    'PII_INTERNAL_API_KEY': secrets.token_hex(24),
})
ENV['DATABASE_URL'] = f"postgresql+asyncpg://check:{ENV['POSTGRES_PASSWORD']}@{PG}:5432/check"

def docker(*args, check=True):
    return subprocess.run(['docker', *args], env=ENV, text=True, capture_output=True, check=check)

def request(path, body=None, tenant='check-a', authenticated=True):
    headers = {'Content-Type': 'application/json'}
    if authenticated:
        headers.update({'X-Api-Key': ENV['ADMIN_INITIAL_KEY'], 'X-Internal-Api-Key': ENV['PII_INTERNAL_API_KEY'], 'X-Pii-Tenant-Id': tenant})
    req = urllib.request.Request(f'http://127.0.0.1:{args.port}'+path, headers=headers, data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)

docker('image', 'inspect', args.image)
docker('volume', 'inspect', args.cache_volume)

try:
    docker('network', 'create', PREFIX)
    docker('run', '-d', '--name', PG, '--network', PREFIX, '--tmpfs', '/var/lib/postgresql/data',
           '-v', f'{ROOT.parent / "scripts"}:/checks:ro',
           '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_USER=check', '-e', 'POSTGRES_DB=check', 'pgvector/pgvector:pg17')
    for _ in range(30):
        if docker('exec', PG, 'pg_isready', '-U', 'check', check=False).returncode == 0:
            break
        time.sleep(1)
    docker('run', '-d', '--name', API, '--network', PREFIX, '-p', f'127.0.0.1:{args.port}:8000',
           '-v', f'{ROOT}:/app:ro', '-v', f'{args.cache_volume}:/root/.cache/huggingface',
           '-e', 'DATABASE_URL', '-e', 'ENCRYPTION_KEY', '-e', 'ADMIN_INITIAL_KEY', '-e', 'PII_INTERNAL_API_KEY',
           '-e', 'MULTITENANCY_ENABLED=true', '-e', 'PII_ACCEPT_TENANT_HEADER=true',
           '-e', 'HF_HUB_OFFLINE=1', '-e', 'TRANSFORMERS_OFFLINE=1',
           '-e', 'OMP_NUM_THREADS=2', '-e', 'MKL_NUM_THREADS=2', '-e', 'TORCH_NUM_THREADS=2',
           '--entrypoint', 'sh', args.image, '/app/entrypoint.sh')
    for _ in range(90):
        try:
            status, health = request('/readiness')
            if status == 200:
                print('READINESS', json.dumps(health), flush=True)
                break
        except Exception:
            pass
        if docker('inspect', '-f', '{{.State.Running}}', API).stdout.strip() != 'true':
            raise RuntimeError('API exited before readiness')
        time.sleep(2)
    else:
        raise RuntimeError('API readiness timeout')
    logs = docker('logs', API)
    startup_logs = logs.stdout + logs.stderr
    for marker in ('Presidio loaded for languages', 'PrivacyFilter model loaded', 'Ai4Privacy model loaded'):
        if marker not in startup_logs:
            raise RuntimeError('Required detector did not load: ' + marker)
    for line in (logs.stdout + logs.stderr).splitlines():
        if any(term in line for term in ('model loaded', 'model unavailable', 'Skipping', 'ONNX', 'inference error')):
            print('DETECTOR_LOG', line, flush=True)
    status, _ = request('/v1/anonymize', {'text': 'mario@example.com', 'context_id': 'unauthorized'}, authenticated=False)
    assert status in (401, 403), status
    print('UNAUTHENTICATED_REJECTED', status, flush=True)
    original = 'Mario Rossi email mario@example.com'
    for mode in ('tag', 'surrogate'):
        payload = {'text': original, 'context_id': 'check-'+mode, 'context_type': 'generic', 'language': 'it', 'mode': mode}
        started = time.monotonic()
        status, result = request('/v1/anonymize', payload)
        print('ANONYMIZE', mode, status, round(time.monotonic()-started, 2), json.dumps(result), flush=True)
        assert status == 200 and result['safe'] and 'mario@example.com' not in result['anonymized_text']
        restore = {'text': result['anonymized_text'], 'context_id': 'check-'+mode, 'context_type': 'generic'}
        status, restored = request('/v1/deanonymize', restore)
        print('RESTORE', mode, status, json.dumps(restored), flush=True)
        assert status == 200 and original in restored.values(), restored
        status, other = request('/v1/deanonymize', restore, tenant='check-b')
        assert original not in json.dumps(other), other
        print('CROSS_TENANT_NO_ORIGINAL', status, flush=True)
        assert status == 200 and other['restored_text'] == result['anonymized_text']
        status, other = request('/v1/deanonymize', {**restore, 'project_id': 'other-project'})
        assert status == 200 and other['restored_text'] == result['anonymized_text'], other
        print('CROSS_PROJECT_NO_ORIGINAL', status, flush=True)
        status, repeated = request('/v1/anonymize', payload)
        assert status == 200 and repeated['anonymized_text'] == result['anonymized_text'], repeated
        print('STABLE_REPEATED_MAPPING', mode, flush=True)
    long_text = ('This is a synthetic support request describing an application issue. ' * 10) + original
    status, result = request('/v1/anonymize', {'text': long_text, 'context_id': 'long-check', 'language': 'it', 'mode': 'tag'})
    assert status == 200 and result['safe'] and 'mario@example.com' not in result['anonymized_text'], result
    print('LONG_TEXT_PASSED', len(long_text), flush=True)
    status, result = request('/v1/anonymize/batch', {
        'context_type': 'generic', 'language': 'it', 'dry_run': False,
        'items': [{'id': 'batch-'+mode, 'text': original, 'mode': mode}
                  for mode in ('tag', 'surrogate')],
    })
    assert status == 200 and len(result['items']) == 2, result
    for item in result['items']:
        assert item['status'] == 'processed' and 'mario@example.com' not in item['output'], item
    print('BATCH_MIXED_MODES_PASSED', flush=True)
    if args.benchmark_output:
        sys.path.insert(0, str(ROOT.parent / 'benchmark'))
        from evaluate import evaluate
        rows = json.loads((ROOT.parent / 'benchmark/datasets/engine_spans_v1.json').read_text())
        metrics = evaluate(rows, request)
        metrics['quality_gate'] = {'min_f1': args.min_f1, 'passed': metrics['f1'] >= args.min_f1}
        args.benchmark_output.write_text(json.dumps(metrics, indent=2) + '\n')
        print('ENGINE_BENCHMARK', json.dumps({k: metrics[k] for k in ('precision', 'recall', 'f1', 'dataset_size')}), flush=True)
        if not metrics['quality_gate']['passed']:
            raise RuntimeError('Real-engine benchmark quality gate failed; inspect the report')
    if args.cloud_root:
        cloud_env = os.environ.copy()
        cloud_env.update({
            'PII_LOCAL_ENGINE_TEST': '1', 'PII_TEST_ENGINE_URL': f'http://127.0.0.1:{args.port}',
            'PII_TEST_ENGINE_KEY': ENV['ADMIN_INITIAL_KEY'],
            'PII_TEST_INTERNAL_KEY': ENV['PII_INTERNAL_API_KEY'],
        })
        subprocess.run(['php', 'vendor/bin/phpunit', 'tests/Integration/LiveEngineTest.php'],
                       cwd=args.cloud_root, env=cloud_env, check=True)
        print('CLOUD_REAL_ENGINE_INTEGRATION_PASSED', flush=True)
    docker('exec', PG, 'bash', '-euc', '''
set -o pipefail
pg_dump -U check -Fc check | gzip > /tmp/check.dump.gz
createdb -U check check_restore
export RESTORE_DRILL=1 PII_ENVIRONMENT=testing APP_ENV=testing
export BACKUP_FILE=/tmp/check.dump.gz PII_DB_NAME=check_restore PII_DB_USER=check
export PII_DB_PASSWORD="$POSTGRES_PASSWORD"
bash /checks/restore-drill.sh
''')
    source_count = docker('exec', PG, 'psql', '-U', 'check', '-d', 'check', '-Atc', 'SELECT count(*) FROM pii_mappings').stdout.strip()
    restored_count = docker('exec', PG, 'psql', '-U', 'check', '-d', 'check_restore', '-Atc', 'SELECT count(*) FROM pii_mappings').stdout.strip()
    assert int(source_count) > 0 and source_count == restored_count
    print('RESTORE_DRILL_MAPPING_COUNT_VERIFIED', restored_count, flush=True)
    print('LIVE_CHECK_PASSED', flush=True)
except Exception:
    logs = docker('logs', '--tail', '65', API, check=False)
    print(logs.stdout + logs.stderr, flush=True)
    raise
finally:
    docker('rm', '-f', API, PG, check=False)
    docker('network', 'rm', PREFIX, check=False)
    print('TEMPORARY_CONTAINERS_REMOVED', flush=True)
