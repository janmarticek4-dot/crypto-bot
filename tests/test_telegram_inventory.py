import copy
import unittest
from v11 import telegram_inventory as t

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.state={'advisory_portfolio':{'positions':[dict(symbol='TAO',quantity=2.,average_cost=200.,currency='USD')],'cash':None},'source':'user_declared_inventory_not_trade_history','trading_enabled':False}
        self.n=10000;self.uid=0
    def msg(self,text,user=7,chat=7):
        self.uid+=1
        return dict(update_id=self.uid,message={'text':text,'date':self.n,'chat':{'id':chat,'type':'private'},'from':{'id':user}})
    def process(self,text,**kw):return t.process(self.state,self.msg(text),7,7,self.n,**kw)
    def confirm(self):
        self.uid+=1;p=self.state['telegram_inventory']['pending']
        return t.process(self.state,dict(update_id=self.uid,callback_query={'data':'ok:'+p['id'],'from':{'id':7},'message':{'date':self.n,'chat':{'id':7,'type':'private'}}}),7,7,self.n)
    def test_full_sale_confirm_only(self):
        self.process('/predal TAO');self.assertEqual(len(self.state['advisory_portfolio']['positions']),1)
        self.confirm();self.assertEqual(self.state['advisory_portfolio']['positions'],[])
    def test_partial_quantity(self):
        self.process('/predal TAO 0.5');self.confirm();p=self.state['advisory_portfolio']['positions'][0]
        self.assertEqual(p['quantity'],'1.5');self.assertEqual(p['average_cost'],200.)
    def test_partial_usd(self):
        self.process('/predal TAO 300 USD cena 250');self.confirm()
        self.assertEqual(self.state['advisory_portfolio']['positions'][0]['quantity'],'0.8')
    def test_buy_usd_quantity_average_fee(self):
        self.process('/kupil TAO 300 USD cena 100 poplatok 0');self.confirm()
        p=self.state['advisory_portfolio']['positions'][0];self.assertEqual(p['quantity'],'5.0');self.assertEqual(t.dec(p['average_cost']),t.dec('140'))
        self.process('/kupil FET 1000 cena 0.18 poplatok 2');self.confirm()
        self.assertEqual(self.state['advisory_portfolio']['positions'][1]['average_cost'],'0.182')
    def test_total_includes_fee(self):
        self.process('/kupil SOL 505 USD celkom cena 100 poplatok 5');self.confirm()
        p=self.state['advisory_portfolio']['positions'][1];self.assertEqual(p['quantity'],'5');self.assertEqual(p['average_cost'],'101')
    def test_unknown_fee_not_invented(self):
        self.process('/kupil SOL 500 USD cena 100');self.confirm()
        self.assertIsNone(self.state['advisory_portfolio']['positions'][1]['average_cost']);self.assertIsNone(self.state['advisory_portfolio']['cash'])
    def test_no_oversell_no_missing_price(self):
        old=copy.deepcopy(self.state['advisory_portfolio'])
        for x in ['/predal TAO 3','/predal TAO 300 USD','/kupil SOL 5','/kupil SOL NaN cena 1','/kupil SOL 0 cena 1']:
            self.process(x);self.assertEqual(self.state['advisory_portfolio'],old)
        self.assertIsNone(self.state['telegram_inventory']['pending'])
    def test_cash_confirmation(self):
        self.process('/hotovost 8500 USD');self.assertIsNone(self.state['advisory_portfolio']['cash']);self.confirm();self.assertEqual(self.state['advisory_portfolio']['cash'],'8500')
    def test_duplicate_update_confirmation(self):
        u=self.msg('/predal TAO');t.process(self.state,u,7,7,self.n)
        p=copy.deepcopy(self.state['telegram_inventory']['pending']);self.assertIsNone(t.process(self.state,u,7,7,self.n))
        self.confirm();self.uid+=1
        r=t.process(self.state,dict(update_id=self.uid,callback_query={'data':'ok:'+p['id'],'from':{'id':7},'message':{'date':self.n,'chat':{'id':7,'type':'private'}}}),7,7,self.n)
        self.assertIn('už použité',r['text']);self.assertEqual(len(self.state['telegram_inventory']['transactions']),1)
    def test_authorization(self):
        for user,chat in [(8,7),(7,8)]:
            self.assertIsNone(t.process(self.state,self.msg('/predal TAO',user,chat),7,7,self.n))
        self.assertEqual(len(self.state['advisory_portfolio']['positions']),1)
    def test_expiry_concurrent_change(self):
        self.process('/predal TAO');self.state['advisory_portfolio']['cash']=4
        self.assertIn('medzičasom',self.confirm()['text']);self.assertEqual(len(self.state['advisory_portfolio']['positions']),1)
        self.process('/predal TAO');self.n+=1801;self.assertIn('neplatné',self.confirm()['text'])
    def test_dynamic_token_ambiguity(self):
        resolver=lambda s:[dict(id='sui',symbol='SUI',price_available=False),dict(id='other-sui',symbol='SUI',price_available=True)]
        r=self.process('/kupil SUI 500 USD cena 1.5',resolver=resolver);self.assertIn('/token SUI sui',r['text']);self.assertIsNone(self.state['telegram_inventory']['pending'])
        self.process('/token SUI sui',resolver=resolver)
        self.process('/kupil SUI 500 USD cena 1.5',resolver=resolver);self.confirm()
        self.assertEqual(self.state['telegram_inventory']['assets']['SUI']['id'],'sui');self.assertEqual(len(self.state['advisory_portfolio']['positions']),2)
    def test_token_lookup_failure(self):
        def no(s):raise ValueError('unavailable')
        self.process('/kupil SUI 2 cena 1',resolver=no);self.assertEqual(len(self.state['advisory_portfolio']['positions']),1)
    def test_precision(self):
        self.process('/kupil SOL 0.00000000000000000001 cena 100 poplatok 0');self.confirm()
        self.assertEqual(self.state['advisory_portfolio']['positions'][1]['quantity'],'0.00000000000000000001')
    def test_multiple_and_unknown_quantity(self):
        self.process('/kupil SOL 1 cena 100 poplatok 0');self.confirm();self.process('/predal SOL TAO');self.confirm();self.assertEqual(self.state['advisory_portfolio']['positions'],[])
    def test_portfolio_valuation(self):
        r=t.portfolio_text(self.state,{'TAO':'250'});self.assertIn('+100.00',r);self.assertIn('500.00',r)
    def test_lost_ack_after_commit_no_reapply(self):
        self.process('/predal TAO 0.5');self.confirm();loaded=copy.deepcopy(self.state)
        self.assertEqual(loaded['advisory_portfolio']['positions'][0]['quantity'],'1.5')
        self.assertEqual(len(loaded['telegram_inventory']['transactions']),1)

if __name__=='__main__':unittest.main()

class EncryptedInventoryTests(unittest.TestCase):
    def test_cas_encryption_backup_and_conflict(self):
        import base64,hashlib,json
        from v11.secure_state import GitHubState,StateError
        files={}
        def transport(method,path,body=None):
            if path=='':return {'private':True}
            if method=='GET':return files.get(path,{'_not_found':True})
            if path in files and body.get('sha')!=files[path]['sha']:raise StateError('conflict')
            content=base64.b64decode(body['content']);sha=hashlib.sha1(content).hexdigest()
            files[path]={'sha':sha,'content':body['content']};return {'content':{'sha':sha}}
        a=GitHubState('test/private','synthetic',b'x'*32,transport=transport)
        a.initialize({'advisory_portfolio':{'positions':[],'cash':None},'trading_enabled':False})
        b=GitHubState('test/private','synthetic',b'x'*32,transport=transport)
        sa=a.read();sb=b.read();sa['advisory_portfolio']['cash']='9876.54321';a.commit(sa)
        raw=json.dumps(files);self.assertNotIn('9876.54321',raw)
        sb['advisory_portfolio']['cash']='1'
        with self.assertRaises(StateError):b.commit(sb)
        self.assertEqual(a.read()['advisory_portfolio']['cash'],'9876.54321')
        self.assertTrue(any('backups' in path for path in files))
    def test_store_unavailable_no_telegram_consumption(self):
        from unittest.mock import patch
        from scripts import private_advisory_updates as script
        with patch.dict(script.os.environ,{'TELEGRAM_TOKEN':'synthetic','TELEGRAM_CHAT_ID':'7','ADVISORY_TELEGRAM_USER_ID':'7'}),patch.object(script,'connect',side_effect=RuntimeError()),patch.object(script,'telegram') as call:
            with self.assertRaises(RuntimeError):script.run()
            call.assert_not_called()
    def test_confirm_failed_cas_never_acknowledges(self):
        from unittest.mock import patch
        from scripts import private_advisory_updates as script
        state={'advisory_portfolio':{'positions':[],'cash':None}}
        class Broken:
            def read(self):return state
            def commit(self,s):raise RuntimeError('CAS conflict')
        def tg(method,payload):
            return {'ok':True,'result':{} if method=='getWebhookInfo' else [dict(update_id=1,message={'text':'/hotovost 7 USD','date':10000,'chat':{'id':7,'type':'private'},'from':{'id':7}})]}
        with patch.dict(script.os.environ,{'TELEGRAM_TOKEN':'synthetic','TELEGRAM_CHAT_ID':'7','ADVISORY_TELEGRAM_USER_ID':'7'}),patch.object(script,'connect',return_value=Broken()),patch.object(script,'telegram',side_effect=tg) as call,patch.object(script.time,'time',return_value=10000):
            with self.assertRaises(RuntimeError):script.run()
            self.assertNotIn('sendMessage',[c.args[0] for c in call.call_args_list])
    def test_cash_zero_precision_and_future_quote(self):
        from scripts.private_advisory_updates import valid_quote
        from v11.advisory_portfolio import validate
        validate({'positions':[],'cash':'0.00'})
        self.assertFalse(valid_quote({'usd':1,'last_updated_at':10**15}))
    def test_owned_to_non_owned_uses_current_inventory(self):
        from tests.test_analyst_v112 import sample,model,NOW
        from v11 import analyst
        state={'advisory_portfolio':{'positions':[dict(symbol='TAO',quantity='2',average_cost='200',currency='USD')],'cash':None}}
        snap=sample();m=model(snap)
        before=analyst.final_text(m,snap,NOW,'manual',state['advisory_portfolio'])
        self.assertRegex(before,r'TAO[^\n]*HOLD \(držba\)')
        state['advisory_portfolio'],_=t.transition(state,t.parse('/predal TAO'),10000)
        after=analyst.final_text(m,snap,NOW,'manual',state['advisory_portfolio'])
        self.assertRegex(after,r'TAO[^\n]*WAIT \(nový nákup\)')
        self.assertNotRegex(after,r'TAO[^\n]*HOLD')
    def test_unknown_fees_explicit_and_nonterminating_quantity_reusable(self):
        s={'advisory_portfolio':{'positions':[],'cash':None}}
        book,tx=t.transition(s,t.parse('/kupil SOL 300 USD cena 104.41 poplatok 0'),10000)
        s['advisory_portfolio']=book
        new,_=t.transition(s,t.parse('/predal SOL 0.1'),10001)
        self.assertLess(t.dec(new['positions'][0]['quantity']),t.dec(book['positions'][0]['quantity']))

class MissingSourceTests(unittest.TestCase):
    def test_lookup_http_outage_returns_safe_reply(self):
        from v11.secure_state import StateError
        state={'advisory_portfolio':{'positions':[],'cash':None}}
        update=dict(update_id=1,message={'text':'/kupil SUI 2 cena 1','date':10000,'chat':{'id':7,'type':'private'},'from':{'id':7}})
        def unavailable(symbol):raise StateError('HTTP unavailable')
        reply=t.process(state,update,7,7,10000,unavailable)
        self.assertIn('nemožno',reply['text']);self.assertEqual(state['advisory_portfolio']['positions'],[])
    def test_no_sender_during_disabled_test(self):
        from unittest.mock import patch
        from scripts import private_advisory_updates as script
        from v11.secure_state import StateError
        with patch.dict(script.os.environ,{'BOT_DISABLE_TELEGRAM':'1'}),patch.object(script.urllib.request,'urlopen') as network:
            with self.assertRaises(StateError):script.telegram('sendMessage',{})
            network.assert_not_called()

class UnknownInitialQuantityTests(unittest.TestCase):
    def test_full_sale_of_unknown_initial_quantity_not_invented(self):
        state={'advisory_portfolio':{'positions':[dict(symbol='SOL',quantity=None,average_cost=None,currency='USD')],'cash':None}}
        book,tx=t.transition(state,t.parse('/predal SOL'),10000)
        self.assertEqual(book['positions'],[]);self.assertIsNone(tx['details'][0]['quantity']);self.assertIsNone(tx['details'][0]['gross'])
        with self.assertRaises(ValueError):t.transition(state,t.parse('/predal SOL 1'),10000)

class AdditionalHoldingTests(unittest.TestCase):
    def test_dynamic_holding_is_not_dropped_from_action_extraction(self):
        from tests.test_analyst_v112 import sample,model,NOW
        from v11 import analyst,report_verdict
        snap=sample();m=model(snap)
        inventory={'positions':[dict(symbol='SUI.X',quantity='2',average_cost='1',currency='USD')],'cash':None}
        text=analyst.final_text(m,snap,NOW,'morning',inventory)
        self.assertIn(('SUI.X','WAIT','držba'),report_verdict.actions(text))
