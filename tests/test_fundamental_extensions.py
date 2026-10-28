"""Synthetic measurements only: no real portfolio, Telegram or live HTTP."""
import copy,json,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from v11 import fundamental_extensions as x,fundamentals,integrated_report,analyst
from tests.test_analyst_v112 import sample,model,INVENTORY

NOW=datetime(2026,10,28,21,tzinfo=timezone.utc)

def table(rows,title='Bitcoin',unit='US$m'):
    return ('<h1>'+title+' ETF Flow ('+unit+')</h1><table><tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>Total</th></tr>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in rows)+'</table>').encode()

def forecast(**kwargs):
    row=dict(title='Advance GDP q/q',country='USD',date='2026-10-29T08:30:00-04:00',forecast='2.1%',previous='1.1%',impact='High')
    row.update(kwargs);return row

class ExtendedFundamentalTests(unittest.TestCase):
    def test_complete_flow_and_missing_latest_not_zero(self):
        out=x.parse_flows(table([['26 Oct 2026','20.0','(10.0)','10.0'],['27 Oct 2026','30.0','0.0','30.0'],['28 Oct 2026','-','0.0','0.0']]),'BTC',NOW)
        self.assertEqual(out['date'],'2026-10-27');self.assertEqual(out['net_flow_usd'],30000000)
        self.assertEqual(out['latest_incomplete_date'],'2026-10-28');self.assertEqual(out['previous_net_flow_usd'],10000000)
        self.assertIsNone(out['published_at']);self.assertFalse(out['provider_audited'])
    def test_explicit_zero_is_a_real_flow_zero(self):
        self.assertEqual(x.parse_flows(table([['27 Oct 2026','0.0','0.0','0.0']]),'BTC',NOW)['net_flow_usd'],0)
    def test_negative_parentheses(self):
        self.assertEqual(x.parse_flows(table([['27 Oct 2026','(3.2)','1.2','(2.0)']]),'BTC',NOW)['net_flow_usd'],-2000000)
    def test_malformed_numeric_cells_not_silently_reinterpreted(self):
        for text in ('(123','123)','1,23,4','(-3.2)','NaN','∞'):
            with self.assertRaises(ValueError):x.flow_number(text)
    def test_flow_total_mismatch_rejected(self):
        with self.assertRaises(ValueError):x.parse_flows(table([['27 Oct 2026','3','4','70']]),'BTC',NOW)
    def test_misaligned_table_cannot_be_a_complete_zero_row(self):
        with self.assertRaises(ValueError):x.parse_flows(table([['27 Oct 2026','0.0','0.0','0.0','0.0']]),'BTC',NOW)
    def test_flow_unit_required(self):
        with self.assertRaises(ValueError):x.parse_flows(table([['27 Oct 2026','3','4','7']],unit='unknown'),'BTC',NOW)
    def test_flow_asset_identity_required(self):
        with self.assertRaises(ValueError):x.parse_flows(table([['27 Oct 2026','3','4','7']]),'ETH',NOW)
    def test_stale_and_future_flow_dates_rejected(self):
        for date in ('01 Oct 2026','29 Oct 2026'):
            with self.assertRaises(ValueError):x.parse_flows(table([[date,'3','4','7']]),'BTC',NOW)
    def test_challenge_page_not_a_flow_source(self):
        with self.assertRaises(ValueError):x.parse_flows(b'<html>challenge</html>','BTC',NOW)
    def test_conflicting_flow_duplicate_rejected(self):
        with self.assertRaises(ValueError):x.parse_flows(table([['27 Oct 2026','3','4','7'],['27 Oct 2026','4','4','8']]),'BTC',NOW)
    def test_forecasts_are_pre_event_and_not_actual_results(self):
        rows=x.parse_forecasts(json.dumps([forecast(),forecast(date='2026-10-27T08:30:00-04:00')]).encode(),NOW)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['event_at'],'2026-10-29T12:30:00+00:00')
        self.assertIsNone(rows[0]['actual']);self.assertIsNone(rows[0]['surprise']);self.assertIsNone(rows[0]['published_at'])
        self.assertEqual(rows[0]['forecast_captured_at'],NOW.isoformat())
    def test_future_calendar_dst(self):
        out=x.parse_forecasts(json.dumps([forecast(date='2026-11-02T08:30:00-05:00')]).encode(),NOW)
        self.assertEqual(out[0]['event_at'],'2026-11-02T13:30:00+00:00')
    def test_unknown_timezone_or_forecast_not_invented(self):
        for changes in (dict(date='2026-10-29T08:30:00'),dict(forecast='N/A'),dict(forecast=''),dict(forecast='60 percent likely'),dict(country='EUR')):
            self.assertEqual(x.parse_forecasts(json.dumps([forecast(**changes)]).encode(),NOW),[])
    def test_conflicting_forecast_rejected(self):
        with self.assertRaises(ValueError):x.parse_forecasts(json.dumps([forecast(),forecast(forecast='8%')]).encode(),NOW)
    def test_official_calendar_conflict_excluded_from_text(self):
        value=dict(consensus=x.parse_forecasts(json.dumps([forecast()]).encode(),NOW))
        x.verify_calendar(value,[dict(scheduled=True,categories=['GDP'],event_at='2026-10-30T12:30:00+00:00')])
        self.assertEqual(value['consensus'][0]['official_schedule'],'CONFLICT')
        self.assertNotIn('GDP',' '.join(x.lines(value,NOW)))
    def test_official_calendar_match(self):
        value=dict(consensus=x.parse_forecasts(json.dumps([forecast()]).encode(),NOW))
        x.verify_calendar(value,[dict(scheduled=True,categories=['GDP'],event_at='2026-10-29T12:30:00+00:00')])
        self.assertEqual(value['consensus'][0]['official_schedule'],'MATCHED')
    def test_unlock_is_date_only_provider_claim(self):
        raw=b'<p>When is the next Ondo unlock? The next unlock for Ondo is scheduled for January 18, 2027.</p>'
        out=x.parse_unlock(raw,'ONDO',NOW)
        self.assertEqual(out['event_date'],'2027-01-18');self.assertIsNone(out['event_at']);self.assertIsNone(out['amount']);self.assertIsNone(out['time_zone'])
        self.assertIn('NOT_ONCHAIN_CONFIRMED',out['status'])
    def test_other_token_advert_cannot_create_unlock(self):
        with self.assertRaises(ValueError):x.parse_unlock(b'When is the next Arbitrum unlock? The next unlock for Arbitrum is scheduled for November 18, 2026.','ONDO',NOW)
    def test_old_unlock_does_not_become_future_event(self):
        with self.assertRaises(ValueError):x.parse_unlock(b'When is the next Ondo unlock? The next unlock for Ondo is scheduled for October 01, 2026.','ONDO',NOW)
    def test_no_date_does_not_mean_fully_unlocked(self):
        with self.assertRaises(ValueError):x.parse_unlock(b'When is the next Aave unlock? Aave is fully unlocked. 96.48% has been unlocked.','AAVE',NOW)
    def test_stablecoin_supply_uses_usd_not_native_peg_totals(self):
        raw=json.dumps([dict(date=int((NOW-timedelta(hours=24)).timestamp()),totalCirculating={'peggedUSD':999999},totalCirculatingUSD={'peggedUSD':100,'peggedEUR':20})]).encode()
        self.assertEqual(x.parse_stablecoins(raw,NOW)['value'],120)
    def test_stablecoin_series_stale_rejected(self):
        with self.assertRaises(ValueError):x.parse_stablecoins(json.dumps([dict(date=0,totalCirculatingUSD={'peggedUSD':100})]).encode(),NOW)
    def test_inflation_fraction_to_percentage(self):
        self.assertEqual(x.parse_inflation(b'{"inflation":"0.03"}','FET',NOW)['value'],3)
    def test_invalid_inflation(self):
        for val in ('NaN','inf','-0.1','2'):
            with self.assertRaises(ValueError):x.parse_inflation(json.dumps(dict(inflation=val)).encode(),'FET',NOW)
    def test_supply_reconciles_finalized_public_counts(self):
        raw=json.dumps(dict(jsonrpc='2.0',result=dict(context=dict(slot=10),value=dict(total=10000000000,circulating=9000000000,nonCirculating=1000000000)))).encode()
        self.assertEqual(x.parse_supply(raw,NOW)['value'],9)
        data=json.loads(raw);data['result']['value']['total']+=1
        with self.assertRaises(ValueError):x.parse_supply(json.dumps(data).encode(),NOW)
    def test_rpc_error_not_zero_supply(self):
        with self.assertRaises(ValueError):x.parse_supply(b'{"jsonrpc":"2.0","error":{"code":-32601}}',NOW)
    def test_only_safe_readonly_rpc_methods_allowed(self):
        for source in (dict(url=x.RPC,rpc_method='sendTransaction'),dict(url='https://example.org',rpc_method='getSupply')):
            with self.assertRaises(fundamentals.SourcePolicyError):fundamentals.fetch(source)
    def test_missing_or_stale_tokenomics_not_dilution_claim(self):
        for c in ({},dict(circulating_supply=50,total_supply=100,metadata_at=(NOW-timedelta(hours=1)).isoformat()),dict(circulating_supply=150,total_supply=100,metadata_at=NOW.isoformat())):
            self.assertIsNone(x.tokenomics(c,NOW))
        self.assertEqual(x.tokenomics(dict(circulating_supply=50,total_supply=100,metadata_at=NOW.isoformat()),NOW)['circulating_percent'],50)
    def test_all_source_failure_returns_na_not_fabricated_metrics(self):
        def missing(source):raise OSError('synthetic outage')
        value=x.collect(NOW,missing)
        for key in ('etf_flows','consensus','unlocks','project_metrics'):self.assertFalse(value[key])
        self.assertTrue(all(row['status']=='N/A' for row in value['sources']))
    def test_extensions_do_not_change_actions_or_inventory(self):
        snap=sample();m=model(snap);m['_current_fundamentals']={'extensions':dict(consensus=x.parse_forecasts(json.dumps([forecast()]).encode(),NOW))}
        before=copy.deepcopy(INVENTORY);baseline=analyst.final_text(m,snap,NOW,'evening',INVENTORY)
        text=integrated_report.render(m,snap,NOW,'evening',INVENTORY)
        for line in baseline.splitlines():
            if any(line.startswith(s+' ') for s in analyst.COINS):self.assertIn(line,text)
        self.assertEqual(INVENTORY,before);self.assertNotIn('https://',text)
