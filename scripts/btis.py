#!/usr/bin/env python3
"""
BTIS updater (no MVRV, Binance klines instead of CoinGecko)
- Price history: Binance spot klines (BTCUSDT, 1d) — no API key required
- Sentiment: Alternative.me Fear & Greed (0–100)
- Funding rate: Binance Futures last funding (BTCUSDT)
- Price "log curve" proxy: percentile of log(close) vs history
- RSI(14) computed from closes
Writes data/btis.json
"""
import os, math, json, datetime, time, urllib.request, urllib.parse

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
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
        ch = values[i] - values[i-1]
        gains.append(max(ch, 0))
        losses.append(abs(min(ch, 0)))
    if len(gains) < period: return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis = []
    for i in range(period, len(gains)):
        g, l = gains[i], losses[i]
        avg_gain = (avg_gain*(period-1) + g) / period
        avg_loss = (avg_loss*(period-1) + l) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        rsis.append(100 - 100/(1+rs))
    return rsis[-1] if rsis else None

def normalize(value, lo, hi, clip=True):
    if value is None: return None
    if hi == lo: return 0
    x = 100 * (value - lo) / (hi - lo)
    if clip: x = max(0, min(100, x))
    return x

def weighted_mean(pairs):
    vals = [(v,w) for v,w in pairs if v is not None and w > 0]
    if not vals: return None
    tw = sum(w for _,w in vals)
    return sum(v*w for v,w in vals) / tw

# ---------- data fetchers ----------
def fetch_binance_closes(days=2000):
    """
    Get up to ~2000 daily closes from Binance spot klines (BTCUSDT).
    Binance returns max 1000 per call; we page using startTime.
    """
    closes = []
    limit = 1000
    end_ms = int(time.time()*1000)
    # pull newest 1000 first
    params = {"symbol":"BTCUSDT","interval":"1d","limit":limit,"endTime":end_ms}
    url = BINANCE_KLINES + "?" + urllib.parse.urlencode(params)
    batch = http_get_json(url)
    closes = [float(k[4]) for k in batch] + closes
    # If we need more, page backwards once
    if days > len(closes):
        start_ms = int(batch[0][0]) - 1  # start just before first candle
        params2 = {"symbol":"BTCUSDT","interval":"1d","limit":limit,"endTime":start_ms}
        url2 = BINANCE_KLINES + "?" + urllib.parse.urlencode(params2)
        batch2 = http_get_json(url2)
        closes = [float(k[4]) for k in batch2] + closes
    # trim to requested days if longer
    return closes[-days:]

def fetch_feargreed():
    j = http_get_json(FEARGREED_API)
    return float(j["data"][0]["value"])

def fetch_funding_last():
    j = http_get_json(BINANCE_FUNDING_LAST)
    if not j: return None
    return float(j[0]["fundingRate"]) * 100  # percent per 8h

# ---------- compute ----------
def compute_components():
    closes = fetch_binance_closes(2000)  # ~5.5 years is not possible w/ 2 calls, but 2000 days is ~5.5 yrs? (actually ~5.5 yrs)
    last_close = closes[-1]

    rsi_val = rsi(closes[-250:], period=14)
    rsi_norm = normalize(rsi_val, 30, 80)

    logs = [math.log(p) for p in closes if p > 0]
    price_pct = normalize(math.log(last_close), min(logs), max(logs))

    feargreed = fetch_feargreed()              # 0–100
    funding_pct_8h = fetch_funding_last()      # percent per 8h
    funding_norm = normalize(funding_pct_8h, 0.0, 0.10)

    components = [
        {"name": "RSI(14)", "normalized": rsi_norm, "detail": f"{rsi_val:.2f}" if rsi_val is not None else "—"},
        {"name": "Fear & Greed", "normalized": feargreed, "detail": f"{feargreed:.0f}"},
        {"name": "Price vs Log Range", "normalized": price_pct, "detail": f"{price_pct:.0f} pctile"},
        {"name": "Funding Rate (8h %)", "normalized": funding_norm, "detail": f"{funding_pct_8h:.4f}%" if funding_pct_8h is not None else "n/a"},
    ]
    return components

def compute_btis(components):
    # Weights (renormalized across these 4 components)
    weights = {
        "RSI(14)": 0.20,
        "Fear & Greed": 0.20,
        "Price vs Log Range": 0.20,
        "Funding Rate (8h %)": 0.15
    }
    pairs = [(c["normalized"], weights.get(c["name"], 0)) for c in components]
    return weighted_mean(pairs)

def main():
    comps = compute_components()
    btis = compute_btis(comps)
    out = {
        "btis": btis,
        "components": comps,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote", OUTFILE)

if __name__ == "__main__":
    main()
