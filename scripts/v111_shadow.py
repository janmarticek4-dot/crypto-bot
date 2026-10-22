"""Live-data shadow previews. No import of main, state backend, Telegram or broker clients."""
import argparse
import copy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v11 import data, fundamentals, macro_context
from v11.ai import explain
from v11.briefing import build
from v11.reporting import chunks
from v11.runtime import market_status
from v11.strategy import decide

SYMBOLS = ('AAVE', 'TAO', 'FET', 'SOL', 'ONDO', 'RENDER')
BL = ZoneInfo('Europe/Bratislava')


class ShadowAPI:
    """Restricted public GET interface; optional Groq POST. No state/delivery methods."""
    TELEGRAM_TOKEN = ''
    TELEGRAM_CHAT_ID = ''

    def __init__(self, use_groq=False):
        self.GROQ_API_KEY = os.getenv('GROQ_API_KEY', '').strip() if use_groq else ''
        self.model = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b').strip()
        self.groq_attempts = 0
        self.requests = []

    @staticmethod
    def safe_float(value, default=None):
        try:
            out = float(value)
            return out if math.isfinite(out) else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def parse_timestamp(value):
        try:
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return result if result.tzinfo else None
        except (ValueError, TypeError, AttributeError):
            return None

    def request(self, url, method='GET', headers=None, payload=None, timeout=15, retries=2):
        import requests
        parsed = urlsplit(url)
        allowed = {
            ('data-api.binance.vision', '/api/v3/klines', 'GET'),
            ('data-api.binance.vision', '/api/v3/ticker/24hr', 'GET'),
            ('api.coingecko.com', '/api/v3/coins/markets', 'GET'),
            ('api.coingecko.com', '/api/v3/global', 'GET'),
            ('api.groq.com', '/openai/v1/chat/completions', 'POST'),
        }
        if parsed.scheme != 'https' or parsed.username or parsed.password or (parsed.hostname, parsed.path, method) not in allowed:
            raise ValueError('Network destination/method blocked in shadow runner')
        for attempt in range(min(retries, 2)):
            started = time.monotonic()
            record = dict(host=parsed.hostname, path=parsed.path, method=method,
                          checked_at=datetime.now(timezone.utc).isoformat())
            try:
                response = requests.request(method, url, headers=headers, json=payload,
                                            timeout=min(timeout, 20), allow_redirects=False)
                record['http_status'] = response.status_code
                response.raise_for_status()
                if 300 <= response.status_code < 400:
                    raise ValueError('Shadow redirects refused')
                return response.json()
            except requests.HTTPError:
                if response.status_code not in (429, 500, 502, 503, 504) or attempt + 1 >= min(retries, 2):
                    raise
                try:
                    delay = float(response.headers.get('Retry-After', 2))
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(response.headers['Retry-After']) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, KeyError, TypeError):
                        delay = 2
                if not math.isfinite(delay) or delay > 10:
                    raise  # respect a long quota reset by declining an early retry
                time.sleep(max(0, delay))
            finally:
                record['seconds'] = round(time.monotonic() - started, 3)
                self.requests.append(record)

    def http_json(self, url, headers=None, timeout=15, retries=2):
        return self.request(url, headers=headers, timeout=timeout, retries=retries)

    def coingecko_markets(self, ids):
        return self.http_json('https://api.coingecko.com/api/v3/coins/markets?' + urlencode(dict(
            vs_currency='usd', ids=','.join(ids), per_page=100, page=1, sparkline='false',
            price_change_percentage='24h,7d')))

    def groq_json(self, prompt, **kwargs):
        if not self.GROQ_API_KEY:
            raise RuntimeError('Groq key unavailable')
        self.groq_attempts += 1
        raw = self.request('https://api.groq.com/openai/v1/chat/completions', method='POST',
            headers={'Authorization': 'Bearer ' + self.GROQ_API_KEY}, timeout=20, retries=2,
            payload=dict(model=self.model, messages=[dict(role='user', content=prompt)],
                         response_format={'type': 'json_object'}, temperature=0, max_tokens=500))
        return json.loads(raw['choices'][0]['message']['content'])


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def protected_hashes():
    # Hash without reading/serializing any real portfolio into artifacts.
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
            ('main.py', 'bot_state.json', 'v11/portfolio.py', 'v11/strategy.py', '.github/workflows/run.yml')}


def render(snapshot, fundamental, ai_api, now):
    safety = market_status(snapshot, {})
    evals = {s: decide(snapshot['coins'][s], held=False, approved=False,
                      market_complete=snapshot['complete'], risk_normal=safety['state'] == 'NORMAL') for s in SYMBOLS}
    ai = explain(ai_api, {}, evals)
    if not any(ai.get('selections', {}).values()):
        ai = dict(available=False, selections={})
    for symbol, reasons in ai.get('selections', {}).items():
        if symbol in evals:
            evals[symbol]['display_reasons'] = reasons
    reports = {}
    for name, hour in (('morning', '07:00'), ('evening', '20:00')):
        header = ('SHADOW TEST — ŽIVÉ DÁTA, ŽIADNE ODOSLANIE ANI OBCHODY\n'
                  'Čas zberu: ' + now.astimezone(BL).isoformat() + '\n'
                  'Ide o náhľad šablóny ' + hour + ', nie historickú analýzu v tomto čase.\n'
                  'Oba náhľady používajú rovnaký aktuálny snapshot. Reálne ranné/večerné porovnanie N/A.\n'
                  'Skutočné pozície a zostatky nie sú načítané; BEZ POZÍCIE znamená iba prázdny shadow kontext.\n')
        # Independent empty state: no fabricated morning record for the evening report.
        lines = build(copy.deepcopy(snapshot), copy.deepcopy(evals), {}, safety, fundamental,
                      {}, 'SHADOW_' + now.astimezone(BL).date().isoformat() + '_' + hour, now.astimezone(BL))
        reports[name] = header + '\n'.join(lines) + '\n'
    return reports, evals, ai


def outage_checks(snapshot, now):
    """Explicit faults, separate from live source results; no fault data enters live report."""
    def failed(_source):
        raise ConnectionError('Injected source outage')
    unavailable = fundamentals.collect({}, now, fetcher=failed)
    unavailable['macro_context'] = macro_context.collect({}, now, fetcher=failed)

    class Down(ShadowAPI):
        GROQ_API_KEY = 'fault-injection-not-a-real-key'
        def __init__(self):
            self.GROQ_API_KEY = 'fault-injection-not-a-real-key'
            self.calls = 0
        def groq_json(self, *args, **kwargs):
            self.calls += 1
            raise ConnectionError('Injected Groq outage')

    api = Down()
    reports, evals, ai = render(snapshot, unavailable, api, now)
    no_key = ShadowAPI()
    baseline, original_evals, _ = render(snapshot, unavailable, no_key, now)
    assert not ai['available'] and api.calls == 1
    assert evals == original_evals and reports == baseline
    assert all(x['status'] == 'N/A' for x in unavailable['sources'])
    assert unavailable['metrics'] == {} and unavailable['macro_context']['treasury'] is None
    assert all('N/A' in r for r in reports.values())
    return dict(passed=True, injected=True, groq_unavailable_fallback=True,
                sources_unavailable_na=True, no_ai_authored_facts=True,
                deterministic_decisions_unchanged=True), reports


def run(out, use_groq=False):
    out = Path(out).resolve()
    # Never allow artifacts to overwrite repository sources/state or an arbitrary private directory.
    allowed = (ROOT / 'shadow-output').resolve()
    if not out.is_relative_to(allowed):
        raise ValueError('Output must be inside shadow-output/')
    out.mkdir(parents=True, exist_ok=True)
    before = protected_hashes()
    api = ShadowAPI(use_groq)
    names = ('BOT_DISABLE_TELEGRAM', 'BOT_DATA_MODE', 'V11_RULES_VALIDATED')
    prior_env = {k: os.environ.get(k) for k in names}
    os.environ.update(BOT_DISABLE_TELEGRAM='1', BOT_DATA_MODE='shadow', V11_RULES_VALIDATED='false')
    try:
        original_watchlist = data.COINS
        try:
            data.COINS = {s: original_watchlist[s] for s in SYMBOLS}
            snap = data.collect(api, full=True)
        finally:
            data.COINS = original_watchlist
        # Retain BTC/ETH context and only requested altcoins in the artifact.
        snap['coins'] = {s: d for s, d in snap['coins'].items() if s in ('BTC', 'ETH', *SYMBOLS)}
        now = datetime.now(timezone.utc)
        source_requests = []
        def fetch(source):
            started = time.monotonic()
            item = dict(url=source['url'], checked_at=datetime.now(timezone.utc).isoformat())
            try:
                raw = fundamentals.fetch(source)
                item.update(status='FETCHED', bytes=len(raw))
                return raw
            except Exception as exc:
                item.update(status='N/A', error_type=type(exc).__name__, http_status=getattr(exc, 'code', None))
                raise
            finally:
                item['seconds'] = round(time.monotonic() - started, 3)
                source_requests.append(item)
        fund = fundamentals.collect({}, now, fetcher=fetch)
        fund['macro_context'] = macro_context.collect({}, now, fetcher=fetch)
        reports, evaluations, ai = render(snap, fund, api, now)
        for name, report in reports.items():
            (out / (name + '.txt')).write_text(report)
            write_json(out / (name + '_parts.json'), chunks(report))
        write_json(out / 'market_snapshot.json', snap)
        write_json(out / 'fundamentals.json', fund)
        write_json(out / 'source_availability.json', dict(feed_parsing=fund['sources'], fetches=source_requests,
                                                       market_and_ai=api.requests))
        faults, fault_reports = outage_checks(snap, now)
        write_json(out / 'outage_checks.json', faults)
        for name, report in fault_reports.items():
            (out / (name + '_injected_outage.txt')).write_text('FAULT INJECTION — NOT LIVE SOURCE STATUS\n' + report)
        usable = {s: bool(snap['coins'][s].get('price') and not snap['coins'][s]['stale'] and
                         snap['coins'][s]['frames'].get('4h', {}).get('ema200') is not None) for s in SYMBOLS}
        ok = all(usable.values())
        summary = dict(status='CURRENT_MARKET_DATA' if ok else 'INCOMPLETE_MARKET_DATA',
            collected_at=now.isoformat(), timezone='Europe/Bratislava', symbols=list(SYMBOLS), current_market_data=usable,
            complete=snap['complete'], same_snapshot_templates=True, real_morning_evening_comparison=False,
            fundamentals_available=sum(s['status'] == 'OK' for s in fund['sources']), fundamentals_total=len(fund['sources']),
            groq=dict(requested=use_groq, available=ai['available'], calls=api.groq_attempts,
                      fallback=not ai['available']), protected_files_unchanged=before == protected_hashes(),
            telegram_enabled=False, production_state_loaded=False, real_positions_loaded=False,
            state_written=False, orders_enabled=False, faults=faults,
            commit=os.getenv('GITHUB_SHA'), branch=os.getenv('GITHUB_REF_NAME'))
        write_json(out / 'summary.json', summary)
        (out / 'README.txt').write_text('V11.1 Shadow Test\nLive market snapshot, preview templates only.\n'
            'morning.txt / evening.txt: actual collected data.\n'
            '*_injected_outage.txt: deliberate source/Groq failures, NOT actual source status.\n'
            'source_availability.json: fetch/parse results; HTTP success does not prove complete/current fundamentals.\n'
            'summary.json: market freshness and safety checks.\n'
            'No real portfolio, private state, Telegram messages or orders.\n')
        print('Shadow results: ' + summary['status'] + '; Groq ' + ('available' if ai['available'] else 'deterministic fallback'))
        return 0 if ok else 2
    finally:
        for key, value in prior_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if protected_hashes() != before:
            raise RuntimeError('Protected files changed during shadow test')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='shadow-output')
    parser.add_argument('--use-groq', action='store_true')
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.output, args.use_groq))
    except Exception as exc:
        # Never print request headers, keys, private state or provider response bodies.
        print('Shadow runner failed: ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
