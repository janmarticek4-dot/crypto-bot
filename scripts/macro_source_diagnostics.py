"""Standalone stdlib HTTPS/schema diagnostics. No bot imports, secrets or trading.

Copy this file and its manual workflow into an empty research repository to run
without registering any workflow on the original production default branch.
"""
import argparse
import csv
import io
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000
TIMEOUT = 12


def sources(year):
    return [
        dict(provider='Fed', id='fed_rss', format='rss', url='https://www.federalreserve.gov/feeds/press_all.xml'),
        dict(provider='Fed', id='fomc_calendar', format='fomc_html', url='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'),
        dict(provider='BLS', id='bls_rss', format='rss', url='https://www.bls.gov/feed/bls_latest.rss'),
        dict(provider='BLS', id='bls_calendar', format='ics', url='https://www.bls.gov/schedule/news_release/bls.ics'),
        dict(provider='BEA', id='bea_rss', format='rss', publisher='bea.gov', url='https://apps.bea.gov/rss/rss.xml'),
        dict(provider='BEA', id='bea_rss_alternative', format='rss', publisher='bea.gov', url='https://www.bea.gov/rss/rss.xml'),
        dict(provider='SEC', id='sec_legacy_rss', format='rss', url='https://www.sec.gov/news/pressreleases.rss'),
        dict(provider='ECB', id='ecb_rss', format='rss', url='https://www.ecb.europa.eu/rss/press.html'),
        dict(provider='SEC', id='sec_rss', format='rss', url='https://www.sec.gov/newsroom/press-releases/rss.xml'),
        dict(provider='CFTC', id='cftc_rss', format='rss', url='https://www.cftc.gov/RSS/RSSGP/rssgp.xml'),
        dict(provider='BEA', id='bea_calendar_candidate', format='ics', url='https://www.bea.gov/news/schedule/ics/online-calendar-subscription'),
        dict(provider='BLS', id='bls_year_calendar', format='ics', url='https://www.bls.gov/schedule/news_release/current_year.ics'),
        dict(provider='Treasury', id='treasury_csv_candidate', format='treasury_csv', url=f'https://home.treasury.gov/resource-center-data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv'),
        dict(provider='Treasury', id='treasury_yields', format='treasury_xml', url=f'https://home.treasury.gov/resource-center-data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}'),
    ]


class InvalidFormat(ValueError):
    pass


class UnsafeRedirect(ValueError):
    pass


def redirect_allowed(source, target):
    start = urllib.parse.urlsplit(source['url'])
    end = urllib.parse.urlsplit(target)
    if end.scheme != 'https' or not end.hostname or end.username or end.password or end.port not in (None, 443):
        return False
    host = end.hostname.removeprefix('www.')
    allowed = {start.hostname.removeprefix('www.'), source.get('publisher', start.hostname.removeprefix('www.'))}
    return any(host == publisher or host.endswith('.' + publisher) for publisher in allowed)


class PublisherRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 4

    def __init__(self, source):
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not redirect_allowed(self.source, newurl):
            raise UnsafeRedirect('Redirect refused before contacting an unrelated/non-HTTPS destination')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(source):
    # Default ProxyHandler is preserved: never bypass a required network proxy.
    opener = urllib.request.build_opener(PublisherRedirects(source))
    request = urllib.request.Request(source['url'], method='GET', headers={
        'User-Agent': 'CryptoAIBotMacroDiagnostics/1.0 (public source availability check)',
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/calendar, text/html;q=0.5',
    })
    with opener.open(request, timeout=source.get('timeout', TIMEOUT)) as response:
        if not redirect_allowed(source, response.geturl()):
            raise UnsafeRedirect('Unexpected final publisher')
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InvalidFormat('Response exceeds 2MB diagnostic limit')
        return raw, dict(http_status=response.status, final_url=response.geturl(),
            content_type=response.headers.get('Content-Type'),
            # Do not serialize cookies, authentication headers, proxy config or environment.
            response_headers={k: response.headers[k] for k in ('Date', 'Server', 'Via', 'Retry-After') if k in response.headers})


def local_tag(node):
    return node.tag.rsplit('}', 1)[-1]


def date(raw):
    try:
        result = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        try:
            result = parsedate_to_datetime(raw)
        except (ValueError, TypeError, AttributeError):
            return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def validate(raw, kind):
    if not raw.strip():
        raise InvalidFormat('Empty body')
    if kind == 'ics':
        text = raw.decode('utf-8-sig')
        text = re.sub(r'\r?\n[ \t]', '', text)
        if 'BEGIN:VCALENDAR' not in text or 'END:VCALENDAR' not in text:
            raise InvalidFormat('Expected iCalendar; HTML/error page is not a calendar')
        blocks = text.split('BEGIN:VEVENT')[1:]
        valid = sum('END:VEVENT' in b and bool(re.search(r'^DTSTART(?:;[^:]*)?:', b, re.M)) and bool(re.search(r'^SUMMARY:', b, re.M)) for b in blocks)
        if blocks and not valid:
            raise InvalidFormat('Calendar event schema lacks DTSTART/SUMMARY')
        return dict(format='iCalendar', records=len(blocks), structurally_valid_records=valid,
                    note='Format/reachability only; dates, timezone precision and future coverage require calendar-level validation.')
    if kind == 'fomc_html':
        text = raw.decode('utf-8-sig')
        years = re.findall(r'(20\d{2})\s+FOMC Meetings', text)
        if not years or 'fomc-meeting__date' not in text or 'fomc-meeting__month' not in text:
            raise InvalidFormat('FOMC calendar markers missing: changed HTML, challenge page or wrong endpoint')
        return dict(format='FOMC HTML', years=sorted(set(years)),
                    records=text.count('fomc-meeting__date'), note='Meeting dates do not prove a decision time; no assumed Fed hour.')
    if kind == 'treasury_csv':
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        rows=[]
        for row in reader:
            try:
                day=datetime.strptime(row['Date'], '%m/%d/%Y').date()
                values=[float(row[key]) for key in ('2 YR','10 YR')]
                if all(math.isfinite(v) and -5<=v<=30 for v in values):rows.append(day)
            except (ValueError,TypeError,KeyError):continue
        if not rows:raise InvalidFormat('Treasury CSV Date/2 YR/10 YR missing or invalid')
        return dict(format='Treasury CSV', records=len(rows), latest_observation_date=max(rows).isoformat(),
                    note='Daily observations only; availability and freshness require separate checks.')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise InvalidFormat('Malformed XML or HTML challenge instead of data') from exc
    if kind == 'rss':
        tag = local_tag(root)
        if tag == 'rss' and any(local_tag(n) == 'channel' for n in root):
            records = [n for n in root.iter() if local_tag(n) == 'item']
        elif tag == 'feed' and any(local_tag(n) == 'title' for n in root):
            records = [n for n in root if local_tag(n) == 'entry']
        else:
            raise InvalidFormat('Expected RSS channel or Atom feed, not arbitrary XML/HTML')
        stamps = [date(n.text or '') for record in records for n in record if local_tag(n) in ('pubDate', 'published', 'updated')]
        stamps = [stamp for stamp in stamps if stamp]
        return dict(format='RSS' if tag == 'rss' else 'Atom', records=len(records),
                    latest_published_or_updated=max(stamps).isoformat() if stamps else None,
                    note='Publication/update time is not event time. Zero entries does not prove no events; success is not coverage/freshness certification.')
    if kind == 'treasury_xml':
        rows = []
        for n in root.iter():
            if local_tag(n) != 'properties':
                continue
            fields = {local_tag(child): child.text for child in n}
            try:
                observation = datetime.fromisoformat(fields['NEW_DATE']).date()
                values = [float(fields[k]) for k in ('BC_2YEAR', 'BC_10YEAR')]
                if not all(math.isfinite(x) and -5 <= x <= 30 for x in values):
                    continue
                rows.append(observation)
            except (ValueError, TypeError, KeyError):
                continue
        if not rows:
            raise InvalidFormat('Treasury properties/NEW_DATE/2Y/10Y observations missing or invalid')
        return dict(format='Treasury XML', records=len(rows), latest_observation_date=max(rows).isoformat(),
                    note='Daily observation; not a live yield quote or an economic consensus.')
    raise InvalidFormat('Unsupported expected format')


def network_failure(exc):
    reason = getattr(exc, 'reason', exc)
    message = str(reason)
    if re.search(r'Tunnel connection failed:\s*(403|407)', message, re.I):
        code = int(re.search(r'Tunnel connection failed:\s*(403|407)', message, re.I).group(1))
        return dict(status='NETWORK_BLOCKED', layer='proxy_connect', proxy_status=code, origin_http_status=None,
                    error='HTTPS CONNECT/tunnel refused before an origin response')
    if isinstance(exc, ssl.SSLError) or isinstance(reason, ssl.SSLError):
        return dict(status='TLS_ERROR', layer='tls', origin_http_status=None, error='TLS/certificate validation failed')
    if isinstance(reason, socket.gaierror):
        return dict(status='NETWORK_ERROR', layer='dns', origin_http_status=None, error='DNS resolution failed')
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return dict(status='NETWORK_ERROR', layer='timeout', origin_http_status=None, error='Connection/read timeout')
    return dict(status='NETWORK_ERROR', layer='transport', origin_http_status=None,
                error='Connection failed before a usable HTTP response; see error_type')


def probe(source, fetcher=fetch, now=None):
    now = now or datetime.now(timezone.utc)
    row = dict(source, checked_at=now.isoformat())
    started = time.monotonic()
    try:
        raw, metadata = fetcher(source)
        row.update(metadata, bytes=len(raw), body_sha256=hashlib.sha256(raw).hexdigest())
        if not 200 <= metadata.get('http_status', 0) < 300:
            raise InvalidFormat('Fetcher returned non-success without HTTPError')
        row.update(validation=validate(raw, source['format']), status='SUCCESS', layer='parsed_data')
    except urllib.error.HTTPError as exc:
        headers = exc.headers or {}
        row['response_headers'] = {k: headers[k] for k in ('Date', 'Server', 'Via', 'Retry-After', 'X-Squid-Error') if k in headers}
        if exc.code == 407 or (exc.code == 403 and headers.get('X-Squid-Error')):
            row.update(status='NETWORK_BLOCKED', layer='http_proxy', proxy_status=exc.code,
                       origin_http_status=None, error='Explicit HTTP proxy rejection')
        else:
            row.update(status='HTTP_ERROR', layer='http_response', http_status=exc.code,
                       origin_http_status=None, origin_attribution='HTTPS endpoint or CDN/gateway responded; application origin not independently proven',
                       error='HTTP non-success response; no response body/credentials exported')
        row['retry_after'] = headers.get('Retry-After')
        row['error_type'] = type(exc).__name__
    except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError, OSError) as exc:
        row.update(network_failure(exc), error_type=type(exc).__name__)
    except (InvalidFormat, ET.ParseError, UnicodeError) as exc:
        row.update(status='INVALID_FORMAT', layer='body_validation', error_type=type(exc).__name__, error=str(exc))
    except UnsafeRedirect:
        row.update(status='REDIRECT_BLOCKED', layer='redirect_policy', error_type='UnsafeRedirect', error='Redirect outside approved HTTPS publisher refused before follow')
    except Exception as exc:
        row.update(status='DIAGNOSTIC_ERROR', layer='diagnostic', error_type=type(exc).__name__, error='Unexpected diagnostic failure; no exception text/body exported')
    row['seconds'] = round(time.monotonic() - started, 3)
    return row


def probe_with_retry(source, fetcher=fetch):
    """One retry only for timeout/HTTP5xx, never for policy blocks or 4xx."""
    first = probe(source, fetcher)
    retry = first.get('layer') == 'timeout' or (
        first['status'] == 'HTTP_ERROR' and first.get('http_status', 0) in (500, 502, 503, 504)
        and not first.get('retry_after'))
    if not retry:
        return first
    second = probe(dict(source, timeout=25), fetcher)
    second['attempts'] = [first, dict(second)]
    return second


def report(rows, context):
    lines = ['# Macro Sources Diagnostics', '', f"UTC: {context['started_at']}; prostredie: {context['runner_environment']}.",
        '', '| Zdroj | Endpoint | Výsledok | Vrstva | HTTP/proxy | Záznamy |', '|---|---|---|---|---|---:|']
    for r in rows:
        code = r.get('http_status', r.get('proxy_status', 'N/A'))
        lines.append(f"| {r['provider']} | {r['id']} | {r['status']} | {r['layer']} | {code} | {r.get('validation', {}).get('records', 'N/A')} |")
    lines += ['', 'SUCCESS znamená HTTPS + rozpoznaný formát, nie úplnosť alebo aktuálnosť kalendára. HTTP200 s HTML blokovacou stránkou je INVALID_FORMAT.',
        'NETWORK_BLOCKED/CONNECT403 nie je HTTP403 pôvodného webu. HTTP_ERROR je odpoveď HTTPS endpointu/CDN/gateway; bez ďalšieho dôkazu ju nepripisujeme samotnému aplikačnému serveru.',
        'Chyba zdroja je výsledok testu, nie zlyhanie workflow. DIAGNOSTIC_ERROR zlyhá job. Bez platených API, tajných údajov, Telegramu, bota, obchodných signálov a obchodov.', '', '## Podrobnosti']
    for r in rows:
        lines += ['', f"### {r['provider']} — {r['id']}", r['url'],
            f"{r['status']}: {r.get('error') or r.get('validation', {}).get('note', 'N/A')}",
            'Oprava: ' + ('povoliť HTTPS/CONNECT na daný host v sieťovej politike/proxy; zmena feed cesty nepomôže' if r['status'] == 'NETWORK_BLOCKED' else
                'skontrolovať origin/CDN status, endpoint a fair-access pravidlá; pri429 rešpektovať Retry-After' if r['status'] == 'HTTP_ERROR' else
                'preveriť Content-Type, schému a prípadnú challenge stránku; nemeníme odpoveď na vymyslené dáta' if r['status'] == 'INVALID_FORMAT' else
                'preveriť DNS/TLS/dostupnosť runnera; neobchádzať overovanie certifikátu' if r['status'] in ('NETWORK_ERROR', 'TLS_ERROR') else 'detaily a merané polia v results.json')]
    return '\n'.join(lines) + '\n'


def run(output):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'macro-diagnostics-output').resolve()):
        raise ValueError('Diagnostic output must stay inside macro-diagnostics-output/')
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    context = dict(started_at=now.isoformat(), bratislava_at=now.astimezone(ZoneInfo('Europe/Bratislava')).isoformat(),
        runner_environment=os.getenv('RUNNER_ENVIRONMENT', 'local_not_github_hosted'),
        commit=os.getenv('GITHUB_SHA'), branch=os.getenv('GITHUB_REF_NAME'),
        proxy_environment_present=bool(urllib.request.getproxies()), tls_verification=True,
        no_bot_imports=True, no_secrets_required=True, no_orders=True)
    # Sequential bounded diagnostics; one retry for transient failures only.
    rows = [probe_with_retry(source) for source in sources(now.year)]
    counts = {status: sum(r['status'] == status for r in rows) for status in sorted({r['status'] for r in rows})}
    payload = dict(context=context, counts=counts, sources=rows)
    (output / 'results.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (output / 'REPORT.md').write_text(report(rows, context))
    (output / 'README.txt').write_text('REPORT.md: readable results. results.json: status, HTTP/proxy layer, format, timings and hashes. No raw bodies, secrets or production data.\n')
    print(json.dumps(counts))
    return 1 if any(r['status'] == 'DIAGNOSTIC_ERROR' for r in rows) else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='macro-diagnostics-output')
    raise SystemExit(run(parser.parse_args().output))
