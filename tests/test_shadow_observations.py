import copy
from datetime import datetime,timedelta,timezone
import unittest
from scripts import v111_compare_observations as o
from v11.shadow_pair import fingerprint
from tests import test_shadow_pair as fixtures


def observation(at):
    snap=fixtures.sample(at)
    for coin in snap['coins'].values():
        coin['raw']['1h']=[dict(timestamp=int((at-timedelta(hours=1)).timestamp()*1000),close=coin['price'])]
    return dict(snapshot=snap,observed_at=at.isoformat(),fingerprint=fingerprint(snap),actions={s:'WAIT' for s in o.SYMBOLS})


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.first_at=datetime(2026,10,22,10,tzinfo=timezone.utc)
        self.second_at=self.first_at+timedelta(hours=1)
        self.first=observation(self.first_at);self.second=observation(self.second_at)

    def test_real_comparison_math_and_original_actions_preserved(self):
        self.second['snapshot']['coins']['SOL'].update(price=110.,market_cap=1200.,volume_24h=150.)
        self.second['fingerprint']=fingerprint(self.second['snapshot'])
        self.second['actions']['SOL']='HOLD'
        result=o.compare(self.first,self.second)
        row=next(r for r in result['rows'] if r['symbol']=='SOL')
        self.assertAlmostEqual(row['price_pct'],10.)
        self.assertAlmostEqual(row['market_cap_pct'],20.)
        self.assertAlmostEqual(row['volume24h_pct'],50.)
        self.assertEqual((row['action_first'],row['action_second']),('WAIT','HOLD'))
        self.assertTrue(result['verified'])
        self.assertFalse(result['morning_evening_slot_test'])

    def test_reused_source_even_with_later_timestamp_refused(self):
        other=copy.deepcopy(self.first);other['observed_at']=self.second_at.isoformat();other['snapshot']['at']=self.second_at.timestamp()
        with self.assertRaisesRegex(ValueError,'Reused'):o.compare(self.first,other)

    def test_price_change_without_provider_clock_advance_not_enough(self):
        other=copy.deepcopy(self.first);other['observed_at']=self.second_at.isoformat();other['snapshot']['at']=self.second_at.timestamp()
        other['snapshot']['coins']['SOL']['price']=111.
        other['fingerprint']=fingerprint(other['snapshot'])
        with self.assertRaisesRegex(ValueError,'provider timestamp'):o.compare(self.first,other)

    def test_too_close_or_reversed_time_refused(self):
        for at in (self.first_at+timedelta(minutes=2),self.first_at-timedelta(hours=1)):
            with self.assertRaisesRegex(ValueError,'15minutes'):o.compare(self.first,observation(at))

    def test_future_candle_in_source_proof_refused(self):
        self.second['snapshot']['coins']['SOL']['raw']['1h'][-1]['timestamp']=int(self.second_at.timestamp()*1000)
        self.second['fingerprint']=fingerprint(self.second['snapshot'])
        with self.assertRaisesRegex(ValueError,'Future'):o.compare(self.first,self.second)

    def test_missing_capitalization_remains_na(self):
        self.second['snapshot']['coins']['SOL']['market_cap']=None
        self.second['fingerprint']=fingerprint(self.second['snapshot'])
        result=o.compare(self.first,self.second)
        self.assertIsNone(next(r for r in result['rows'] if r['symbol']=='SOL')['market_cap_pct'])

    def test_same_4h_trend_can_be_valid_with_new_hourly_observation(self):
        result=o.compare(self.first,self.second)
        self.assertTrue(all(not r['trend_changed'] for r in result['rows']))
        self.assertTrue(all(r['source_proof']['second_closed_1h']>r['source_proof']['first_closed_1h'] for r in result['rows']))

    def test_no_arbitrary_private_input_paths(self):
        with self.assertRaises(ValueError):o.load_bundle(o.ROOT)
