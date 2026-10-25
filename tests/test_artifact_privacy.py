"""Synthetic canaries only. No real account/credential or production state read."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from scripts.stage_shadow_artifacts import stage, ROOT
from v11.state_policy import PublicDataError, require_public_data

class ArtifactPrivacy(unittest.TestCase):
    def setUp(self):
        (ROOT/'shadow-output').mkdir(exist_ok=True)
        (ROOT/'shadow-public-artifacts').mkdir(exist_ok=True)
        self.source=Path(tempfile.mkdtemp(dir=ROOT/'shadow-output'))
        self.dest=Path(tempfile.mkdtemp(dir=ROOT/'shadow-public-artifacts'))
    def tearDown(self):
        shutil.rmtree(self.source);shutil.rmtree(self.dest)
    def invoke(self):
        with contextlib.redirect_stdout(io.StringIO()):return stage(self.source,self.dest)
    def assert_refused(self):
        self.assertEqual(self.invoke(),1)
        self.assertEqual([p.name for p in self.dest.iterdir()],['artifact_privacy.json'])
        self.assertEqual(json.loads((self.dest/'artifact_privacy.json').read_text())['status'],'REFUSED')

    def test_public_market_data_and_unknown_positions_checkpoint_pass(self):
        (self.source/'market_snapshot.json').write_text(json.dumps({'coins':{'SOL':{'price':100,'volume_24h':10}},'positions':'UNKNOWN; no real portfolio loaded'}))
        (self.source/'morning.txt').write_text('SHADOW; HOLD N/A; technical entry zone $100')
        self.assertEqual(self.invoke(),0)
        self.assertTrue((self.dest/'market_snapshot.json').exists())

    def test_no_silent_redaction_of_portfolio_or_credentials_even_empty(self):
        for fixture in ({'portfolio_v11':{'cash':7}}, {'nested':{'transactions':[]}},
                        {'balances':{}},{'positions':{'SOL':{'qty':2}}}, {'password':'fixture-only'},
                        {'positions':'SOL 2 units fixture'}, {'held':True}):
            with self.assertRaises(PublicDataError):require_public_data(fixture)
        (self.source/'summary.json').write_text(json.dumps({'portfolio_v11':{'cash':7}}))
        self.assert_refused()

    def test_secret_from_environment_is_not_uploaded_or_logged(self):
        canary='TEST-ONLY-SECRET-CANARY-NOT-A-REAL-KEY'
        (self.source/'morning.txt').write_text('Unexpected fixture: '+canary)
        capture=io.StringIO()
        with patch.dict(os.environ,{'GROQ_API_KEY':canary}),contextlib.redirect_stdout(capture):
            self.assertEqual(stage(self.source,self.dest),1)
        self.assertNotIn(canary,capture.getvalue())
        self.assertNotIn(canary,(self.dest/'artifact_privacy.json').read_text())

    def test_private_json_field_in_text_and_credential_shape_rejected(self):
        for text in ('{"cash": 7}', '-----BEGIN PRIVATE KEY----- synthetic fixture'):
            (self.source/'morning.txt').write_text(text)
            self.assert_refused()

    def test_unknown_file_or_symlink_refuses_entire_upload(self):
        (self.source/'morning.txt').write_text('Safe fixture')
        (self.source/'accidental-account.json').write_text('{"fixture":true}')
        self.assert_refused()
        (self.source/'accidental-account.json').unlink()
        (self.source/'evening.txt').symlink_to(self.source/'morning.txt')
        self.assert_refused()

    def test_restored_input_reference_not_republished(self):
        reference=self.source/'reference';reference.mkdir()
        (reference/'old.json').write_text('{"cash":7}')
        (self.source/'summary.json').write_text('{"phase":"evening"}')
        self.assertEqual(self.invoke(),0)
        self.assertFalse((self.dest/'reference').exists())

    def test_previous_staging_cannot_survive_refused_new_output(self):
        (self.dest/'morning.txt').write_text('Previous public fixture')
        (self.source/'bad-file.txt').write_text('unknown')
        self.assert_refused()

    def test_paths_cannot_escape_reserved_staging(self):
        for src,dst in [(ROOT, self.dest),(self.source,ROOT),
                        (self.source,ROOT/'shadow-public-artifacts'/'..'/'public')]:
            with self.assertRaises(PublicDataError):stage(src,dst)

    def test_shadow_workflow_uploads_staged_directory_only(self):
        text=(ROOT/'.github/workflows/v11-1-shadow-test.yml').read_text()
        self.assertIn('python scripts/stage_shadow_artifacts.py',text)
        self.assertNotIn('path: shadow-output/\n',text)
        self.assertEqual(text.count('path: shadow-public-artifacts/'),2)
        self.assertLess(text.index('name: Validate and stage'),text.index('name: Publish discoverable'))
        summary=text.split('      - name: Summary',1)[1]
        self.assertNotIn('shadow-output/',summary)
        self.assertIn('shadow-public-artifacts/summary.json',summary)

    def test_real_checkpoint_structure_with_synthetic_data_survives_staging(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from tests.test_shadow_pair import sample
        from v11.shadow_pair import checkpoint,save_once,SYMBOLS
        now=datetime(2026,10,26,7,tzinfo=ZoneInfo('Europe/Bratislava'))
        saved=checkpoint(sample(now),{s:{'action':'WAIT','held':False} for s in SYMBOLS},now)
        save_once(self.source/'checkpoints'/'morning.json',saved)
        self.assertEqual(self.invoke(),0)
        self.assertTrue((self.dest/'checkpoints'/'morning.json').exists())
        self.assertFalse((self.dest/'checkpoints'/'morning.lock').exists())
