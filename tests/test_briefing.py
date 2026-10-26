import unittest
from datetime import datetime, timezone
from copy import deepcopy
from v11.briefing import scenarios, evaluate, remember, event_lines, fundamental_lines, build
from v11.data import PRIMARY

NOW=datetime(2026,10,21,5,tzinfo=timezone.utc).timestamp()
def coin():
    return dict(price=100,stale=False,change_24h=2,age_seconds=10,price_source='fixture',market_cap=1000,volume_24h=100,
        frames={tf:dict(support=90,resistance=110,atr=2,ema200=95,ema50=98,rsi14=55,adx=22) for tf in ('4h','1d')})
def snapshot():return dict(at=NOW,coins={s:coin() for s in ('BTC',*PRIMARY)},global_data={})

class BriefingTests(unittest.TestCase):
    def test_missing_scenario(self):
        self.assertTrue(all(not f['available'] for f in scenarios({'stale':True})))
    def test_no_probability(self):
        self.assertIn('pravdepodobnosti N/A',scenarios(coin())[0]['text'])
    def test_no_future_evaluation(self):
        s={'analysis_forecasts_v11':[dict(symbol='BTC',due=NOW+1,outcome=None)]}
        evaluate(s,snapshot());self.assertIsNone(s['analysis_forecasts_v11'][0]['outcome'])
    def test_exact_closed_bar(self):
        snap=snapshot();snap['coins']['BTC']['raw']={'1h':[dict(timestamp=(NOW-3600)*1000,close=80),dict(timestamp=NOW*1000,close=150)]}
        state={'analysis_forecasts_v11':[dict(symbol='BTC',due=NOW,price=100,low=90,high=110,outcome=None)]}
        evaluate(state,snap)
        self.assertEqual(state['analysis_forecasts_v11'][0]['outcome']['price'],80)
        self.assertFalse(state['analysis_forecasts_v11'][0]['outcome']['inside'])
    def test_missing_due_price_not_replaced(self):
        state={'analysis_forecasts_v11':[dict(symbol='BTC',due=NOW,price=100,low=90,high=110,outcome=None)]}
        evaluate(state,snapshot());self.assertIsNone(state['analysis_forecasts_v11'][0]['outcome'])
    def test_idempotent_forecast_and_morning(self):
        state={};snap=snapshot()
        remember(state,snap,{},'2026-10-21 07:00');original=deepcopy(state['analysis_forecasts_v11'])
        snap['coins']['BTC']['price']=105
        remember(state,snap,{},'2026-10-21 07:00')
        self.assertEqual(original,state['analysis_forecasts_v11'])
        self.assertEqual(state['morning_plan_v11']['date'],'2026-10-21')
    def test_calendar_dst_conversion(self):
        event=dict(scheduled=True,event_at='2026-10-28T18:00:00+00:00',title='test',url='https://example.test',categories=['Fed'])
        lines=event_lines({'events':[event]},datetime(2026,10,28,tzinfo=timezone.utc).timestamp())
        self.assertIn('28.10.2026 19:00',' '.join(lines))
    def test_date_without_time_not_fabricated(self):
        event=dict(scheduled=True,event_at='2026-10-21',title='test')
        self.assertNotIn('00:00',' '.join(event_lines({'events':[event]},NOW)))
    def test_no_news_does_not_mean_neutral(self):
        text=' '.join(fundamental_lines('TAO',{'events':[]},{},NOW))
        self.assertIn('hodnotenie N/A',text)
        self.assertIn('neznamená to absenciu',text)
    def test_report_and_evening(self):
        snap=snapshot();ev={s:dict(action='WAIT',held=False,reasons=[],data_complete=True,score=3) for s in PRIMARY}
        state={};remember(state,snap,ev,'2026-10-21 07:00')
        text='\n'.join(build(snap,ev,{},dict(state='NORMAL',reasons=[]),{'events':[]},state,'2026-10-21 20:00',datetime(2026,10,21,20)))
        self.assertIn('POROVNANIE S RÁNOM',text)
        for s in PRIMARY:self.assertIn(s+': WAIT',text)
        self.assertIn('Bot nikdy nevykonáva obchody',text)
        self.assertIn('24–72 h',text);self.assertIn('7–14 dní',text)
        self.assertIn('NAJBLIŽŠÍCH 24 HODÍN',text)

if __name__=='__main__':unittest.main()

class EventLifecycleTests(unittest.TestCase):
    def test_past_event_does_not_invent_release_result(self):
        from v11.event_ledger import update,lines
        event=dict(id='x',title='CPI',scheduled=True,event_at=datetime.fromtimestamp(NOW-3600,timezone.utc).isoformat(),url='https://www.bls.gov/')
        state={};update(state,[event],snapshot())
        item=next(iter(state['event_ledger_v11'].values()))
        self.assertIsNone(item['result']);self.assertIsNone(item['expectation'])
        self.assertIn('číselný výsledok N/A',' '.join(lines(state,NOW)))
    def test_fomc_date_never_assumes_2pm(self):
        from v11.fundamentals import parse_fomc
        source=dict(id='fomc',url='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',official=True)
        html=b'<h4>2026 FOMC Meetings</h4><div class="fomc-meeting__month">October</div><div class="fomc-meeting__date">27-28*</div>'
        events=parse_fomc(html,source,datetime.fromtimestamp(NOW,timezone.utc))
        self.assertEqual(events[0]['event_date'],'2026-10-28')
        self.assertIsNone(events[0]['event_at'])
        text=' '.join(event_lines({'events':events},NOW))
        self.assertIn('presný čas Bratislava N/A',text)
        self.assertNotIn('20:00',text)
    def test_repeat_event_deduplicates_observation(self):
        from v11.event_ledger import update
        event=dict(id='x',title='CPI',scheduled=True,event_at=datetime.fromtimestamp(NOW-3600,timezone.utc).isoformat(),url='https://www.bls.gov/')
        state={};update(state,[event],snapshot());update(state,[event],snapshot())
        self.assertEqual(len(state['event_ledger_v11']),1)
        self.assertEqual(len(next(iter(state['event_ledger_v11'].values()))['observations']),1)
