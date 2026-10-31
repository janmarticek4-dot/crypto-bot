import copy,json,os,tempfile,unittest
from contextlib import contextmanager,ExitStack
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch,MagicMock
from scripts import v111_trial as pilot,v111_integrated_delivery as delivery
from tests import test_integration_candidate as fixtures

ENV={'V111_INTEGRATION_ENABLED':'true','V111_MANUAL_ANALYSIS':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':'1000','PRIVATE_ADVISORY_ENABLED':'false','V111_DIAGNOSTICS_DIR':''}

class MemoryJournal:
    def __init__(self):
        self.value={'schema':1,'slots':{'2026-10-26-evening':{'status':'sent','quotes':{}},'2026-09-01-morning':{'status':'uncertain'}},'analysis_forecasts_v11':[],'macro_observation_history_v1':[{'synthetic':'unchanged'}]};self.writes=[]
    def read(self):return copy.deepcopy(self.value)
    def save(self,value):self.value=copy.deepcopy(value);self.writes.append(copy.deepcopy(value))

class ManualV111Tests(unittest.TestCase):
    @contextmanager
    def setup_run(self,now=None,private=False,directory=''):
        now=now or datetime(2026,10,27,11,tzinfo=timezone.utc);journal=MemoryJournal();snapshot=fixtures.IntegrationTests().data()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,dict(ENV,PRIVATE_ADVISORY_ENABLED='true' if private else 'false',V111_DIAGNOSTICS_DIR=directory)))
            clock=stack.enter_context(patch.object(pilot,'datetime'));clock.now.return_value=now
            stack.enter_context(patch.object(pilot,'PublicJournal',return_value=journal))
            collect=stack.enter_context(patch.object(pilot.data,'collect',side_effect=lambda *a,**k:copy.deepcopy(snapshot)))
            stack.enter_context(patch.object(pilot.fundamentals,'collect',return_value={'events':[]}))
            stack.enter_context(patch.object(pilot.macro_context,'collect',return_value={}))
            stack.enter_context(patch.object(pilot.macro_context,'economic_observations',return_value={'observations':{}}))
            stack.enter_context(patch.object(delivery,'latest_public_rule_state',return_value={}))
            stack.enter_context(patch.object(delivery.legacy,'get_fear_greed',return_value={}))
            send=stack.enter_context(patch.object(pilot,'send'))
            yield journal,collect,send
    def test_manual_anytime_uses_full_renderer_and_preserves_scheduled_state(self):
        with self.setup_run() as (j,collect,send):
            before=copy.deepcopy(j.value)
            self.assertEqual(delivery.run(),0)
            self.assertEqual(j.value['slots'],before['slots'])
            self.assertEqual(j.value['analysis_forecasts_v11'],before['analysis_forecasts_v11'])
            self.assertEqual(j.value['macro_observation_history_v1'],before['macro_observation_history_v1'])
            self.assertEqual(j.value['manual_slots']['github-run-1000']['status'],'sent')
            self.assertEqual(j.writes[0]['manual_slots']['github-run-1000']['status'],'attempting')
            text=send.call_args.args[0]
            self.assertIn('RUČNÁ ANALÝZA V11.1',text)
            for symbol in delivery.legacy.PORTFOLIO:self.assertIn(symbol,text)
            self.assertNotIn('— VEČER',text);collect.assert_called_once()
    def test_ten_explicit_runs_ten_reports_but_rerun_attempt_not_new_report(self):
        with self.setup_run() as (j,collect,send):
            for i in range(1000,1010):
                os.environ['GITHUB_RUN_ID']=str(i);delivery.run()
            self.assertEqual(send.call_count,10);self.assertEqual(collect.call_count,10)
            os.environ['GITHUB_RUN_ATTEMPT']='2';delivery.run()
            self.assertEqual(send.call_count,10);self.assertEqual(collect.call_count,10)
            self.assertEqual(len(j.value['manual_slots']),10)
    def test_all_recorded_statuses_refuse_automatic_resend(self):
        for status in ('attempting','uncertain','sent'):
            with self.subTest(status=status),self.setup_run() as (j,collect,send):
                j.value['manual_slots']={'github-run-1000':{'status':status}}
                delivery.run();send.assert_not_called();collect.assert_not_called()
    def test_send_failure_is_uncertain_and_rerun_never_retries(self):
        with self.setup_run() as (j,collect,send):
            send.side_effect=TimeoutError('synthetic timeout')
            with self.assertRaises(TimeoutError):delivery.run()
            self.assertEqual(j.value['manual_slots']['github-run-1000']['status'],'uncertain')
            delivery.run();self.assertEqual(send.call_count,1);self.assertEqual(collect.call_count,1)
    def test_cas_failure_stops_before_any_telegram(self):
        with self.setup_run() as (j,collect,send):
            with patch.object(j,'save',side_effect=RuntimeError('synthetic CAS conflict')):
                with self.assertRaises(RuntimeError):delivery.run()
            send.assert_not_called()
    def test_manual_during_morning_does_not_consume_scheduled_slot(self):
        with self.setup_run(datetime(2026,10,27,6,tzinfo=timezone.utc)) as (j,collect,send):
            delivery.run();self.assertNotIn('2026-10-27-morning',j.value['slots'])
            os.environ['V111_MANUAL_ANALYSIS']='false';os.environ['GITHUB_EVENT_NAME']='schedule'
            delivery.run();self.assertEqual(send.call_count,2)
            self.assertEqual(j.value['slots']['2026-10-27-morning']['status'],'sent')
            self.assertEqual(j.value['manual_slots']['github-run-1000']['status'],'sent')
    def test_manual_in_us_window_still_is_complete_crypto_analysis(self):
        with self.setup_run(datetime(2026,10,27,14,tzinfo=timezone.utc)) as (j,collect,send):
            with patch('us_context.report.collect',side_effect=AssertionError('manual must not delegate to US-only report')):
                delivery.run()
            collect.assert_called_once();send.assert_called_once()
            self.assertNotIn('2026-10-27-usa',j.value['slots'])
    def test_private_attachment_only_sent_not_persisted_or_exported(self):
        with tempfile.TemporaryDirectory() as directory,self.setup_run(private=True,directory=directory) as (j,collect,send):
            with patch('v11.advisory_portfolio.load',return_value={'synthetic':True}),patch('v11.advisory_portfolio.advice',return_value='PRIVATE-SYNTHETIC-CANARY'):
                delivery.run()
            self.assertIn('PRIVATE-SYNTHETIC-CANARY',send.call_args.args[0])
            self.assertNotIn('PRIVATE-SYNTHETIC-CANARY',json.dumps(j.writes))
            for p in Path(directory).iterdir():self.assertNotIn('PRIVATE-SYNTHETIC-CANARY',p.read_text())
    def test_manual_requires_explicit_main_dispatch_and_enabled_integration(self):
        with patch.dict(os.environ,dict(ENV)):
            self.assertEqual(delivery.manual_request_key(),'github-run-1000')
            for bad in ({'GITHUB_EVENT_NAME':'schedule'},{'GITHUB_RUN_ID':''},{'GITHUB_REF':'refs/heads/feature/test'}):
                with patch.dict(os.environ,bad),self.assertRaises(ValueError):delivery.manual_request_key()
            with patch.dict(os.environ,{'V111_INTEGRATION_ENABLED':'false'}),patch.object(pilot,'run') as old:
                with self.assertRaises(RuntimeError):delivery.run()
                old.assert_not_called()
    def test_multipart_send_stops_on_first_uncertain_part_without_retry(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"ok":true,"result":{"message_id":1}}'
        with patch.dict(os.environ,{'TELEGRAM_TOKEN':'synthetic','TELEGRAM_CHAT_ID':'synthetic'}),patch.object(pilot.urllib.request,'urlopen',side_effect=[response,TimeoutError('synthetic'),response]) as post:
            with self.assertRaises(TimeoutError):pilot.send('x'*12000)
            self.assertEqual(post.call_count,2)
