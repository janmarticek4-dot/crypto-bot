import copy,unittest
from datetime import datetime,timezone,timedelta
from v11.news_incidents import group_news
from v11.production_schedule import due_phase
from v11.support_scenarios import assess
NOW=datetime(2026,11,2,19,42,tzinfo=timezone.utc)
def story(i,title,**kw):
    return dict(id=str(i),title=title,published_at=NOW.isoformat(),url='https://example.org/'+str(i),source='synthetic',kind='news',state='NEWS',categories=['hack'],symbols=[],**kw)

class IncidentTests(unittest.TestCase):
    def test_actual_evening_is_two_incidents_not_three_or_one(self):
        rows=[story(1,'Mercado Bitcoin wallets keep moving funds after $46M hack'),story(2,'North Korea Is Laundering Binance Hack Loot at One New Wallet Every 25 Seconds'),story(3,"Brazil's Largest Exchange Mercado Bitcoin Halts Withdrawals After $40 Million Hack")]
        groups,_=group_news(rows,[],NOW)
        self.assertEqual(len(groups),2)
        mercado=next(g for g in groups if g['incident_entity']=='mercado-bitcoin')
        self.assertEqual(len(mercado['citations']),2);self.assertIn('odhady sa líšia',mercado['text'])
    def test_generic_article_matches_only_unique_evidence_anchor(self):
        rows=[story(1,'Binance hack caused $6.3B loss'),story(2,'Exchange withdrawals halted after $6.30 billion hack')]
        groups,_=group_news(rows,[],NOW);self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['incident_entity'],'binance')
    def test_two_incidents_same_exchange_separate_explicit_dates(self):
        rows=[story(1,'Binance hack loss $2M',incident_date='2026-10-30'),story(2,'Binance hack loss $3M',incident_date='2026-11-02')]
        self.assertEqual(len(group_news(rows,[],NOW)[0]),2)
    def test_restart_stable_id_and_new_material_fact(self):
        first=group_news([story(1,'Binance hack loss $6.3B')],[],NOW)[0][0]
        second=group_news([story(2,'Binance withdrawals resumed after hack')],[first],NOW+timedelta(hours=2))[0][0]
        self.assertEqual(first['id'],second['id']);self.assertIn('withdrawals_resumed',second['incident_facts'])
    def test_unidentified_generic_headline_not_filled_with_fake_facts(self):
        rows,diag=group_news([story(1,'Crypto exchange hack reported')],[],NOW)
        self.assertEqual(rows,[]);self.assertEqual(diag[0]['reason'],'UNVERIFIED_INCIDENT_IDENTITY')
    def test_42_minute_delay_due_once_and_uncertain_not_replayed(self):
        self.assertEqual(due_phase(NOW,{'slots':{}}),'evening')
        for status in ('sent','attempting','uncertain'):
            self.assertEqual(due_phase(NOW,{'slots':{'2026-11-02-evening':{'status':status}}}),'')

class SupportTests(unittest.TestCase):
    def coin(self):
        step=14400000;end=int(NOW.timestamp()*1000)//step*step
        rows=[]
        for i in range(240):
            # Repeatable historical pivot 80, while recent support 93 has broken.
            low=80 if i in (40,80,120) else 95
            rows.append(dict(timestamp=end-(240-i)*step,open=100,high=103,low=low,close=100,volume=100))
        for row in rows[-2:]:row.update(open=94,high=95,low=89,close=90,volume=200)
        return dict(price=91.12,stale=False,raw={'4h':rows},frames={'4h':{'support':93.18,'atr':2}})
    def test_sol_and_tao_breakdown_new_closed_history_zone_no_buy(self):
        for symbol in ('SOL','TAO'):
            c=self.coin();r=assess(c,int(NOW.timestamp()*1000))
            self.assertEqual(r['breakdown'],'CONFIRMED_2_CLOSED_BARS')
            self.assertEqual(r['support']['price'],80);self.assertLess(r['support']['price'],c['price'])
            self.assertFalse(r['approved_buy']);self.assertFalse(r['pullback']['ready']);self.assertIn('level',r['confirmed'])
    def test_no_history_and_intrabar_not_confirmed_break(self):
        c=self.coin();c['raw']['4h'][-1]['close']=94
        self.assertEqual(assess(c,int(NOW.timestamp()*1000))['breakdown'],'INTRABAR_OR_UNCONFIRMED')
        c['raw']['4h']=[];self.assertIsNone(assess(c,int(NOW.timestamp()*1000))['support'])

class DeliveryHistoryTests(unittest.TestCase):
    def test_fact_history_survives_restart_without_repeating_updates(self):
        from v11 import event_notices as en
        def fund(i,title):
            e=story(i,title,retrieved_at=NOW.isoformat())
            return {'events':[e]}
        j={};plan=en.plan(fund(1,'Binance hack caused $6.3B loss'),j,NOW)
        self.assertEqual(len(plan['selected']),1);en.commit(j,plan,NOW)
        plan=en.plan(fund(2,'Binance withdrawals resumed after hack'),copy.deepcopy(j),NOW+timedelta(minutes=1))
        self.assertEqual(len(plan['selected']),1);self.assertIn('obnovenie',plan['selected'][0]['text'])
        en.commit(j,plan,NOW+timedelta(minutes=1))
        plan=en.plan(fund(3,'Binance hack caused $6.3B loss'),copy.deepcopy(j),NOW+timedelta(minutes=2))
        self.assertEqual(plan['selected'],[])
        self.assertTrue(next(v for v in j[en.KEY].values() if v.get('incident_id'))['announced_facts'])

class LegacyHistoryTests(unittest.TestCase):
    def test_already_announced_aspects_are_merged_before_deciding_novelty(self):
        from v11 import event_notices as en
        older=[story(1,'Mercado Bitcoin moving funds after $46M hack'),story(2,'Mercado Bitcoin halts withdrawals after $40M hack')]
        for row in older:row.update(last_announced_at=NOW.isoformat(),semantic='old-headline-hash')
        j={en.KEY:{r['id']:r for r in older}}
        fresh=story(3,'Mercado Bitcoin halts withdrawals after $40M hack',retrieved_at=NOW.isoformat())
        self.assertEqual(en.plan({'events':[fresh]},j,NOW)['selected'],[])

class AmountContextTests(unittest.TestCase):
    def test_frozen_assets_and_reserves_are_not_presented_as_loss_estimates(self):
        rows=[story(1,'Binance $6.3B hack; freezes $3B assets'),story(2,'Binance holds $5B matching tokens to cover hack losses')]
        group=group_news(rows,[],NOW)[0][0]
        self.assertNotIn('odhady sa líšia',group['text'])
        self.assertIn('plán krytia',group['text']);self.assertIn('nie je dokončená náhrada',group['text'])

class DailyFallbackTests(unittest.TestCase):
    def test_lower_daily_support_used_when_recent_intraday_has_no_zone(self):
        c=SupportTests().coin()
        for row in c['raw']['4h']:row['low']=min(row['open'],row['close'])-0.5
        day=86400000;end=int(NOW.timestamp()*1000)//day*day
        c['raw']['1d']=[dict(timestamp=end-(80-i)*day,open=100,close=100,high=105,low=70 if i in (10,30) else 95,volume=100) for i in range(80)]
        r=assess(c,int(NOW.timestamp()*1000))
        self.assertEqual(r['support']['price'],70);self.assertEqual(r['support']['timeframe'],'1d')

class AmbiguityTests(unittest.TestCase):
    def test_cross_exchange_price_comparison_not_a_second_hack(self):
        rows,diag=group_news([story(1,'Coinbase leads selloff after Binance hack loss $6.3B')],[],NOW)
        self.assertEqual(rows[0]['incident_entity'],'binance')
        rows,diag=group_news([story(2,'Binance and Coinbase security incidents reported')],[],NOW)
        self.assertEqual(rows,[]);self.assertTrue(diag)

class MonetaryScopeTests(unittest.TestCase):
    def test_article_body_market_metrics_not_reported_as_hack_loss(self):
        row=story(1,'Binance $6.3B hack',excerpt='Market capitalization $171B, volume $515M; a bitcoin treasury $643M. Protocol fees $106M.')
        value=group_news([row],[],NOW)[0][0]
        self.assertEqual(value['reported_amounts'],['6300000000'])
        self.assertNotIn('171000',value['text'])
    def test_recovered_amount_is_not_new_total_loss_estimate(self):
        row=story(1,'Mercado Bitcoin recovers $4.5M after hack')
        self.assertEqual(group_news([row],[],NOW)[0][0]['reported_amounts'],[])

class IncompatibleAmountsTests(unittest.TestCase):
    def test_widely_different_historical_scopes_not_presented_as_same_loss(self):
        rows=[story(1,'Binance $106M hack'),story(2,'Binance $6B hack')]
        grouped,_=group_news(rows,[],NOW)
        self.assertTrue(grouped[0]['amounts_ambiguous'])
        self.assertTrue(grouped[0]['suppress_uninformative'])
        self.assertNotIn('106/6000',grouped[0].get('text',''))

class ReservationSizeTests(unittest.TestCase):
    def test_delivery_reservation_keeps_dedup_facts_without_copying_article_payloads(self):
        from scripts.v111_trial import reserve_events
        row=dict(id='i',state='NEWS',semantic='s',title='Binance hack',published_at=NOW.isoformat(),kind='news',incident_id='i',incident_facts=['breach'],reported_amounts=[],citations=[{'url':'https://example.org/'+('x'*10000)}],excerpt='x'*5000)
        stored=reserve_events({'selected':[row]})[0]
        self.assertEqual(stored['semantic'],'s');self.assertEqual(stored['incident_facts'],['breach'])
        self.assertNotIn('citations',stored);self.assertNotIn('excerpt',stored)
