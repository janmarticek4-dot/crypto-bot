"""Civil-time slots; bounded late catch-up, same canonical delivery identity."""
from zoneinfo import ZoneInfo
BL=ZoneInfo('Europe/Bratislava')
WINDOWS=(('morning',420,660),('usa',900,1020),('evening',1200,1380))

def phase(now):
    local=now.astimezone(BL);minute=local.hour*60+local.minute
    return next((name for name,start,end in WINDOWS if start<=minute<=end),None)

def target(now,kind):
    hour={'morning':7,'usa':15,'evening':20}[kind]
    return now.astimezone(BL).replace(hour=hour,minute=0,second=0,microsecond=0)
