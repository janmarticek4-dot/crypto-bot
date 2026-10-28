"""Own-repository PUBLIC research CAS only; no portfolio or delivery state."""
import base64,json,os,re,urllib.request,urllib.error
from v11 import prediction_journal as journal
from v11.state_policy import require_public_data
PATH='public-analytics/prediction-shadow.json'

class PublicPredictionStore:
    def __init__(self):
        self.repo=os.environ['GITHUB_REPOSITORY'];self.token=os.environ['GH_TOKEN'];self.sha=None
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',self.repo):raise ValueError('Invalid own repository')
    def request(self,method,path,body=None):
        req=urllib.request.Request('https://api.github.com/repos/'+self.repo+'/'+path,method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'crypto-bot-public-paper'})
        with urllib.request.urlopen(req,timeout=12) as response:
            raw=response.read(24_000_001)
        if len(raw)>24_000_000:raise ValueError('Public research object oversized')
        return json.loads(raw)
    def read(self):
        try:value=self.request('GET','contents/'+PATH+'?ref=main')
        except urllib.error.HTTPError as e:
            if e.code==404:self.sha=None;return journal.load([])
            raise
        self.sha=value['sha'];encoded=value.get('content')
        if value.get('encoding')!='base64':encoded=self.request('GET','git/blobs/'+self.sha)['content']
        return journal.load(json.loads(base64.b64decode(encoded)))
    def append(self,records,now_ms):
        for attempt in range(3):
            value=self.read();value=journal.update(value,records,[],{},now_ms);require_public_data(value)
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            body=dict(message='Record public report predictions [skip ci]',branch='main',content=base64.b64encode(raw).decode())
            if self.sha:body['sha']=self.sha
            try:return self.request('PUT','contents/'+PATH,body)
            except urllib.error.HTTPError as e:
                if e.code!=409 or attempt==2:raise
        raise RuntimeError('Public paper CAS failed')
