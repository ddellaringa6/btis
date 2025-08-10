#!/usr/bin/env python3
"""
BTIS updater (no MVRV version)
- Fetches free data only:
  * RSI(14) from CoinGecko daily prices
  * Sentiment from Alternative.me Fear & Greed (0–100)
  * Funding rate (last 8h) from Binance Futures (BTCUSDT)
  * Price "log curve" proxy: percentile of log(price) vs history
- Weights are renormalized automatically across the 4 components.
Writes data/btis.json
"""
import os, math, json, datetime, urllib.request

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEARGREED_API = "https://api.alternative.me/fng/?limit=1"
BINANCE_FUNDING_LAST = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1"

OUTFILE = os.path.join(os.path.dirname(__file__), "..", "data", "btis.json")

# ---------- helpers ----------
def http_get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i-1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis = []
    for i in range(period, len(gains)):
        gain = gains[i]; loss = losses[i]
        avg_gain = (avg_gain*(period-1) + gain) / period
        avg_loss = (avg_loss*(period-1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
        rsis.append(100 - (100 / (1 + rs)))
    return rsis[-1] if rsis else None

def normalize(value, lo, hi, clip=True):
    if value is None: return None
    if hi == lo: return 0
    x = 100 * (value - lo) / (hi - lo)
    if clip: x = max(0, min(100, x))
    return x

def weighted_mean(pairs):
    # pairs: list of (value, weight); None values skipped; weights renormalized.
    vals = [(v,w) for v,w in pairs if v is not None and w > 0]
    if not vals: return None
    total_w = sum(w for _,w in vals)
    return sum(v*w for v,w in vals) / total_w

# ---------- fetch data ----------
def fetch_prices_days(days=4000):
    url = f"{COINGECKO_BASE}/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
    j = http_get_json(url)
    return [p[1] for p in j["prices"]]

def fetch_feargreed():
    j = http_get_json(FEARGREED_API)
    return float(j["data"][0]["value"])

def fetch_funding_last():
    j = http_get_json(BINANCE_FUNDING_LAST)
    if not j: return None
    return float(j[0]["fundingRate"]) * 100  # percent per 8h

# ---------- compute ----------
def compute_components():
    prices = fetch_prices_days(4000)
    last_price = prices[-1]

    # RSI from recent window
    rsi_val = rsi(prices[-250:], period=14)
    rsi_norm = normalize(rsi_val, 30, 80)

    # Price vs "log curve": percentile of log(price) vs full history
    logs = [math.log(p) for p in prices if p > 0]
    price_pct = normalize(math.log(last_price), min(logs), max(logs))

    feargreed = fetch_feargreed()               # already 0–100
    funding_pct_8h = fetch_funding_last()       # percent per 8h
    funding_norm = normalize(funding_pct_8h, 0.0, 0.10)  # 0.10% ~ overheated

    components = [
        {"name": "RSI(14)", "normalized": rsi_norm, "detail": f"{rsi_val:.2f}" if rsi_val is not None else "—"},
        {"name": "Fear & Greed", "normalized": feargreed, "detail": f"{feargreed:.0f}"},
        {"name": "Price vs Log Range", "normalized": price_pct, "detail": f"{price_pct:.0f} pctile"},
        {"name": "Funding Rate (8h %)", "normalized": funding_norm, "detail": f"{funding_pct_8h:.4f}%" if funding_pct_8h is not None else "n/a"},
    ]
    return components

def compute_btis(components):
    # Base weights (same ratios as before, minus MVRV, then auto-renormalized)
    weights = {
        "RSI(14)": 0.20,
        "Fear & Greed": 0.20,
        "Price vs Log Range": 0.20,
        "Funding Rate (8h %)": 0.15
    }
    pairs = []
    for comp in components:
        w = weights.get(comp["name"], 0)
        pairs.append((comp["normalized"], w))
    return weighted_mean(pairs)

def main():
    comps = compute_components()
    btis = compute_btis(comps)
    out = {
        "btis": btis,
        "components": comps,  # no MVRV component included
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote", OUTFILE)

if __name__ == "__main__":
    main()

