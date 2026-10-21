#!/usr/bin/env bash
# Offline research and public market-data reads only. Never runs main.py or trade.
set -euo pipefail
cd "$(dirname "$0")/../.."
ft="${FREQTRADE_BIN:-/workspace/.venvs/freqtrade/bin/freqtrade}"
py="${RESEARCH_PYTHON:-/workspace/.venvs/freqtrade/bin/python}"
mkdir -p backtesting/user_data
"$ft" download-data --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --timeframes 1h 4h 1d --pairs SOL/USDT TAO/USDT ONDO/USDT RENDER/USDT AAVE/USDT FET/USDT BTC/USDT ETH/USDT --timerange 20230101-20261001
for period in 20240101-20250101 20250101-20260101; do
 for fee in 0.012 0.002 0; do
  "$ft" backtesting --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --strategy-path backtesting/strategies --strategy TrendComponent --timerange "$period" --fee "$fee" --cache none --timeframe-detail 1h --export trades
 done
done
for period in 20240101-20250101 20250101-20260101 20260101-20261001; do
 "$ft" backtesting --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --strategy-path backtesting/strategies --strategy LegacyNoProtectiveExit --timerange "$period" --cache none --timeframe-detail 1h --export trades
done
"$ft" backtesting --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --strategy-path backtesting/strategies --strategy TrendComponent --timerange 20260101-20261001 --cache none --timeframe-detail 1h --export trades
"$py" research/phase2/run.py
"$py" research/phase2/diagnose.py
"$py" research/phase2/report.py
"$py" -m unittest discover -s tests -v
"$py" -m unittest discover -s research/phase2 -p 'test_*.py' -v
