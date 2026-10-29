"""Main-based integration tests; review-only V11 entrypoint replacement is excluded."""
import os,socket,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(BOT_DISABLE_TELEGRAM='1',TELEGRAM_TOKEN='',TELEGRAM_CHAT_ID='',GROQ_API_KEY='')
MODULES=['test_briefing','test_fundamentals','test_fundamental_analysis','test_trial_pilot','test_artifact_privacy','test_integration_candidate','test_compact_report','test_us_outlook','test_us_live_integration','test_manual_v111','test_analyst_v112','test_prediction_shadow','test_prediction_research','test_production_v2','test_fundamental_extensions','test_report_quality','test_us_brief']
def blocked(*a,**k):raise RuntimeError('Unmocked network forbidden')
if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
    with patch.object(socket.socket,'connect',blocked),patch.object(socket.socket,'connect_ex',blocked):
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
