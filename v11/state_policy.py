"""Fail-closed boundary for public analysis exports; never redact a private ledger."""
import re

class PublicDataError(ValueError):
    pass

# Prices/technical entry zones are public. Actual fills, ownership, balances and
# credentials belong only in private state, even if their current value is zero.
PRIVATE_FIELDS=frozenset({
    'portfolio_v11','portfolio','holdings','transactions','cash','initial_cash',
    'additional_capital','cash_delta','balances','balance','account_balance',
    'qty','quantity','purchase_price','average_purchase_price','cost_basis',
    'realized','unrealized','credentials','password','private_key','api_key',
    'access_token','refresh_token','telegram_token','telegram_chat_id',
    'groq_api_key','state_repo_token','state_encryption_key',
})
KEY_PATTERNS=(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
              r'\bgh[pousr]_[A-Za-z0-9]{20,}\b',r'\bgithub_pat_[A-Za-z0-9_]{20,}\b',
              r'\bgsk_[A-Za-z0-9]{20,}\b',r'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b')


def require_public_data(value):
    if isinstance(value,dict):
        for key,item in value.items():
            name=str(key).lower()
            if name in PRIVATE_FIELDS or (name=='positions' and item!='UNKNOWN; no real portfolio loaded'):
                raise PublicDataError('Private state field refused at public export boundary')
            if name=='held' and item is not False:
                raise PublicDataError('Real ownership is not public analysis data')
            require_public_data(item)
    elif isinstance(value,(list,tuple)):
        for item in value:require_public_data(item)
    elif isinstance(value,str) and any(re.search(pattern,value) for pattern in KEY_PATTERNS):
        raise PublicDataError('Credential-shaped value refused at public export boundary')
    return value
