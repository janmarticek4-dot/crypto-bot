import base64
import copy
from datetime import datetime,timedelta,timezone
import json
import unittest
from unittest.mock import patch
from tests.test_state_hardening import MemoryGitHub
from tests import test_shadow as fixtures
from v11 import advisory_portfolio as a,macro_context as m,forecast_audit as f
from v11.secure_state import StateError
from v11.state_policy import require_public_data,PublicDataError

class AdvisoryCompletion(unittest.TestCase):
    def setUp(self):
        self.inventory={'positions':[{'symbol':'AAVE','quantity':None,'average_cost':None,'currency':'USD'}],'cash':None}
    def test_unknown_amounts_stay_unknown_and_inventory_is_private(self):
        self.assertEqual(a.validate(self.inventory),self.inventory)
        with self.assertRaises(PublicDataError):require_public_data({'advisory_portfolio':self.inventory})
        fixture=fixtures.ShadowTests();fixture.setUp()
        text=a.advice(self.inventory,fixture.snap)
        self.assertIn('N/A',text);self.assertNotIn('8500',text)
    def test_bad_inventory_refused_without_inventing_positions(self):
        for patchrow in ({'quantity':-1},{'average_cost':float('nan')},{'currency':'BAD'}):
            value=copy.deepcopy(self.inventory);value['positions'][0].update(patchrow)
            with self.assertRaises(StateError):a.validate(value)
    def test_private_import_requires_dedicated_repo_and_never_overwrites(self):
        remote=MemoryGitHub()
        original=remote.__call__
        def transport(method,path,body=None):
            if method=='GET' and path=='/contents/'+a.MARKER:return {'content':base64.b64encode(json.dumps(a.MARKER_VALUE).encode()).decode()}
            return original(method,path,body)
        env={'CONFIRM_PRIVATE_IMPORT':'true','PROD_STATE_REPOSITORY':'fixture/crypto-bot-state-production','PROD_STATE_TOKEN':'synthetic-fixture-token','PROD_STATE_ENCRYPTION_KEY':base64.b64encode(bytes([17])*32).decode(),'INITIAL_ADVISORY_PORTFOLIO':json.dumps(self.inventory)}
        self.assertTrue(a.initialize_from_secret(env,transport))
        self.assertEqual(a.load(env,transport),self.inventory)
        writes=remote.writes
        with self.assertRaises(StateError):a.initialize_from_secret(env,transport)
        self.assertEqual(remote.writes,writes)
        env['PROD_STATE_REPOSITORY']='fixture/crypto-bot-state-integration-test'
        with self.assertRaises(StateError):a.connect(env,transport)
    def test_macro_values_are_period_observations_not_release_or_consensus(self):
        now=datetime(2026,10,26,tzinfo=timezone.utc)
        raw=b'observation_date,CPIAUCSL,PCEPI,UNRATE,PAYEMS\n2026-09-01,300,120,4,150000\n2026-10-01,.,.,.,.\n'
        result=m.economic_observations(now,lambda s:raw)
        self.assertEqual(result['observations']['CPIAUCSL']['period'],'2026-09-01')
        self.assertIsNone(result['consensus']);self.assertFalse(result['first_release'])
        self.assertIn('nie je dátum zverejnenia',' '.join(m.economic_lines(result)))
    def test_forecast_outcome_waits_for_horizon_and_tracks_failures(self):
        fixture=fixtures.ShadowTests();fixture.setUp();snap=fixture.snap
        start=snap['at'];state={}
        f.update(state,snap,{'events':[]},'fixture_07:00')
        item=state['analysis_forecasts_v11'][0];item['delivery_confirmed']=True
        now=item['due']+1800
        future=copy.deepcopy(snap);future['at']=now
        due_bar=int((item['due']//3600)*3600-3600)
        future['coins'][item['symbol']].setdefault('raw',{})['1h']=[{'timestamp':due_bar*1000,'close':item['high']*2}]
        f.update(state,future,{'events':[]},'fixture_20:00')
        self.assertEqual(state['forecast_totals_v1']['outside'],1)
        self.assertIn('nepotvrdených',' '.join(f.lines(state)))
        f.update(state,future,{'events':[]},'fixture_later')
        self.assertEqual(state['forecast_totals_v1']['evaluated'],1)

    def test_inventory_commands_record_user_facts_but_never_place_orders(self):
        from scripts.private_advisory_updates import apply_inventory_command,authorized
        state={'advisory_portfolio':self.inventory}
        reply=apply_inventory_command(state,'POZICIA AAVE 2 100 USD')
        self.assertEqual(state['advisory_portfolio']['positions'][0]['quantity'],2)
        self.assertIsNone(state['advisory_portfolio']['cash'])
        self.assertIn('Žiadny obchod',reply)
        with self.assertRaises(ValueError):apply_inventory_command(state,'BUY AAVE 100')
        self.assertFalse(authorized({'chat':{'id':1,'type':'group'},'from':{'id':2}},1))
        self.assertTrue(authorized({'chat':{'id':1,'type':'private'},'from':{'id':1}},1))
        self.assertFalse(authorized({'chat':{'id':1,'type':'private'},'from':{'id':2}},1))
        apply_inventory_command(state,'UZAVRETA AAVE')
        self.assertEqual(state['advisory_portfolio']['positions'],[])

    def test_delivery_health_distinguishes_missing_uncertain_and_sent(self):
        from scripts.check_analysis_delivery import assess
        now=datetime(2026,10,27,8,tzinfo=timezone.utc)
        self.assertEqual(assess(now,{}),'MISSING')
        key='2026-10-27-morning'
        self.assertEqual(assess(now,{'slots':{key:{'status':'uncertain'}}}),'UNCERTAIN')
        self.assertEqual(assess(now,{'slots':{key:{'status':'sent'}}}),'SENT')
        self.assertEqual(assess(now-timedelta(hours=1),{}),'NOT_DUE')

    def test_long_horizon_pending_forecasts_are_not_dropped_by_recent_outcomes(self):
        fixture=fixtures.ShadowTests();fixture.setUp();snap=fixture.snap;now=snap['at']
        original={'id':'old-long','symbol':'AAVE','at':now-13*86400,'due':now+86400,'horizon':'7–14 dní','low':1,'high':10000,'delivery_confirmed':True,'outcome':None}
        state={'analysis_forecasts_v11':[original]+[dict(original,id='done'+str(i),outcome={'inside':False,'return_pct':0,'counted':True}) for i in range(400)]}
        f.update(state,snap,{'events':[]},'new_20:00')
        self.assertIn('old-long',[item['id'] for item in state['analysis_forecasts_v11']])

    def test_private_advice_is_sent_but_never_persisted_in_public_journal(self):
        import os
        from scripts import v111_trial as pilot
        fixture=fixtures.ShadowTests();fixture.setUp()
        now=datetime(2026,10,27,6,tzinfo=timezone.utc);writes=[]
        with patch.dict(os.environ,{'PRIVATE_ADVISORY_ENABLED':'true'}),patch.object(pilot,'datetime') as clock,patch.object(pilot,'PublicJournal') as journal,patch.object(pilot.data,'collect',return_value=fixture.snap),patch.object(pilot.fundamentals,'collect',return_value={'events':[]}),patch.object(pilot.macro_context,'collect',return_value={}),patch.object(pilot.macro_context,'economic_observations',return_value={'url':'https://fred.stlouisfed.org','checked_at':now.isoformat(),'observations':{}}),patch('v11.advisory_portfolio.load',return_value=self.inventory),patch('v11.advisory_portfolio.advice',return_value='PRIVATE-ADVICE-CANARY'),patch.object(pilot,'send') as send:
            clock.now.return_value=now
            journal.return_value.read.return_value={'schema':1,'slots':{}}
            journal.return_value.save.side_effect=lambda state:writes.append(copy.deepcopy(state))
            pilot.run()
        self.assertIn('PRIVATE-ADVICE-CANARY',send.call_args.args[0])
        self.assertTrue(writes)
        for written in writes:
            self.assertNotIn('PRIVATE-ADVICE-CANARY',json.dumps(written))
            require_public_data(written)

    def test_private_inventory_offset_is_committed_before_telegram_ack(self):
        import os
        from scripts import private_advisory_updates as updates
        state={'advisory_portfolio':self.inventory,'as_of':'2026-01-01T00:00:00+00:00','inventory_start_at':'2026-01-01T00:00:00+00:00'}
        order=[]
        def telegram(method,payload):
            order.append(method)
            return {'result':[{'update_id':1,'message':{'date':int(datetime(2026,10,26,tzinfo=timezone.utc).timestamp()),'chat':{'id':1,'type':'private'},'from':{'id':1},'text':'POZICIA AAVE 2 100 USD'}}]} if method=='getUpdates' else {'ok':True}
        with patch.dict(os.environ,{'PROD_STATE_TOKEN':'fixture','PROD_STATE_ENCRYPTION_KEY':'fixture','PROD_STATE_REPOSITORY':'fixture','TELEGRAM_CHAT_ID':'1'}),patch.object(updates,'connect') as connect,patch.object(updates,'telegram',side_effect=telegram):
            connect.return_value.read.return_value=state
            connect.return_value.commit.side_effect=lambda value:order.append('encrypted_commit')
            updates.run()
        self.assertEqual(order,['getUpdates','encrypted_commit','sendMessage'])
        self.assertEqual(state['telegram_update_offset'],2)
