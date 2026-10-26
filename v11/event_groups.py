"""Conservative event grouping. Similar headlines are not independent confirmation."""
import re
from datetime import datetime

STOP=set('a an the at on in of for to and as with after says said new update interest'.split())

def tokens(title):
    text=title.lower().replace('federal reserve','fed')
    for pattern,replacement in [(r'\b(leaves|keeps|holds)\b','hold'),(r'\brates\b','rate'),(r'\bsteady\b','unchanged')]:text=re.sub(pattern,replacement,text)
    return set(re.findall(r'\w+',text))-STOP


def same_event(a,b):
    if set(a['categories'])!=set(b['categories']) or set(a['symbols'])!=set(b['symbols']):return False
    if abs((datetime.fromisoformat(a['published_at'])-datetime.fromisoformat(b['published_at'])).total_seconds())>86400:return False
    if re.findall(r'\d+(?:[.,]\d+)?',a['title'])!=re.findall(r'\d+(?:[.,]\d+)?',b['title']):return False
    # Do not collapse differing institutions or process stages into one claim.
    for pattern in (r'\bfed\b|federal reserve',r'\becb\b',r'\bboj\b',r'\bcpi\b',r'\bpce\b',r'proposal|proposes',r'approved|passes',r'denies|denied',r'confirmed|confirms'):
        if bool(re.search(pattern,a['title'],re.I))!=bool(re.search(pattern,b['title'],re.I)):return False
    x,y=tokens(a['title']),tokens(b['title'])
    return x==y or (len(x&y)>=4 and len(x&y)/max(1,len(x|y))>=0.65)


def group(events):
    groups=[]
    for event in events:
        target=next((e for e in groups if same_event(e,event)),None)
        citation={k:event[k] for k in ('id','title','source','url','published_at','retrieved_at')}
        if target is None:
            target=dict(event,citations=[citation],member_ids=[event['id']]);groups.append(target)
        elif event['id'] not in target['member_ids']:
            target['citations'].append(citation);target['member_ids'].append(event['id'])
    return groups
