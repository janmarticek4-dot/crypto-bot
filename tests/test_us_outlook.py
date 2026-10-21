import copy
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import main
from us_context import report as us

UTC=timezone.utc
NOW=datetime(2026,10,21,13,0,tzinfo=UTC)
SLOT='BRATISLAVA_2026-10-21_15:00'


def ticker(symbol='BTC', change=2.75, now=NOW):
    return dict(symbol=symbol+'USDT',lastPrice='100',priceChangePercent=str(change),
                openTime=(now-timedelta(days=1)).timestamp()*1000,closeTime=now.timestamp()*1000)


def global_data(now=NOW,change=-.15):
    return dict(data=dict(updated_at=now.timestamp(),total_market_cap={'usd':2.81e12},
                         market_cap_change_percentage_24h_usd=change,market_cap_percentage={'btc':59.6}))


def quote(symbol='NQ=F',now=NOW,previous=100,price=101):
    return {'chart':{'error':None,'result':[{'meta':dict(symbol=symbol,currency='USD',
        instrumentType='INDEX' if symbol.startswith('^') else 'FUTURE',regularMarketPrice=price,
        chartPreviousClose=previous,regularMarketTime=now.timestamp())}]}}


def snapshot(now=NOW):
    return dict(market=us.session(now),quotes={s:us.parse_quote({},s,now,us.session(now)) for s in us.QUOTES},
        crypto=us.crypto_snapshot([ticker(now=now),ticker('SOL',-3,now),ticker('AAVE',-1,now)],[],global_data(now),now),
        macro=[],sources={})


class CalendarTests(unittest.TestCase):
    def test_dst_mismatch_weeks_and_normal_weeks(self):
        for date,hour,phase in [('2026-03-06',9,'PREOPEN'),('2026-03-09',10,'AFTER OPEN'),
                ('2026-03-27',10,'AFTER OPEN'),('2026-03-30',9,'PREOPEN'),
                ('2026-10-23',9,'PREOPEN'),('2026-10-26',10,'AFTER OPEN'),('2026-11-02',9,'PREOPEN')]:
            with self.subTest(date=date):
                at=datetime.fromisoformat(date+'T15:00:00').replace(tzinfo=us.BRATISLAVA)
                result=us.session(at)
                self.assertEqual(result['ny'].hour,hour)
                self.assertEqual(result['phase'],phase)
                self.assertEqual(main.get_main_analysis_slot(at.astimezone(UTC)),f'BRATISLAVA_{date}_15:00')

    def test_real_incident_time_is_opening_not_preopen(self):
        self.assertEqual(us.session(NOW)['phase'],'PREOPEN')
        delayed=NOW+timedelta(minutes=33)
        self.assertEqual(us.session(delayed)['phase'],'OPENING')
        self.assertEqual(us.session(NOW+timedelta(hours=1))['phase'],'AFTER OPEN')

    def test_opening_boundaries(self):
        for minute,second,expected in [(29,59,'PREOPEN'),(30,0,'OPENING'),(59,59,'OPENING')]:
            at=NOW.replace(minute=minute,second=second)
            self.assertEqual(us.session(at)['phase'],expected)
        self.assertEqual(us.session(NOW.replace(hour=14))['phase'],'AFTER OPEN')

    def test_holidays_observed_holidays_and_weekends(self):
        for day in ['2026-01-01','2026-01-19','2026-02-16','2026-04-03','2026-05-25',
                    '2026-06-19','2026-07-03','2026-09-07','2026-11-26','2026-12-25',
                    '2026-10-24','2026-10-25','2025-01-09']:
            with self.subTest(day=day):
                self.assertEqual(us.session(datetime.fromisoformat(day+'T15:00:00').replace(tzinfo=us.BRATISLAVA))['phase'],'CLOSED')

    def test_early_close_and_full_close(self):
        for date in ['2026-11-27','2026-12-24']:
            at=datetime.fromisoformat(date+'T12:59:00').replace(tzinfo=us.NEW_YORK)
            self.assertEqual(us.session(at)['phase'],'AFTER OPEN')
            self.assertEqual(us.session(at+timedelta(minutes=1))['phase'],'CLOSED')
        at=datetime(2026,10,21,16,tzinfo=us.NEW_YORK)
        self.assertEqual(us.session(at)['phase'],'CLOSED')

    def test_calendar_failure_is_unknown_not_open(self):
        def unavailable(year):raise RuntimeError('offline')
        self.assertEqual(us.session(NOW,get_calendar=unavailable)['phase'],'N/A')

    def test_naive_times_rejected(self):
        with self.assertRaises(ValueError):us.session(datetime(2026,10,21,15))
        with self.assertRaises(ValueError):main.get_main_analysis_slot(datetime(2026,10,21,15))

    def test_scheduler_morning_evening_grace_and_duplicate(self):
        with patch.dict(os.environ,{'GITHUB_EVENT_NAME':'schedule','MANUAL_ANALYSIS':'false'}):
            for hour in (7,15,20):
                at=NOW.astimezone(us.BRATISLAVA).replace(hour=hour)
                slot=main.get_main_analysis_slot(at)
                self.assertTrue(slot.endswith(f'{hour:02}:00'))
                self.assertIsNotNone(main.get_main_analysis_slot(at+timedelta(minutes=89)))
                self.assertIsNone(main.get_main_analysis_slot(at+timedelta(minutes=90)))
                with patch.object(main,'load_state',return_value={'last_main_slot':slot}):
                    self.assertFalse(main.is_main_analysis_time(at)[0])


class QuoteTests(unittest.TestCase):
    def test_futures_distinct_from_index_and_have_update_time(self):
        q=us.parse_quote(quote(), 'NQ=F', NOW,us.session(NOW))
        self.assertEqual(q['kind'],'future');self.assertEqual(q['at'],NOW)
        self.assertIn('Nasdaq-100',q['name']);self.assertAlmostEqual(q['change'],1)
        self.assertIsNone(us.parse_quote(quote(),'^IXIC',NOW,us.session(NOW))['price'])

    def test_open_index_requires_current_session_quote(self):
        at=NOW+timedelta(minutes=33)
        self.assertIsNone(us.parse_quote(quote('^GSPC',NOW+timedelta(minutes=20)),'^GSPC',at,us.session(at))['price'])
        self.assertIsNotNone(us.parse_quote(quote('^GSPC',at),'^GSPC',at,us.session(at))['price'])

    def test_previous_cash_close_preopen_labeled_not_live(self):
        previous=datetime(2026,10,20,20,tzinfo=UTC)
        q=us.parse_quote(quote('^IXIC',previous),'^IXIC',NOW,us.session(NOW))
        self.assertEqual(q['status'],'posledná uzavretá seansa')
        self.assertIsNotNone(q['price'])
        older=previous-timedelta(days=1)
        self.assertIsNone(us.parse_quote(quote('^IXIC',older),'^IXIC',NOW,us.session(NOW))['price'])

    def test_monday_preopen_uses_friday_close(self):
        monday=datetime(2026,10,26,12,tzinfo=UTC)  # 08:00 NY, before open despite EU DST change
        friday=datetime(2026,10,23,20,tzinfo=UTC)
        q=us.parse_quote(quote('^GSPC',friday),'^GSPC',monday,us.session(monday))
        self.assertEqual(q['status'],'posledná uzavretá seansa')

    def test_stale_future_and_future_clock_rejected(self):
        for at in [NOW-timedelta(minutes=21),NOW+timedelta(minutes=2)]:
            self.assertIsNone(us.parse_quote(quote(now=at),'NQ=F',NOW,us.session(NOW))['price'])

    def test_wrong_currency_instrument_nan_or_no_timestamp(self):
        for key,value in [('currency','EUR'),('instrumentType','INDEX'),('regularMarketPrice',float('nan')),('regularMarketTime',None),('regularMarketPrice',True)]:
            d=quote();d['chart']['result'][0]['meta'][key]=value
            self.assertIsNone(us.parse_quote(d,'NQ=F',NOW,us.session(NOW))['price'])

    def test_malformed_payload_is_na(self):
        for payload in [None,{},[],{'chart':None},{'chart':{'result':[]}}, {'chart':{'result':[{'meta':[]}]}}]:
            self.assertIsNone(us.parse_quote(payload,'NQ=F',NOW,us.session(NOW))['price'])

    def test_calendar_cash_holiday_does_not_close_futures(self):
        at=datetime(2026,11,26,14,tzinfo=UTC)
        self.assertEqual(us.session(at)['phase'],'CLOSED')
        self.assertIsNotNone(us.parse_quote(quote(now=at),'NQ=F',at,us.session(at))['price'])
        self.assertIsNone(us.parse_quote(quote('^IXIC',at),'^IXIC',at,us.session(at))['price'])

    def test_refresh_crossing_bell_removes_old_cash_quote(self):
        data=snapshot();old=datetime(2026,10,20,20,tzinfo=UTC)
        data['quotes']['^GSPC']=us.parse_quote(quote('^GSPC',old),'^GSPC',NOW,us.session(NOW))
        us.refresh(data,NOW+timedelta(minutes=33))
        self.assertEqual(data['market']['phase'],'OPENING')
        self.assertIsNone(data['quotes']['^GSPC']['price'])
        self.assertIsNone(data['crypto']['cap'])


class CryptoTests(unittest.TestCase):
    def test_exact_requested_btc_global_divergence(self):
        c=snapshot()['crypto'];warnings=us.divergences(c)
        self.assertTrue(any('BTC +2.75% vs kryptotrh -0.15%' in w for w in warnings))
        self.assertTrue(any('SOL' in w for w in warnings))

    def test_no_invented_divergence_missing_or_old_data(self):
        c=us.crypto_snapshot([],[],{},NOW)
        self.assertEqual(us.divergences(c),[])
        c=us.crypto_snapshot([ticker()],[],global_data(NOW-timedelta(minutes=30)),NOW)
        self.assertEqual(us.divergences(c),[])
        self.assertIsNone(c['cap'])

    def test_invalid_or_non_24h_ticker_not_compared(self):
        t=ticker();t['openTime']=NOW.timestamp()*1000
        c=us.crypto_snapshot([t],[],global_data(),NOW)
        self.assertIsNone(c['coins']['BTC']['change'])
        self.assertEqual(us.divergences(c),[])

    def test_coingecko_fallback_has_its_own_time_and_source(self):
        m=[dict(id='bitcoin',current_price=100,price_change_percentage_24h=2,last_updated=NOW.isoformat())]
        c=us.crypto_snapshot([],m,{},NOW)
        self.assertEqual(c['coins']['BTC']['source'],'CoinGecko USD')
        self.assertEqual(c['coins']['BTC']['change'],2)
        self.assertEqual(c['coins']['BTC']['at'],NOW)

    def test_partial_or_malformed_data_is_na_not_zero(self):
        for g in [None,[],{}, {'data':None},{'data':{'updated_at':NOW.timestamp(),'total_market_cap':[]}}]:
            c=us.crypto_snapshot([{'symbol':[]}],[{'id':{}}],g,NOW)
            self.assertIsNone(c['cap']);self.assertIsNone(c['dominance'])
            self.assertTrue(all(d['change'] is None for d in c['coins'].values()))

    def test_uniform_positive_returns_not_called_divergence(self):
        c=us.crypto_snapshot([ticker(),ticker('SOL',3)],[],global_data(change=2),NOW)
        self.assertEqual(us.divergences(c),[])

    def test_only_the_requested_watchlist_is_included(self):
        c=us.crypto_snapshot([ticker(),ticker('SOL',3),ticker('AAVE',-2)],[],{},NOW,watched={'SOL':'solana'})
        self.assertEqual(set(c['coins']),{'BTC','SOL'})


class MacroTests(unittest.TestCase):
    def calendar(self,date='20261021T083000',title='Employment situation',url='https://www.bls.gov/schedule/news_release/'):
        return f'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=America/New_York:{date}\nSUMMARY:{title}\nURL:{url}\nEND:VEVENT\nEND:VCALENDAR'.encode()

    def test_today_past_release_in_calendar_keeps_exact_time_not_result(self):
        events=us.macro_events({'bls_calendar':self.calendar()},NOW)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['at'],NOW-timedelta(minutes=30))
        self.assertTrue(events[0]['scheduled'])
        data=snapshot();data['macro']=events
        message=us.render(data,NOW,SLOT)
        self.assertIn('08:30 NY / 14:30 BL',message)
        self.assertIn('výsledok N/A',message)
        self.assertIn('https://www.bls.gov/',message)

    def test_old_tomorrow_unrelated_undated_external_excluded(self):
        for raw in [self.calendar('20261020T083000'),self.calendar('20261022T083000'),
                    self.calendar(title='Unrelated speech'),self.calendar(url='https://evil.invalid/'),b'not a calendar']:
            self.assertEqual(us.macro_events({'bls_calendar':raw},NOW),[])

    def test_only_today_official_rss_and_no_future_publication(self):
        def rss(date):
            return f'<rss><channel><item><title>FOMC monetary policy statement</title><link>https://www.federalreserve.gov/newsevents/x.htm</link><pubDate>{date}</pubDate></item></channel></rss>'.encode()
        self.assertEqual(len(us.macro_events({'fed':rss('Wed, 21 Oct 2026 12:00:00 GMT')},NOW)),1)
        self.assertEqual(us.macro_events({'fed':rss('Tue, 20 Oct 2026 12:00:00 GMT')},NOW),[])
        self.assertEqual(us.macro_events({'fed':rss('Wed, 21 Oct 2026 13:04:00 GMT')},NOW),[])

    def test_unrelated_fed_bank_approval_is_not_macro_context(self):
        raw=b'<rss><channel><item><title>Federal Reserve Board approves bank merger</title><link>https://www.federalreserve.gov/newsevents/x.htm</link><pubDate>Wed, 21 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(us.macro_events({'fed':raw},NOW),[])


class ReportTests(unittest.TestCase):
    def test_short_specific_report_and_delay(self):
        data=snapshot();message=us.render(data,NOW,SLOT)
        self.assertIn('PREOPEN',message);self.assertIn('Nasdaq Composite: N/A',message)
        self.assertIn('BTC dominancia 59.60%',message)
        self.assertIn('Divergencia',message);self.assertIn('Nejde o dôkaz toku kapitálu',message)
        self.assertNotIn('SKÔR RAST',message);self.assertNotIn('Pravdepodobnosť',message)
        self.assertLess(len(message),3800)
        delayed=NOW+timedelta(minutes=33);us.refresh(data,delayed)
        message=us.render(data,delayed,SLOT,collected_seconds=5)
        self.assertIn('OPENING',message);self.assertIn('33.0 min',message)
        self.assertIn('zber 5.0s',message)

    def test_dominance_difference_is_since_dated_report_not_flows(self):
        old={'at':(NOW-timedelta(days=1)).isoformat(),'dominance':59.0}
        message=us.render(snapshot(),NOW,SLOT,old)
        self.assertIn('+0.60 p. b. od',message)
        old['at']=(NOW-timedelta(days=3)).isoformat()
        self.assertNotIn('+0.60 p. b. od',us.render(snapshot(),NOW,SLOT,old))

    def test_all_unavailable_still_produces_short_report(self):
        api=MagicMock();api.http_json.side_effect=OSError('offline')
        api.PORTFOLIO=main.PORTFOLIO
        with patch('us_context.report.fundamentals.fetch',side_effect=OSError('offline')):
            data=us.collect(api,NOW)
        self.assertTrue(all(q['price'] is None for q in data['quotes'].values()))
        self.assertIn('N/A',us.render(data,NOW,SLOT))
        self.assertEqual(data['macro'],[])
        for call in api.http_json.call_args_list:
            self.assertEqual(call.kwargs['retries'],1);self.assertEqual(call.kwargs['timeout'],6)
        api.groq_call.assert_not_called()

    def test_send_failure_does_not_mark_slot_and_success_does_not_change_trades(self):
        api=MagicMock();state={'last_actions':{'SOL':{'action':'HOLD'}},'last_analysis':{'coins':[{'symbol':'SOL','action':'HOLD'}]}}
        api.load_state.return_value=state;api.iso_now.return_value=NOW.isoformat()
        old=copy.deepcopy(state)
        with patch('us_context.report.collect',return_value=snapshot()):
            api.telegram_send_long.side_effect=RuntimeError('delivery failed')
            with self.assertRaises(RuntimeError):us.run(api,SLOT)
            self.assertEqual(state['last_actions'],old['last_actions'])
            self.assertNotIn('last_us_slot',state)
            self.assertEqual(state['delivery_v111'][SLOT]['status'],'uncertain')
            calls=api.telegram_send_long.call_count
            us.run(api,SLOT)
            self.assertEqual(api.telegram_send_long.call_count,calls)
            # Explicit operator-reviewed retry after checking the target chat.
            state['delivery_v111'].pop(SLOT)
            api.telegram_send_long.side_effect=None
            us.run(api,SLOT)
        self.assertEqual(state['last_actions'],old['last_actions'])
        self.assertEqual(state['last_analysis'],old['last_analysis'])
        self.assertEqual(state['last_us_slot'],SLOT)
        self.assertIn('sent_at',state['us_outlook_timing'])
        calls=api.telegram_send_long.call_count
        us.run(api,SLOT)
        self.assertEqual(calls,api.telegram_send_long.call_count)
        api.groq_call.assert_not_called()

    def test_timing_separates_job_preparation_collection_and_send(self):
        api=MagicMock();state={};api.load_state.return_value=state
        api.VERSION='10.6';api.iso_now.return_value=NOW.isoformat()
        data=snapshot()
        with patch('us_context.report.collect',return_value=data),patch('us_context.report.datetime',wraps=datetime) as clock,\
             patch('us_context.report.time.monotonic',side_effect=[100.,106.]),\
             patch.dict(os.environ,{'BOT_JOB_STARTED_AT':(NOW+timedelta(seconds=5)).isoformat()}):
            clock.now.side_effect=[NOW+timedelta(seconds=20),NOW+timedelta(seconds=26),NOW+timedelta(seconds=27)]
            us.run(api,SLOT)
        timing=state['us_outlook_timing']
        self.assertEqual(timing['schedule_to_job_seconds'],5)
        self.assertEqual(timing['job_to_outlook_seconds'],15)
        self.assertEqual(timing['collect_seconds'],6)
        self.assertEqual(timing['send_seconds'],1)
        self.assertEqual(timing['delay_seconds'],27)
        self.assertEqual(state['us_market_previous']['dominance'],59.6)

    def test_main_preserves_morning_evening_monitor_and_usa_needs_no_ai_key(self):
        with patch.object(main,'TELEGRAM_TOKEN','fixture'),patch.object(main,'TELEGRAM_CHAT_ID','fixture'), \
             patch.object(main,'GROQ_API_KEY',''),patch.object(main,'is_main_analysis_time') as due, \
             patch.object(main,'get_main_analysis_slot') as slot,patch.object(main,'load_state',return_value={}), \
             patch('v11.runtime.telegram_updates'),patch('v11.runtime.run_outlook') as outlook, \
             patch('v11.runtime.run_analysis') as analysis,patch('v11.runtime.run_monitor') as monitor:
            due.return_value=(True,'BRATISLAVA_15:00');slot.return_value=SLOT
            main.main();outlook.assert_called_once_with(main,SLOT)
            analysis.assert_not_called();monitor.assert_not_called()
            for hour in (7,20):
                due.return_value=(True,'BRATISLAVA');slot.return_value=f'BRATISLAVA_2026-10-21_{hour:02}:00'
                main.main();self.assertEqual(analysis.call_args.args[2],slot.return_value)
            due.return_value=(False,'SAFETY_MONITOR');slot.return_value=None
            main.main();monitor.assert_called_once_with(main)

    def test_legacy_entrypoint_delegates_to_same_implementation(self):
        with patch('us_context.report.run') as run:
            main.run_us_open_outlook(SLOT)
            run.assert_called_once_with(main,SLOT)

if __name__=='__main__':unittest.main()
