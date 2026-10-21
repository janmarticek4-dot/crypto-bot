"""AI can select existing deterministic explanations, never author market facts."""
import hashlib
import json
import time


def explain(api, state, evaluations):
    facts={s:dict(action=e['action'],reasons=e['reasons'][:8],confidence=e['confidence']) for s,e in evaluations.items()}
    serialized=json.dumps(facts,sort_keys=True,ensure_ascii=False)
    key=hashlib.sha256(serialized.encode()).hexdigest()
    cache=state.setdefault('ai_v11',{})
    if cache.get('key')==key and time.time()-cache.get('at',0)<12*3600:
        return cache['result']
    if time.time()-cache.get('failed_at',0)<2*3600 or not api.GROQ_API_KEY:
        return dict(available=False, selections={})
    prompt=('Vyber najviac dva existujúce dôvody pre každý symbol. Vráť iba JSON '
            '{"selections":{"SOL":[0,1]}}. Indexy od nuly; nesmieš meniť rozhodnutie, '
            'pridávať čísla, pravdepodobnosti ani správy. Vstup: '+serialized)
    try:
        raw=api.groq_json(prompt,search=False,thinking_level='low')
        selections={}
        for symbol,indices in raw.get('selections',{}).items():
            if symbol in facts and isinstance(indices,list):
                selections[symbol]=[facts[symbol]['reasons'][i] for i in indices[:2] if type(i) is int and 0<=i<len(facts[symbol]['reasons'])]
        if not selections:
            raise ValueError('No valid selections')
        result=dict(available=True,selections=selections)
        cache.update(key=key,at=time.time(),result=result)
        cache.pop('failed_at',None)
        return result
    except Exception as exc:
        cache['failed_at']=time.time()
        cache['last_error_type']=type(exc).__name__
        return dict(available=False,selections={})
