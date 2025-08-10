# BTIS – Bitcoin Top Indicator Score

A tiny website that shows a single **Bitcoin Top Indicator Score (BTIS)** and updates it **daily** via GitHub Actions.

**Live data sources**
- **Price & history**: CoinGecko API (for RSI & log-range percentile)
- **Sentiment**: Alternative.me Crypto Fear & Greed Index
- **Funding rate**: Binance Futures API (BTCUSDT last funding rate)
- **MVRV Z-Score** (optional): Glassnode API — add a free key as a GitHub Secret to enable

> If you don't provide a `GLASSNODE_API_KEY`, the script will **skip** the MVRV component and automatically re-weight the other components proportionally.

## Components & Weights
- RSI(14) – 20%
- MVRV Z-Score – 25% (optional)
- Fear & Greed – 20%
- Price vs Log Range – 20%
- Funding (8h %) – 15%

Normalization heuristics:
- RSI: 30→0, 80→100
- MVRV Z: 0→0, 9→100 (cycle-top-ish near 9 historically)
- Fear & Greed: already 0–100
- Price vs Log Range: percentile of log(price) over full history
- Funding: 0.00%→0, 0.10%→100 (per 8h). Tweak in `scripts/btis.py` if desired.

## Quick Start (Local)
```bash
python3 -m http.server 8080
# open http://localhost:8080
python scripts/btis.py  # generates data/btis.json
```

## Deploy to GitHub Pages
1. Create a new GitHub repo and push these files.
2. In **Settings → Pages**, set the Source to `Deploy from a branch` and choose the branch (e.g., `main`) and root (`/`).
3. In **Settings → Secrets and variables → Actions → New repository secret**, add `GLASSNODE_API_KEY` (optional).
4. The included workflow updates `data/btis.json` **daily at 13:15 UTC**. You can also trigger it manually via **Actions → Update BTIS daily → Run workflow**.

## Customization
- Edit weights or normalization in `scripts/btis.py`.
- Adjust schedule in `.github/workflows/update-btis.yml` (CRON).
- Add more components (e.g., funding breadth across exchanges) as you like.

## Disclaimer
For educational purposes only. No financial advice.
