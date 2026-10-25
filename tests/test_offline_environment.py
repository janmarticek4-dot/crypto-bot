"""Offline harness must be deterministic under the CI shadow job environment."""
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

class OfflineHarnessEnvironment(unittest.TestCase):
    def test_shadow_job_environment_is_scoped_to_test_process_with_delivery_disabled(self):
        script=Path(__file__).resolve().parents[1]/'scripts/test_offline.py'
        for inherited in ('shadow','synthetic','live'):
            with patch.dict(os.environ,{'BOT_DATA_MODE':inherited,'TELEGRAM_TOKEN':'dummy',
                                        'TELEGRAM_CHAT_ID':'dummy','GROQ_API_KEY':'dummy'}):
                runpy.run_path(str(script),run_name='offline_harness_configuration_only')
                self.assertEqual(os.environ['BOT_DATA_MODE'],'live')
                self.assertEqual(os.environ['BOT_DISABLE_TELEGRAM'],'1')
                for name in ('TELEGRAM_TOKEN','TELEGRAM_CHAT_ID','GROQ_API_KEY'):
                    self.assertEqual(os.environ[name],'')
