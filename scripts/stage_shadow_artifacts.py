"""Upload only reviewed shadow files, never the raw working directory.

No private state imports, no network, no secret creation. A failed validation
stages only a fixed status report. This is defense in depth, not a full DLP tool.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.state_policy import PublicDataError, PRIVATE_FIELDS, KEY_PATTERNS, require_public_data

ROOT=Path(__file__).resolve().parents[1]
ALLOWED=frozenset({
 'risk_diagnostics.json','legacy_rule_audit.json','analysis_validation.json','REPORT.md','source_diagnostics.json','ai_diagnostics.json','fundamental_evidence.json','README.txt','calendar.txt','calendar_coverage.json','entry_diagnostics.json',
 'evening.txt','evening_injected_outage.txt','evening_parts.json','fundamentals.json',
 'market_snapshot.json','morning.txt','morning_injected_outage.txt','morning_parts.json',
 'offline-tests.log','outage_checks.json','phase_validation.json','risk_evidence.json',
 'source_availability.json','summary.json','comparison.json','comparison.txt',
 'morning_reference.txt','checkpoints/morning.json',
})
SECRET_ENV=('GROQ_API_KEY','TELEGRAM_TOKEN','TELEGRAM_CHAT_ID','STATE_REPO_TOKEN',
            'STATE_ENCRYPTION_KEY','GH_TOKEN','GITHUB_TOKEN','COINGECKO_API_KEY')


def stage(source,destination):
    source=Path(source).absolute();destination=Path(destination).absolute()
    if not source.is_relative_to(ROOT/'shadow-output') or not destination.is_relative_to(ROOT/'shadow-public-artifacts'):
        raise PublicDataError('Artifact paths outside isolated directories refused')
    if '..' in source.parts or '..' in destination.parts:
        raise PublicDataError('Artifact traversal refused')
    if any(p.is_symlink() for p in (source,destination,*source.parents,*destination.parents)):
        raise PublicDataError('Artifact symlink refused')
    if destination.exists():shutil.rmtree(destination)
    destination.mkdir(parents=True,mode=0o700)
    ready=[]
    try:
        if not source.is_dir():raise PublicDataError('No shadow source directory')
        secret_values=[os.environ.get(k,'') for k in SECRET_ENV if os.environ.get(k,'')]
        for path in source.rglob('*'):
            relative=path.relative_to(source).as_posix()
            if path.is_symlink():raise PublicDataError('Artifact symlink refused')
            # Restored artifacts are input references, not new outputs.
            if relative=='reference' or relative.startswith('reference/'):continue
            if relative=='checkpoints/morning.lock':continue
            if path.is_dir():continue
            if relative not in ALLOWED:raise PublicDataError('Unexpected file refused')
            if path.stat().st_size>20_000_000:raise PublicDataError('Oversized artifact refused')
            raw=path.read_bytes();text=raw.decode('utf-8')
            if any(secret in text for secret in secret_values):raise PublicDataError('Credential value refused')
            require_public_data(text)
            if path.suffix=='.json':require_public_data(json.loads(text))
            elif any(re.search(r'[\"\x27]'+re.escape(key)+r'[\"\x27]\s*:',text,re.I) for key in PRIVATE_FIELDS):
                raise PublicDataError('Private field in text refused')
            ready.append((relative,raw))
        # Copy only after ALL files passed; a refusal cannot leave a partial leak.
        for name,raw in ready:
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
        status=dict(status='PASSED',files=len(ready),scope='allowlist, private fields, credential patterns and known environment values; not complete semantic DLP')
        code=0
    except (PublicDataError,ValueError,OSError,UnicodeError):
        shutil.rmtree(destination);destination.mkdir(mode=0o700)
        status=dict(status='REFUSED',reason='Artifact privacy validation failed; no source content uploaded')
        code=1
    (destination/'artifact_privacy.json').write_text(json.dumps(status)+'\n')
    print('Shadow artifact privacy: '+status['status'])
    return code


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default='shadow-output');p.add_argument('--destination',default='shadow-public-artifacts')
    args=p.parse_args()
    raise SystemExit(stage(args.source,args.destination))
