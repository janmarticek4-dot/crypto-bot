#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ft="${FREQTRADE_BIN:-freqtrade}"
mkdir -p backtesting/user_data
# Download warm-up before the first trading period, preserve out-of-sample 2025.
"$ft" download-data --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --timeframes 1h 4h 1d --timerange 20230101-20260101
for period in 20240101-20250101 20250101-20260101; do
 for strategy in TrendComponent PullbackComponent CombinedStrategy; do
  "$ft" backtesting --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --strategy-path backtesting/strategies --strategy "$strategy" --timerange "$period" --cache none --timeframe-detail 1h --export trades --export-filename "backtesting/user_data/${strategy}-${period}.json"
 done
done
"${PYTHON_BIN:-python}" backtesting/report.py

"$ft" lookahead-analysis --config backtesting/config.json --userdir backtesting/user_data --datadir backtesting/user_data/data/binance --strategy-path backtesting/strategies --strategy CombinedStrategy --timerange 20250101-20260101
