"""Run bot tests with all unmocked network access disabled."""
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
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
