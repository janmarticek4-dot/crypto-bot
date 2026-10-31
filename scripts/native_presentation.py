"""Presentation-only native entrypoint; native rules and state handling stay unchanged."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as legacy
from v11.telegram_text import without_links


def run():
    original_monitor = legacy.run_safety_monitor
    from v11.verified_monitor import run as monitor
    legacy.run_safety_monitor = lambda: monitor(legacy)
    original = legacy.telegram_send
    def send(message):
        return original(without_links(message))
    legacy.telegram_send = send
    try:
        return legacy.main()
    finally:
        legacy.telegram_send = original
        legacy.run_safety_monitor = original_monitor


if __name__ == "__main__":
    run()
