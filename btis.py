#!/usr/bin/env python3
"""
BTIS updater
- Fetches data from public APIs
- Computes:
  * RSI(14) from CoinGecko daily prices
  * Sentiment from Alternative.me Fear & Greed
  * Funding rate from Binance Futures (last value)
  * Price "log curve" proxy: percentile of log price vs history
  * MVRV Z-Score from Glassnode if GLASSNODE_API_KEY is set (optional)
- Re-weights components automatically if MVRV is unavailable.
Writes data/btis.json
"""
import os, math, time, json, statistics, datetime, urllib.request

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEARGREED_API = "https://api.alternative.me/fng/?limit=1"
BINANCE_FUNDING_LAST = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1"
GLASSNODE_Z = "https://api.glassnode.com/v1/metrics/market/mvrv_z_score?api_key={key}&a=BTC&i=1d"

OUTFILE = os.path.join(os.path.dirname(__file__), "..", "data", "btis.json")

# -------------- helpers --------------
def http_get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def rsi(values, period=14):
    # Classic Wilder's RSI using simple averages
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
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain*(period-1) + gain) / period
        avg_loss = (avg_loss*(period-1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
        rsis.append(100 - (100 / (1 + rs)))
    return rsis[-1] if rsis else None

def normalize(value, lo, hi, clip=True):
    if value is None: return None
    if hi == lo: return 0
    x = 100 * (value - lo) / (hi - lo)
    if clip:
        x = max(0, min(100, x))
    return x

def weighted_mean(pairs):
    # pairs: list of (value, weight). None values are skipped, weights renormalized.
    vals = [(v,w) for v,w in pairs if v is not None and w > 0]
    if not vals: return None
    total_w = sum(w for _,w in vals)
    return sum(v*w for v,w in vals) / total_w

# -------------- fetch data --------------
def fetch_prices_days(days=1825):  # ~5 years, hourly not needed
    url = f"{COINGECKO_BASE}/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
    j = http_get_json(url)
    prices = [p[1] for p in j["prices"]]
    return prices

def fetch_feargreed():
    j = http_get_json(FEARGREED_API)
    return float(j["data"][0]["value"])

def fetch_funding_last():
    j = http_get_json(BINANCE_FUNDING_LAST)
    if not j: 
        return None
    return float(j[0]["fundingRate"]) * 100  # to percentage

def fetch_mvrv_z():
    key = os.environ.get("GLASSNODE_API_KEY", "").strip()
    if not key:
        return None
    url = GLASSNODE_Z.format(key=key)
    j = http_get_json(url)
    if not j:
        return None
    # last non-null value
    for item in reversed(j):
        if item.get("v") is not None:
            return float(item["v"])
    return None

# -------------- compute components --------------
def compute_components():
    prices = fetch_prices_days(4000)  # long history for percentile
    last_price = prices[-1]
    # RSI(14) from last ~200 days subset for stability
    rsi_val = rsi(prices[-250:], period=14)

    # Price vs "log curve": percentile of log price across full history
    logs = [math.log(p) for p in prices if p > 0]
    pct = normalize(math.log(last_price), min(logs), max(logs))

    feargreed = fetch_feargreed()  # 0..100 already
    funding_pct_per_8h = fetch_funding_last()  # percent per 8h

    # Normalize funding: 0 -> 0, 0.03% -> 50, 0.1% -> 100 (heuristic)
    funding_norm = None
    if funding_pct_per_8h is not None:
        funding_norm = normalize(funding_pct_per_8h, 0.0, 0.10)

    # MVRV Z, if available
    mvrv_z = fetch_mvrv_z()
    mvrv_norm = normalize(mvrv_z, 0.0, 9.0) if mvrv_z is not None else None

    components = [
        {"name": "RSI(14)", "normalized": normalize(rsi_val, 30, 80), "detail": f"{rsi_val:.2f}" if rsi_val is not None else "—"},
        {"name": "MVRV Z-Score", "normalized": mvrv_norm, "detail": f"{mvrv_z:.2f}" if mvrv_z is not None else "n/a"},
        {"name": "Fear & Greed", "normalized": feargreed, "detail": f"{feargreed:.0f}"},
        {"name": "Price vs Log Range", "normalized": pct, "detail": f"{pct:.0f} pctile"},
        {"name": "Funding Rate (8h %)", "normalized": funding_norm, "detail": f"{funding_pct_per_8h:.4f}%" if funding_pct_per_8h is not None else "n/a"},
    ]
    return components

def compute_btis(components):
    weights = {
        "RSI(14)": 0.20,
        "MVRV Z-Score": 0.25,
        "Fear & Greed": 0.20,
        "Price vs Log Range": 0.20,
        "Funding Rate (8h %)": 0.15
    }
    pairs = []
    for comp in components:
        name = comp["name"]
        w = weights[name]
        v = comp["normalized"]
        pairs.append((v, w))
    score = weighted_mean(pairs)
    return score

def main():
    comps = compute_components()
    btis = compute_btis(comps)
    out = {
        "btis": btis,
        "components": comps,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    with open(OUTFILE, "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote", OUTFILE)

if __name__ == "__main__":
    main()
