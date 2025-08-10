#!/usr/bin/env python3
"""
BTIS updater (no MVRV; CoinCap for price history)
- Price history: CoinCap daily history (BTC) – no API key
- Sentiment: Alternative.me Fear & Greed (0–100)
- Funding: Binance Futures last funding (BTCUSDT)
- RSI(14) from closes; price percentile from log(closes)
Writes data/btis.json
"""
import os, math, json, datetime, urllib.request, urllib.parse, time

COINCAP_HISTORY = "https://api.coincap.io/v2/assets/bitcoin/history"
FEARGREED_API = "https://api.alternative.me/fng/?limit=1"
BINANCE_FUNDING_LAST = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1"

OUTFILE = os.path.join(os.path.dirname(__file__), "..", "data", "btis.json")

def http_get_json(url, headers=None):
    h = {"User-Agent":"btis-bot"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
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
    out = []
    for i in range(period, len(gains)):
        g, l = gains[i], losses[i]
        avg_gain = (avg_gain*(period-1) + g) / period
        avg_loss = (avg_loss*(period-1) + l) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        out.append(100 - 100/(1+rs))
    return out[-1] if out else None

def normalize(v, lo, hi, clip=True):
    if v is None: return None
    if hi == lo: return 0
    x = 100 * (v - lo) / (hi - lo)
    return max(0, min(100, x)) if clip else x

def weighted_mean(pairs):
    vals = [(v,w) for v,w in pairs if v is not None and w > 0]
    if not vals: return None
    tw = sum(w for _,w in vals)
    return sum(v*w for v,w in vals) / tw

def fetch_coincap_daily(days=1095):
    # ~3 years of daily data (CoinCap interval d1)
    now = int(time.time()*1000)
    start = now - days*24*60*60*1000
    params = {"interval":"d1","start":str(start),"end":str(now)}
    url = COINCAP_HISTORY + "?" + urllib.parse.urlencode(params)
    j = http_get_json(url)
    data = j.get("data", [])
    closes = [float(row["priceUsd"]) for row in data]
    return closes

def fetch_feargreed():
    j = http_get_json(FEARGREED_API)
    return float(j["data"][0]["value"])

def fetch_funding_last():
    j = http_get_json(BINANCE_FUNDING_LAST)
    if not j: return None
    return float(j[0]["fundingRate"]) * 100  # percent per 8h

def compute_components():
    closes = fetch_coincap_daily(1095)  # ~3 years
    last_close = closes[-1]

    rsi_val = rsi(closes[-250:], 14)
    rsi_norm = normalize(rsi_val, 30, 80)

    logs = [math.log(p) for p in closes if p > 0]
    price_pct = normalize(math.log(last_close), min(logs), max(logs))

    feargreed = fetch_feargreed()
    funding_pct_8h = fetch_funding_last()
    funding_norm = normalize(funding_pct_8h, 0.0, 0.10)

    components = [
        {"name":"RSI(14)", "normalized": rsi_norm, "detail": f"{rsi_val:.2f}" if rsi_val is not None else "—"},
        {"name":"Fear & Greed", "normalized": feargreed, "detail": f"{feargreed:.0f}"},
        {"name":"Price vs Log Range", "normalized": price_pct, "detail": f"{price_pct:.0f} pctile"},
        {"name":"Funding Rate (8h %)", "normalized": funding_norm, "detail": f"{funding_pct_8h:.4f}%" if funding_pct_8h is not None else "n/a"},
    ]
    return components

def compute_btis(components):
    weights = {
        "RSI(14)": 0.20,
        "Fear & Greed": 0.20,
        "Price vs Log Range": 0.20,
        "Funding Rate (8h %)": 0.15
    }
    pairs = [(c["normalized"], weights.get(c["name"],0)) for c in components]
    return weighted_mean(pairs)

def main():
    comps = compute_components()
    btis = compute_btis(comps)
    out = {"btis": btis, "components": comps, "generated_at": datetime.datetime.utcnow().isoformat()+"Z"}
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote", OUTFILE)

if __name__ == "__main__":
    main()

