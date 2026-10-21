"""Transport boundaries: Unicode-safe logical chunks and fixture isolation."""
import os


def allow_telegram():
    if os.getenv('BOT_DATA_MODE','live') != 'live' or os.getenv('BOT_DISABLE_TELEGRAM')=='1':
        raise RuntimeError('Telegram disabled for preview/test data')


def require_live_snapshot(snapshot):
    if os.getenv('BOT_DATA_MODE','live')!='live' or snapshot.get('synthetic') or snapshot.get('data_mode','live')!='live':
        raise RuntimeError('Synthetic snapshot refused by live analysis entrypoint')


def units(text):
    return len(text.encode('utf-16-le'))//2


def chunks(message,limit=3800):
    """Keep paragraphs/lines together where possible; count UTF-16 units."""
    room=limit-30
    if room<10:raise ValueError('Chunk limit too small')
    parts=[];current=''
    for line in message.splitlines():
        pieces=[];piece=''
        for char in line:
            if units(piece)+units(char)>room:
                pieces.append(piece);piece=''
            piece+=char
        pieces.append(piece)
        for piece in pieces:
            addition=('\n' if current else '')+piece
            if units(current+addition)>room:
                parts.append(current);current=piece
            else:current+=addition
    if current:parts.append(current)
    return [f'[{i}/{len(parts)}]\n'+p for i,p in enumerate(parts,1)] if len(parts)>1 else parts
