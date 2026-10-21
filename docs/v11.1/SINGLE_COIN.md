# V11.1 single-asset Freqtrade runs

Research only. 2024 development; 2025 historical holdout already inspected in prior work, not a fresh untouched sample.
Account $1500, gross stake $1000, one position, same config cost per side as hold. USDT spot proxy, not eToro execution.
Config fee 1.2% models 1% fees + 0.2% spread/slippage each side; this is an assumption, not measured costs.
No new strategy activation. Profit factor N/A when no losses; zero trades is insufficient evidence.

| Asset | Strategy | Period | Trades | Net return | Max DD | Win rate | Avg win $ | Avg loss $ | PF | Hold return | Hold DD | Status |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SOL | TrendComponent | 20240101-20250101 | 7 | -7.42% | 34.67% | 28.57% | 336.30 | -156.78 | 0.86 | 55.12% | 35.66% | INSUFFICIENT |
| SOL | PullbackComponent | 20240101-20250101 | 5 | -4.58% | 22.90% | 40.00% | 159.21 | -129.04 | 0.82 | 55.12% | 35.66% | INSUFFICIENT |
| SOL | CombinedStrategy | 20240101-20250101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | 55.12% | 35.66% | INSUFFICIENT |
| TAO | TrendComponent | 20240101-20250101 | 4 | -40.31% | 40.31% | 25.00% | 59.73 | -221.47 | 0.09 | -1.42% | 53.30% | INSUFFICIENT |
| TAO | PullbackComponent | 20240101-20250101 | 1 | -14.76% | 14.76% | 0.00% | N/A | -221.42 | 0.00 | -1.42% | 53.30% | INSUFFICIENT |
| TAO | CombinedStrategy | 20240101-20250101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -1.42% | 53.30% | INSUFFICIENT |
| FET | TrendComponent | 20240101-20250101 | 3 | -44.30% | 44.30% | 0.00% | N/A | -221.51 | 0.00 | 57.10% | 71.93% | INSUFFICIENT |
| FET | PullbackComponent | 20240101-20250101 | 3 | -44.28% | 44.28% | 0.00% | N/A | -221.41 | 0.00 | 57.10% | 71.93% | INSUFFICIENT |
| FET | CombinedStrategy | 20240101-20250101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | 57.10% | 71.93% | INSUFFICIENT |
| ONDO | TrendComponent | 20240101-20250101 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | NO_DATA |
| ONDO | PullbackComponent | 20240101-20250101 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | NO_DATA |
| ONDO | CombinedStrategy | 20240101-20250101 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | NO_DATA |
| AAVE | TrendComponent | 20240101-20250101 | 5 | -37.12% | 37.12% | 20.00% | 226.83 | -195.90 | 0.29 | 119.70% | 37.64% | INSUFFICIENT |
| AAVE | PullbackComponent | 20240101-20250101 | 4 | 83.68% | 13.57% | 75.00% | 492.22 | -221.52 | 6.67 | 119.70% | 37.64% | INSUFFICIENT |
| AAVE | CombinedStrategy | 20240101-20250101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | 119.70% | 37.64% | INSUFFICIENT |
| RENDER | TrendComponent | 20240101-20250101 | 2 | 16.76% | 14.76% | 50.00% | 472.86 | -221.45 | 2.14 | -3.83% | 33.35% | INSUFFICIENT |
| RENDER | PullbackComponent | 20240101-20250101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -3.83% | 33.35% | INSUFFICIENT |
| RENDER | CombinedStrategy | 20240101-20250101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -3.83% | 33.35% | INSUFFICIENT |
| SOL | TrendComponent | 20250101-20260101 | 7 | -12.08% | 23.79% | 28.57% | 214.70 | -122.11 | 0.70 | -24.10% | 49.80% | INSUFFICIENT |
| SOL | PullbackComponent | 20250101-20260101 | 2 | -0.52% | 14.77% | 50.00% | 213.71 | -221.56 | 0.96 | -24.10% | 49.80% | INSUFFICIENT |
| SOL | CombinedStrategy | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -24.10% | 49.80% | INSUFFICIENT |
| TAO | TrendComponent | 20250101-20260101 | 3 | -31.05% | 31.05% | 0.00% | N/A | -155.24 | 0.00 | -34.73% | 50.17% | INSUFFICIENT |
| TAO | PullbackComponent | 20250101-20260101 | 3 | -32.23% | 32.23% | 0.00% | N/A | -161.13 | 0.00 | -34.73% | 50.17% | INSUFFICIENT |
| TAO | CombinedStrategy | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -34.73% | 50.17% | INSUFFICIENT |
| FET | TrendComponent | 20250101-20260101 | 6 | -34.08% | 40.02% | 16.67% | 369.66 | -176.17 | 0.42 | -57.18% | 63.69% | INSUFFICIENT |
| FET | PullbackComponent | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -57.18% | 63.69% | INSUFFICIENT |
| FET | CombinedStrategy | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -57.18% | 63.69% | INSUFFICIENT |
| ONDO | TrendComponent | 20250101-20260101 | 5 | -32.36% | 32.36% | 20.00% | 158.89 | -161.08 | 0.25 | -33.95% | 52.56% | INSUFFICIENT |
| ONDO | PullbackComponent | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -33.95% | 52.56% | INSUFFICIENT |
| ONDO | CombinedStrategy | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -33.95% | 52.56% | INSUFFICIENT |
| AAVE | TrendComponent | 20250101-20260101 | 3 | -32.64% | 32.64% | 0.00% | N/A | -163.21 | 0.00 | -36.32% | 48.74% | INSUFFICIENT |
| AAVE | PullbackComponent | 20250101-20260101 | 4 | -11.96% | 14.74% | 50.00% | 33.58 | -123.31 | 0.27 | -36.32% | 48.74% | INSUFFICIENT |
| AAVE | CombinedStrategy | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -36.32% | 48.74% | INSUFFICIENT |
| RENDER | TrendComponent | 20250101-20260101 | 3 | -39.61% | 39.61% | 0.00% | N/A | -198.03 | 0.00 | -54.98% | 63.02% | INSUFFICIENT |
| RENDER | PullbackComponent | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -54.98% | 63.02% | INSUFFICIENT |
| RENDER | CombinedStrategy | 20250101-20260101 | 0 | 0.00% | 0.00% | N/A | N/A | N/A | N/A | -54.98% | 63.02% | INSUFFICIENT |
