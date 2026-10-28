"""Public endpoint discovery, not production evidence or a trading signal."""
import concurrent.futures,json,re,sys,urllib.request,urllib.error
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.state_policy import require_public_data

class Tables(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None;self.ignore=0;self.text=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':self.links.extend(v for k,v in attrs if k=='href' and re.search(r'token|ondo|allocation|vesting|emission',v,re.I))
  if tag in ('script','style'):self.ignore+=1
  if tag=='tr':self.row=[]
  if tag in ('td','th'):self.cell=[]
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.ignore=max(0,self.ignore-1)
  if tag in ('td','th') and self.cell is not None:
   if self.row is not None:self.row.append(re.sub(r'\s+',' ',' '.join(self.cell)).strip())
   self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
 def handle_data(self,text):
  if not self.ignore:
   self.text.append(text)
   if self.cell is not None:self.cell.append(text)

SOURCES=[
 ('btc_flows','https://farside.co.uk/btc/',None),('eth_flows','https://farside.co.uk/eth/',None),
 ('btc_flows_alt','https://farside.co.uk/bitcoin-etf-flow-all-data/',None),
 ('eth_flows_alt','https://farside.co.uk/ethereum-etf-flow-all-data/',None),
 ('calendar_forecasts','https://nfs.faireconomy.media/ff_calendar_thisweek.json',None),
 ('calendar_next','https://nfs.faireconomy.media/ff_calendar_nextweek.json',None),
 ('protocol_names','https://api.llama.fi/protocols',None),
 ('sol_dex_volume','https://api.llama.fi/overview/dexs/Solana?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true',None),
 ('sol_stablecoins','https://stablecoins.llama.fi/stablecoincharts/Solana',None),
 ('sol_supply','https://api.mainnet-beta.solana.com',dict(jsonrpc='2.0',id=1,method='getSupply',params=[{'commitment':'finalized','excludeNonCirculatingAccountsList':True}])),
 ('sol_inflation','https://api.mainnet-beta.solana.com',dict(jsonrpc='2.0',id=1,method='getInflationRate')),
 ('fet_supply','https://rest-fetchhub.fetch.ai/cosmos/bank/v1beta1/supply/afet',None),
 ('fet_inflation','https://rest-fetchhub.fetch.ai/cosmos/mint/v1beta1/inflation',None),
 ('ondo_docs','https://docs.ondo.finance/',None),
 ('ondo_foundation','https://ondo.foundation/',None),
 ('ondo_public_unlocks','https://tokenomist.ai/ondo-finance',None),
 ('ondo_yield_tvl','https://api.llama.fi/protocol/ondo-yield-assets',None),
 ('ondo_markets_tvl','https://api.llama.fi/protocol/ondo-global-markets',None),
 ('tao_dtao_tvl','https://api.llama.fi/protocol/bittensor-dtao',None),
 ('render_fees','https://api.llama.fi/summary/fees/render-network-bme?dataType=dailyFees',None),
 ('ondo_tokenomics','https://docs.ondo.foundation/tokenomics',None),
 ('tao_emissions_docs','https://docs.learnbittensor.org/learn/emissions',None),
 ('render_tokenomics','https://know.rendernetwork.com/basics/render-network-tokenomics',None),
]+[(s+'_unlocks','https://api.llama.fi/emissions/'+slug,None) for s,slug in [('ondo','ondo-finance'),('sol','solana'),('tao','bittensor'),('fet','fetch-ai'),('aave','aave'),('render','render')]]

def one(source):
 name,url,body=source;out=dict(source=name,url=url,retrieved_at=datetime.now(timezone.utc).isoformat())
 try:
  req=urllib.request.Request(url,data=json.dumps(body).encode() if body else None,headers={'User-Agent':'CryptoBotResearch/11.2 public financial source reader','Accept':'application/json,text/html','Content-Type':'application/json'} if body else {'User-Agent':'CryptoBotResearch/11.2 public financial source reader'})
  with urllib.request.urlopen(req,timeout=12) as response:
   if not response.geturl().startswith('https://'):raise ValueError('HTTPS required')
   raw=response.read(12000001)
   if len(raw)>12000000:raise ValueError('Size limit')
   out.update(http=response.status,bytes=len(raw),final_url=response.geturl())
  try:
   data=json.loads(raw);out['format']='JSON';out['schema']=list(data)[:35] if isinstance(data,dict) else 'list'
   if name=='protocol_names':out['sample']=[{k:r.get(k) for k in ('name','slug','parentProtocol','category','tvl')} for r in data if re.search(r'ondo|aave|bittensor|render|fetch.ai',r.get('name',''),re.I)][:30]
   elif name.startswith('calendar'):out['sample']=[r for r in data if r.get('country')=='USD'][:18]
   elif isinstance(data,dict):out['sample']={k:v[-2:] if isinstance(v,list) else v for k,v in data.items() if k in ('result','error','amount','inflation','totalDataChart','total24h','name','events','sources','tvl','methodology','description')}
   elif isinstance(data,list):out['sample']=data[-2:]
   out['status']='RETRIEVED_NOT_VALIDATED'
  except (json.JSONDecodeError,UnicodeDecodeError):
   page=Tables();page.feed(raw.decode(errors='replace'));text=re.sub(r'\s+',' ',' '.join(page.text));out['format']='HTML'
   dated=[r for r in page.rows if any(re.search(r'\d{1,2}\s+[A-Z][a-z]{2}\s+20\d{2}',c) for c in r)]
   out['table_headers']=[r for r in page.rows if any(re.search(r'total|ibit|fbtc|eth[a-z]',c,re.I) for c in r)][:3]
   out['links']=list(dict.fromkeys(page.links))[:25];out['dated_rows']=dated[-3:];out['text_start']=text[:420]
   out['relevant_excerpts']=[text[max(0,m.start()-100):m.end()+220] for m in list(re.finditer(r'US\$|US\$m|million|2027|unlock|vesting|emission|January|10 billion',text,re.I))[:6]]
   out['status']='RETRIEVED_NOT_VALIDATED'
 except Exception as exc:out.update(status='UNAVAILABLE',error=type(exc).__name__,http=getattr(exc,'code',None))
 return out

def run():
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:rows=list(pool.map(one,SOURCES))
 require_public_data(rows);out=Path('shadow-output/source-repair');out.mkdir(parents=True,exist_ok=True)
 (out/'extended-candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print('::notice title=Extended source candidates::'+json.dumps([[r['source'],r['status'],r.get('http'),r.get('format')] for r in rows],separators=(',',':')))
 for group in [('details',lambda n:n in ('ondo_docs','ondo_foundation','ondo_public_unlocks','ondo_yield_tvl','ondo_markets_tvl','tao_dtao_tvl','render_fees','tao_emissions_docs','sol_inflation','fet_inflation')),('flows',lambda n:'flows' in n),('calendar',lambda n:n.startswith('calendar')),('project',lambda n:n in ('protocol_names','sol_dex_volume','sol_stablecoins','sol_supply','sol_inflation','fet_supply','fet_inflation')),('unlocks',lambda n:'unlocks' in n or 'tokenomics' in n or 'emissions_docs' in n)]:
  selected=[{k:r.get(k) for k in ('source','schema','sample','table_headers','dated_rows','relevant_excerpts','links')} for r in rows if group[1](r['source']) and r['status']!='UNAVAILABLE']
  value=json.dumps(selected,ensure_ascii=False,separators=(',',':'))
  # Chunk independent records so public GitHub annotation truncation cannot hide them.
  for i,item in enumerate(selected):
   print('::notice title=Extended '+group[0]+' '+str(i)+'::'+json.dumps(item,ensure_ascii=False,separators=(',',':'))[:3900])

if __name__=='__main__':run()
