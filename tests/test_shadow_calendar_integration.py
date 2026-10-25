"""Synthetic regression fixtures only; never contact network or deliver Telegram."""
from datetime import datetime,timezone
from pathlib import Path
import unittest
from v11.fundamentals import parse_calendar, SOURCES
from v11.briefing import event_lines

class ShadowCalendarIntegration(unittest.TestCase):
    def test_bls_alias_is_displayed_in_real_report_builder_with_dst(self):
        now=datetime(2026,10,25,20,tzinfo=timezone.utc)
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=US-Eastern:20261106T083000\nSUMMARY:Employment Situation\nEND:VEVENT\nEND:VCALENDAR'
        source=next(s for s in SOURCES if s['id']=='bls_calendar')
        events=parse_calendar(raw,source,now)
        text='\n'.join(event_lines(dict(events=events,sources=[]),now.timestamp()))
        self.assertIn('06.11.2026 14:30 Bratislava',text)
        self.assertIn('Employment Situation',text)
        self.assertIn('Očakávanie trhu N/A',text)
        self.assertIn('Overený cenový dopad: N/A',text)

    def test_registered_entrypoint_calls_same_commit_shadow_without_secrets(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows/run.yml').read_text()
        job=text.split('\n  shadow:\n',1)[1]
        self.assertIn('uses: ./.github/workflows/v11-1-shadow-test.yml',job)
        self.assertIn('use_groq: false',job)
        self.assertNotIn('secrets:',text)
        self.assertIn("inputs.task == 'shadow'",job)
        reused=(root/'.github/workflows/v11-1-shadow-test.yml').read_text()
        for constraint in ('run.head_sha !== context.sha', 'run.conclusion', 'dedicated',
                           'No successful morning checkpoint', 'actions/download-artifact@v4'):
            self.assertIn(constraint,reused)
        self.assertNotIn('  schedule:',reused)
