import unittest
from datetime import datetime,timezone
from v11 import integration,compact_report
from tests import test_integration_candidate as fixtures
import main as legacy

class CompactTests(unittest.TestCase):
    def test_parity_and_diagnostics_separation(self):
        snap=fixtures.IntegrationTests().data();now=datetime.now(timezone.utc)
        short,quotes,ev=integration.render(legacy,snap,{},now,'morning',{})
        full,q2,e2=integration.render_detailed(legacy,snap,{},now,'morning',{})
        self.assertEqual(ev,e2);self.assertEqual(quotes,q2)
        self.assertNotIn('EMA20/50',short);self.assertIn('EMA20/50',full)
        self.assertLessEqual(len(short),3000)
        self.assertIn('WAIT nie',compact_report.reason(dict(action='WAIT',price=1)))
    def test_broken_levels_are_labelled_not_changed(self):
        e=dict(price=100,support=110,resistance=90);before=dict(e)
        text=compact_report.levels(e,str)
        self.assertIn('Prerazený support 110',text);self.assertIn('prekonaná rezistencia 90',text)
        self.assertEqual(e,before)
    def test_missing_values_remain_na(self):
        self.assertEqual(compact_report.levels({},legacy.format_price),'S N/A / R N/A')
    def test_unknown_incident_exposure_not_attributed_to_six_coins(self):
        now=datetime.now(timezone.utc)
        event=dict(id='synthetic',title='Unknown wallet security hack',source='test',url='https://example.org',published_at=now.isoformat(),retrieved_at=now.isoformat(),categories=['hack'])
        text,*_=integration.render(legacy,fixtures.IntegrationTests().data(),dict(events=[event]),now,'morning',{})
        self.assertNotIn(event['title'],text)
    def test_no_fake_evening_reference(self):
        text,*_=integration.render(legacy,fixtures.IntegrationTests().data(),{},datetime.now(timezone.utc),'evening',{})
        self.assertIn('chýba overený ranný snapshot',text)
    def test_scheduled_event_date_and_source_without_invented_hour(self):
        now=datetime(2026,10,27,12,tzinfo=timezone.utc)
        event=dict(scheduled=True,event_date='2026-10-28',title='FOMC decision',url='https://www.federalreserve.gov/calendar',categories=['Fed'])
        text,*_=integration.render(legacy,fixtures.IntegrationTests().data(),{'events':[event]},now,'morning',{})
        self.assertIn('2026-10-28 čas N/A',text);self.assertIn(event['url'],text)
    def test_economics_comparison_is_not_a_capital_flow(self):
        now=datetime.now(timezone.utc)
        fund={'project_economics':{'observations':{'AAVE':{'fees':dict(value=110,previous_value=100,period='2026-10-26',previous_period='2026-10-25')}}}}
        text,*_=integration.render(legacy,fixtures.IntegrationTests().data(),fund,now,'morning',{})
        self.assertIn('AAVE poplatky +10.0%',text);self.assertIn('Nie je to výnos tokenu ani čistý tok',text)
