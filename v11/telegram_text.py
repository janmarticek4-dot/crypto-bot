"""Presentation-only link removal; evidence objects retain their original URLs."""
import re

def without_links(text):
    # Preserve labels, never render either Markdown or HTML clickable destinations.
    text=re.sub(r'\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)',r'\1',str(text),flags=re.I)
    text=re.sub(r'<a\b[^>]*>(.*?)</a>',r'\1',text,flags=re.I|re.S)
    text=re.sub(r'(?:https?://|www\.)[^\s<>]+','',text,flags=re.I)
    return '\n'.join(re.sub(r'[ \t]+',' ',line).rstrip(' ;') for line in text.splitlines()).strip()
