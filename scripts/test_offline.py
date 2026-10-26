"""Run bot tests with all unmocked network access disabled."""
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
# Production-entrypoint regression tests use mocked I/O and their own explicit
# fixture contexts. Do not inherit shadow mode from the outer Actions job.
# This changes this test subprocess only, not the subsequent live shadow step.
os.environ['BOT_DATA_MODE']='live'
os.environ['BOT_DISABLE_TELEGRAM']='1'
os.environ['GROQ_API_KEY']=''
os.environ['TELEGRAM_TOKEN']=''
os.environ['TELEGRAM_CHAT_ID']=''

def forbidden(*args,**kwargs):
    raise RuntimeError('Unmocked network forbidden in unit tests')

if __name__=='__main__':
    with patch.object(socket.socket,'connect',forbidden),patch.object(socket.socket,'connect_ex',forbidden):
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
    raise SystemExit(not result.wasSuccessful())
