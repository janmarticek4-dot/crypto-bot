"""Read-only candidate source audit: no Telegram, holdings, AI, or state writes."""
import concurrent.futures,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.fundamental_sources_shadow import Probe
from v11 import fundamentals as f
from v11.state_policy import require_public_data

CANDIDATES=[
 dict(id='ondo_blog_alt',url='https://ondo.finance/blog/rss.xml',official=True,symbol='ONDO',coverage=['project']),
 dict(id='ondo_blog_www',url='https://www.ondo.finance/blog/rss.xml',official=True,symbol='ONDO',coverage=['project']),
 dict(id='sol_news',url='https://solana.com/news/rss.xml',official=True,symbol='SOL',coverage=['project']),
 dict(id='sol_status',url='https://status.solana.com/history.rss',official=True,symbol='SOL',coverage=['hack'],kind='network_status_notice'),
 dict(id='fet_news',url='https://fetch.ai/blog/rss.xml',official=True,symbol='FET',coverage=['project']),
 dict(id='tao_news',url='https://blog.bittensor.com/rss/',official=True,symbol='TAO',coverage=['project']),
 dict(id='render_news',url='https://rendernetwork.com/rss.xml',official=True,symbol='RENDER',coverage=['project']),
 dict(id='decrypt',url='https://decrypt.co/feed',official=False,coverage=['project','regulation','hack']),
 dict(id='theblock',url='https://www.theblock.co/rss.xml',official=False,coverage=['project','regulation','hack']),
 dict(id='council',url='https://www.consilium.europa.eu/en/press/press-releases/rss/',official=True,coverage=['geopolitics','regulation']),
 dict(id='bea_calendar',url='https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics',official=True,publisher_host='bea.gov',coverage=['PCE','GDP'],format='ics'),
 dict(id='aave_v3_tvl',url='https://api.llama.fi/protocol/aave-v3',symbol='AAVE'),
]

def run():
 now=datetime.now(timezone.utc);probe=Probe(now)
 all_sources=f.SOURCES+[v for values in f.FALLBACKS.values() for v in values]+CANDIDATES
 seen=set();sources=[]
 for source in all_sources:
  if source['url'] not in seen:sources.append(source);seen.add(source['url'])
 def one(source):
  try:probe.fetch(source)
  except Exception:pass
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(one,sources))
 rows=sorted(probe.rows,key=lambda r:r['source']);require_public_data(rows)
 out=Path('shadow-output/source-repair');out.mkdir(parents=True,exist_ok=True)
 (out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 report=['# Source repair candidates',now.isoformat(),'No Telegram or private state access. Candidate success is not production activation.','', '| Source | Status | HTTP / policy | Published | Relevant items |','|---|---|---|---|---|']
 for r in rows:
  report.append('| '+' | '.join(str(x) for x in (r['source'],r['status'],r.get('http_status') or r.get('error_code') or r.get('error_type') or '',r.get('publication_at') or 'N/A',r.get('relevant_items','N/A')))+' |')
  minimal={k:r.get(k) for k in ('source','status','http_status','error_code','error_layer','publication_at','relevant_items','bytes')}
  print('::notice title=Source repair::'+json.dumps(minimal))
 (out/'REPORT.md').write_text('\n'.join(report)+'\n')

if __name__=='__main__':run()
