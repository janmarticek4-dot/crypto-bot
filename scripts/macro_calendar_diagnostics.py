"""Isolated real calendar validation. No state, bot, Telegram or AI imports."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.macro_source_diagnostics import sources, fetch, probe_with_retry, ROOT
from v11.fundamentals import parse_calendar, parse_fomc, timestamp
from zoneinfo import ZoneInfo


def windows(events, now):
    result = {}
    for label, hours in [('24h', 24), ('7d', 168), ('14d', 336)]:
        rows = []
        for item in events:
            at = timestamp(item.get('event_at'))
            day = item.get('event_date')
            if at is not None:
                include = now <= at <= now + timedelta(hours=hours)
            else:
                # Date-only events are candidates, never asserted to be in an exact 24h window.
                include = bool(day and now.astimezone(ZoneInfo('Europe/Bratislava')).date().isoformat() <= day <= (now + timedelta(hours=hours)).astimezone(ZoneInfo('Europe/Bratislava')).date().isoformat())
            if include:
                rows.append(dict(item, bratislava_at=at.astimezone(ZoneInfo('Europe/Bratislava')).isoformat() if at else None,
                                 window_precision='exact' if at else 'date_only_candidate',
                                 consensus=None, actual=None, confirmed_direction=None))
        result[label] = rows
    return result


def run(fetcher=fetch):
    now = datetime.now(timezone.utc)
    events, statuses = [], []
    for source in sources(now.year):
        if source['format'] not in ('ics', 'fomc_html'):
            continue
        bodies = []
        def capture(candidate):
            raw, meta = fetcher(candidate)
            bodies.append(raw)
            return raw, meta
        status = probe_with_retry(source, capture)
        if status['status'] == 'SUCCESS':
            attributed = dict(source, official=True)
            parser = parse_calendar if source['format'] == 'ics' else parse_fomc
            try:
                parsed = parser(bodies[-1], attributed, now)
                events.extend(parsed)
                status['future_relevant_events'] = len(parsed)
            except Exception as exc:
                status.update(status='INVALID_FORMAT', error_type=type(exc).__name__)
        statuses.append(status)
    payload = dict(checked_at=now.isoformat(), sources=statuses, windows=windows(events, now),
                   coverage='Fed meeting dates and BLS calendar only; BEA/ECB and unscheduled events not covered. Missing entries do not prove absence of events.')
    output = ROOT / 'macro-diagnostics-output'
    output.mkdir(exist_ok=True)
    (output / 'calendar-results.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Calendar validation', '', payload['coverage'], '', 'Consensus, actual result and confirmed price direction: N/A unless separately verified.']
    for status in statuses:
        lines.append(f"Source {status['id']}: {status['status']}; future relevant events: {status.get('future_relevant_events', 'N/A')}")
    for name, rows in payload['windows'].items():
        lines += ['', '## ' + name]
        if not rows:
            lines.append('N/A — no verified entries available; not proof of no events.')
        for item in rows:
            lines.append(f"- {item['title']} | {item.get('bratislava_at') or item.get('event_date')} | time: {'verified' if item.get('bratislava_at') else 'N/A; date-only candidate'} | {item['url']}")
            lines.append('  Possible mechanism (not confirmed direction): ' + '; '.join(item['mechanisms']))
    (output / 'CALENDAR.md').write_text('\n'.join(lines) + '\n')
    return 1 if any(s['status'] == 'DIAGNOSTIC_ERROR' for s in statuses) else 0


if __name__ == '__main__':
    raise SystemExit(run())
