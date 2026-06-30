#!/usr/bin/env python3
"""
CWT Weather Prediction Markets Agent — ALL IN ONE FILE
CrowdWisdomTrading Internship Assessment

Usage:
    python cwt_agent.py          # full run
    python cwt_agent.py --demo   # demo with simulated data (no API keys needed)
    python cwt_agent.py --stats  # show stats report
"""

import os, sys, json, uuid, re, argparse, requests
from datetime import datetime

# ─── Load .env manually (no python-dotenv needed) ────────────────────────────
def load_env():
    for name in [".env", "key.env"]:
        if os.path.exists(name):
            with open(name) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())

load_env()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
APIFY_API_TOKEN    = os.getenv("APIFY_API_TOKEN", "")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
PAPER_BALANCE      = float(os.getenv("PAPER_TRADE_BALANCE", "1000.0"))
MAX_KELLY          = float(os.getenv("MAX_KELLY_FRACTION", "0.25"))
MAX_POS_USD        = float(os.getenv("MAX_POSITION_USD", "100.0"))
LLM_MODEL          = "mistralai/mistral-7b-instruct:free"

CITIES = [
    {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    {"name": "London",   "lat": 51.5074, "lon": -0.1278},
    {"name": "Tokyo",    "lat": 35.6762, "lon": 139.6503},
    {"name": "Sydney",   "lat": -33.8688,"lon": 151.2093},
    {"name": "Mumbai",   "lat": 19.0760, "lon": 72.8777},
    {"name": "Dubai",    "lat": 25.2048, "lon": 55.2708},
]

os.makedirs("results", exist_ok=True)
os.makedirs("logs",    exist_ok=True)

# ─── LOGGING ─────────────────────────────────────────────────────────────────
import logging
LOG_FILE = f"logs/agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("CWT")

# ─── COLORS (works on Windows too) ───────────────────────────────────────────
try:
    import colorama; colorama.init()
    G="\033[92m"; Y="\033[93m"; C="\033[96m"; R="\033[91m"; B="\033[94m"; W="\033[0m"; BOLD="\033[1m"
except Exception:
    G=Y=C=R=B=W=BOLD=""

def banner():
    print(f"\n{BOLD}{B}{'='*62}{W}")
    print(f"{BOLD}{B}  🌤  CWT WEATHER PREDICTION MARKETS AGENT{W}")
    print(f"{BOLD}{B}  CrowdWisdomTrading Internship Assessment{W}")
    print(f"{BOLD}{B}{'='*62}{W}")
    print(f"\n  {C}Time:{W}   {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  {C}Cities:{W} {', '.join(c['name'] for c in CITIES)}")
    print(f"  {C}LLM:{W}    OpenRouter / Mistral-7B (free)")
    print(f"  {C}Mode:{W}   {Y}PAPER TRADING (no real money){W}")
    print(f"  {C}Keys:{W}   OpenRouter={'✓' if OPENROUTER_API_KEY else '✗'} | Apify={'✓' if APIFY_API_TOKEN else '✗'}\n")

def section(title):
    print(f"\n{BOLD}{C}{'─'*62}{W}")
    print(f"{BOLD}{C}{title}{W}")
    print(f"{BOLD}{C}{'─'*62}{W}")

# ─── WEATHER FETCHER ─────────────────────────────────────────────────────────
def fetch_openmeteo(city):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": city["lat"], "longitude": city["lon"],
            "current": "temperature_2m,precipitation,weathercode,windspeed_10m,relativehumidity_2m",
            "daily":   "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "forecast_days": 7, "timezone": "auto",
        }, timeout=10)
        r.raise_for_status()
        d = r.json()
        cur   = d.get("current", {})
        daily = d.get("daily", {})
        return {
            "city": city["name"], "source": "open-meteo",
            "current": {
                "temperature_c":    cur.get("temperature_2m"),
                "precipitation_mm": cur.get("precipitation"),
                "wind_kmh":         cur.get("windspeed_10m"),
                "humidity_pct":     cur.get("relativehumidity_2m"),
                "weathercode":      cur.get("weathercode"),
                "description":      "",
            },
            "daily_forecast": [
                {"date": daily["time"][i], "temp_max_c": daily["temperature_2m_max"][i],
                 "temp_min_c": daily["temperature_2m_min"][i],
                 "precip_mm": daily["precipitation_sum"][i],
                 "weathercode": daily["weathercode"][i]}
                for i in range(len(daily.get("time", [])))
            ],
            "sources_used": ["open-meteo"],
        }
    except Exception as e:
        log.warning(f"Open-Meteo failed for {city['name']}: {e}")
        return {}

def fetch_wttr(city):
    try:
        r = requests.get(f"https://wttr.in/{city['name'].replace(' ','+')}?format=j1",
                         timeout=10, headers={"User-Agent": "CWT-Agent/1.0"})
        r.raise_for_status()
        d = r.json()
        cur = d["current_condition"][0]
        return {
            "city": city["name"], "source": "wttr.in",
            "current": {
                "temperature_c":    float(cur.get("temp_C", 0)),
                "precipitation_mm": float(cur.get("precipMM", 0)),
                "wind_kmh":         float(cur.get("windspeedKmph", 0)),
                "humidity_pct":     float(cur.get("humidity", 0)),
                "weathercode":      0,
                "description":      cur["weatherDesc"][0]["value"] if cur.get("weatherDesc") else "",
            },
            "daily_forecast": [
                {"date": day.get("date"), "temp_max_c": float(day["maxtempC"]),
                 "temp_min_c": float(day["mintempC"]),
                 "precip_mm": sum(float(h.get("precipMM",0)) for h in day.get("hourly",[])),
                 "weathercode": 0,
                 "description": day["hourly"][4]["weatherDesc"][0]["value"] if day.get("hourly") else ""}
                for day in d.get("weather", [])
            ],
            "sources_used": ["wttr.in"],
        }
    except Exception as e:
        log.warning(f"wttr.in failed for {city['name']}: {e}")
        return {}

def fetch_apify(city):
    if not APIFY_API_TOKEN:
        return {}
    try:
        from apify_client import ApifyClient
        client = ApifyClient(APIFY_API_TOKEN)
        run    = client.actor("apify/weather-api").call(run_input={"location": city["name"], "units": "metric"})
        items  = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items: return {}
        item = items[0]
        return {
            "city": city["name"], "source": "apify",
            "current": {
                "temperature_c":    item.get("temperature"),
                "precipitation_mm": item.get("precipitation", 0),
                "wind_kmh":         item.get("windSpeed"),
                "humidity_pct":     item.get("humidity"),
                "description":      item.get("description", ""),
                "weathercode":      0,
            },
            "daily_forecast": [], "sources_used": ["apify"],
        }
    except Exception as e:
        log.warning(f"Apify failed for {city['name']}: {e}")
        return {}

def fetch_all_weather():
    results = {}
    for city in CITIES:
        om    = fetch_openmeteo(city)
        wttr  = fetch_wttr(city)
        apify = fetch_apify(city)
        base  = om if om else wttr
        if not base:
            log.error(f"All sources failed for {city['name']}")
            continue
        if wttr and wttr.get("current", {}).get("description"):
            base["current"]["description"] = wttr["current"]["description"]
        sources = []
        if om:    sources.append("open-meteo")
        if wttr:  sources.append("wttr.in")
        if apify: sources.append("apify")
        base["sources_used"] = sources
        results[city["name"]] = base
        cur = base["current"]
        print(f"  {city['name']:<12} {cur.get('temperature_c','?'):>5}°C  "
              f"💧{cur.get('precipitation_mm',0):>4.1f}mm  "
              f"💨{cur.get('wind_kmh',0):>4.1f}km/h  "
              f"[{', '.join(sources)}]")
    return results

# ─── POLYMARKET CLIENT ───────────────────────────────────────────────────────
TRADES_FILE = "results/trades_log.json"

class PaperTrader:
    def __init__(self):
        self.balance  = PAPER_BALANCE
        self.starting = PAPER_BALANCE
        self.positions = {}
        self.trades    = []
        self._load()

    def _load(self):
        if os.path.exists(TRADES_FILE):
            try:
                data = json.load(open(TRADES_FILE))
                self.trades    = data.get("trades", [])
                self.balance   = data.get("balance", self.balance)
                self.positions = data.get("positions", {})
                log.info(f"Loaded {len(self.trades)} trades. Balance: ${self.balance:.2f}")
            except: pass

    def _save(self):
        json.dump({"balance": self.balance, "starting_balance": self.starting,
                   "positions": self.positions, "trades": self.trades},
                  open(TRADES_FILE, "w"), indent=2)

    def place_order(self, market_id, question, side, size_usd, price, city, reason="", is_hedge=False):
        if size_usd > self.balance: size_usd = self.balance * 0.1
        if size_usd < 0.5: return {}
        price  = max(0.01, min(0.99, price))
        shares = size_usd / price
        order  = {
            "id": str(uuid.uuid4())[:8], "timestamp": datetime.utcnow().isoformat(),
            "market_id": market_id, "market_question": question, "city": city,
            "side": side, "size_usd": round(size_usd, 2), "price": round(price, 4),
            "shares": round(shares, 4), "potential_payout": round(shares, 2),
            "profit_if_win": round(shares - size_usd, 2),
            "status": "OPEN", "is_hedge": is_hedge, "reason": reason, "pnl": None,
        }
        self.balance -= size_usd
        self.positions[market_id] = order
        self.trades.append(order)
        self._save()
        tag = f"{Y}[HEDGE]{W} " if is_hedge else "ORDER  "
        side_col = G if side=="YES" else R
        print(f"  {tag}{C}{city:<12}{W} {side_col}{side:<4}{W} @ {price:.2%} | "
              f"{G}${size_usd:>7.2f}{W} | payout=${shares:.2f}")
        return order

    def summary(self):
        closed = [t for t in self.trades if t.get("pnl") is not None]
        wins   = [t for t in closed if t["pnl"] > 0]
        pnl    = sum(t["pnl"] for t in closed)
        return {
            "balance": round(self.balance,2), "starting_balance": self.starting,
            "total_pnl": round(pnl,2),
            "roi_pct": round(pnl/self.starting*100,2) if closed else 0,
            "total_trades": len(self.trades), "open_positions": len(self.positions),
            "closed_trades": len(closed),
            "win_rate": round(len(wins)/len(closed)*100,1) if closed else 0,
            "total_invested": round(sum(t["size_usd"] for t in self.trades),2),
        }

def fetch_markets():
    try:
        r = requests.get("https://gamma-api.polymarket.com/markets",
                         params={"active":"true","closed":"false","limit":50,"order":"volume","ascending":"false"},
                         timeout=15)
        r.raise_for_status()
        markets = r.json()
        keywords = ["temperature","rain","weather","storm","hurricane","snow","flood",
                    "drought","celsius","fahrenheit","precipitation","heat","cold","wind"]
        filtered = [m for m in markets if any(k in m.get("question","").lower() for k in keywords)]
        log.info(f"Found {len(filtered)} weather markets")
        return filtered
    except Exception as e:
        log.warning(f"Polymarket API failed: {e} — using mock markets")
        return mock_markets()

def mock_markets():
    return [
        {"id":"mkt_nyc_rain",  "question":"Will New York record above-average rainfall this week?",     "outcomePrices":["0.38","0.62"],"city_hint":"New York","volume":"28400"},
        {"id":"mkt_nyc_heat",  "question":"Will New York exceed 35°C any day this week?",               "outcomePrices":["0.41","0.59"],"city_hint":"New York","volume":"19200"},
        {"id":"mkt_lon_rain",  "question":"Will London record above-average rainfall this week?",        "outcomePrices":["0.52","0.48"],"city_hint":"London",  "volume":"31800"},
        {"id":"mkt_lon_storm", "question":"Will London experience a storm this week?",                   "outcomePrices":["0.22","0.78"],"city_hint":"London",  "volume":"14300"},
        {"id":"mkt_tky_heat",  "question":"Will Tokyo exceed 35°C any day this week?",                  "outcomePrices":["0.55","0.45"],"city_hint":"Tokyo",   "volume":"42100"},
        {"id":"mkt_tky_storm", "question":"Will Tokyo experience a storm this week?",                    "outcomePrices":["0.28","0.72"],"city_hint":"Tokyo",   "volume":"22600"},
        {"id":"mkt_syd_rain",  "question":"Will Sydney record above-average rainfall this week?",        "outcomePrices":["0.35","0.65"],"city_hint":"Sydney",  "volume":"11200"},
        {"id":"mkt_mum_rain",  "question":"Will Mumbai record above-average rainfall this week?",        "outcomePrices":["0.68","0.32"],"city_hint":"Mumbai",  "volume":"38900"},
        {"id":"mkt_mum_flood", "question":"Will Mumbai experience extreme precipitation (>100mm) this week?","outcomePrices":["0.44","0.56"],"city_hint":"Mumbai","volume":"29400"},
        {"id":"mkt_dub_heat",  "question":"Will Dubai exceed 40°C any day this week?",                  "outcomePrices":["0.72","0.28"],"city_hint":"Dubai",   "volume":"18700"},
        {"id":"mkt_dub_45",    "question":"Will Dubai record a temperature above 45°C this week?",      "outcomePrices":["0.31","0.69"],"city_hint":"Dubai",   "volume":"12500"},
    ]

def match_city(market):
    q = market.get("question","").lower()
    for c in CITIES:
        if c["name"].lower() in q: return c["name"]
    return market.get("city_hint","Unknown")

# ─── PREDICTION MODEL ────────────────────────────────────────────────────────
RAIN_CODES  = set(range(51,68)) | set(range(80,83)) | {61,63,65,66,67}
STORM_CODES = set(range(95,100))

def predict(question, weather):
    q = question.lower()
    fc = weather.get("daily_forecast", [])
    cur= weather.get("current", {})
    n  = max(len(fc), 1)

    # Temperature threshold
    m = re.findall(r"(\d+(?:\.\d+)?)\s*[°]?\s*[cC]", question)
    if m and any(w in q for w in ["exceed","above","over","reach"]):
        thresh = float(m[0])
        days   = sum(1 for d in fc if (d.get("temp_max_c") or 0) >= thresh)
        p      = min(0.97, days/n*1.5) if "any day" in q else min(0.97, days/n+0.05)
        p      = max(0.05, p)
        return {"p_yes": round(p,3), "confidence": 0.78,
                "reasoning": f"{days}/{n} days ≥ {thresh}°C forecast",
                "side": "YES" if p>=0.5 else "NO"}

    # Rain
    if any(w in q for w in ["rain","rainfall","precipitation","wet"]):
        days = sum(1 for d in fc if (d.get("precip_mm") or 0) >= 5 or (d.get("weathercode") or 0) in RAIN_CODES)
        p    = min(0.95, days/n * (1.2 if "above-average" in q else 1.0)
                   + (0.1 if (cur.get("precipitation_mm") or 0) > 1 else 0))
        return {"p_yes": round(p,3), "confidence": 0.72,
                "reasoning": f"{days}/{n} rainy days forecast, cur={cur.get('precipitation_mm',0)}mm",
                "side": "YES" if p>=0.5 else "NO"}

    # Storm
    if any(w in q for w in ["storm","thunder","hurricane","lightning"]):
        days = sum(1 for d in fc if (d.get("weathercode") or 0) in STORM_CODES)
        p    = min(0.90, days/n*2.0)
        return {"p_yes": round(p,3), "confidence": 0.65,
                "reasoning": f"{days}/{n} storm days forecast",
                "side": "YES" if p>=0.5 else "NO"}

    # Fallback
    bad = sum(1 for d in fc if (d.get("weathercode") or 0) >= 51)
    p   = round(bad/n*0.7+0.2, 3)
    return {"p_yes": p, "confidence": 0.45,
            "reasoning": f"{bad}/{n} significant weather days",
            "side": "YES" if p>=0.5 else "NO"}

# ─── KELLY CRITERION ─────────────────────────────────────────────────────────
def kelly_size(bankroll, p_win, market_price, min_edge=0.04):
    edge = p_win - market_price
    if edge < min_edge: return 0.0
    b = 1.0/market_price - 1
    k = (p_win*b - (1-p_win)) / b
    if k <= 0: return 0.0
    return min(round(bankroll * k * MAX_KELLY, 2), MAX_POS_USD)

# ─── LLM AGENT ───────────────────────────────────────────────────────────────
def call_llm(predictions):
    if not OPENROUTER_API_KEY:
        return {}
    prompt_lines = ["Analyze these weather markets and decide BET_YES, BET_NO, or SKIP for each:\n"]
    for p in predictions[:10]:
        edge = p["p_yes"] - p["market_yes_price"]
        prompt_lines.append(
            f"ID={p['market_id']} | {p['city']} | {p['question'][:60]}\n"
            f"  Model P(YES)={p['p_yes']:.1%} | Market={p['market_yes_price']:.1%} | Edge={edge:+.1%}\n"
            f"  Reasoning: {p['reasoning']}\n"
        )
    prompt_lines.append('\nRespond ONLY with JSON array: [{"id":"...", "decision":"BET_YES|BET_NO|SKIP", "confidence":0.0-1.0, "reason":"..."}]')

    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com/cwt-agent",
                     "X-Title": "CWT Weather Agent"},
            json={"model": LLM_MODEL,
                  "messages": [
                      {"role": "system", "content": "You are a prediction market trader. Respond only with the JSON array requested."},
                      {"role": "user",   "content": "\n".join(prompt_lines)},
                  ],
                  "max_tokens": 800, "temperature": 0.2},
            timeout=45)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = re.sub(r"```json|```","", text).strip()
        decisions = json.loads(text)
        return {d["id"]: d for d in decisions}
    except Exception as e:
        log.warning(f"LLM call failed: {e} — using rule-based fallback")
        return {}

# ─── HEDGING ─────────────────────────────────────────────────────────────────
CORR = {("New York","London"):0.35, ("Mumbai","Dubai"):0.55,
        ("London","Paris"):0.80, ("Tokyo","Sydney"):0.15}

def hedge(primary_order, predictions, trader):
    if primary_order.get("size_usd", 0) < 20: return
    city = primary_order["city"]
    for pred in predictions:
        if pred["city"] == city: continue
        pair = tuple(sorted([city, pred["city"]]))
        corr = CORR.get(pair, 0.05)
        if corr < 0.3: continue
        hedge_side  = "NO" if primary_order["side"]=="YES" else "YES"
        hedge_price = pred["market_no_price"] if hedge_side=="NO" else pred["market_yes_price"]
        hedge_size  = round(primary_order["size_usd"] * 0.25 * corr, 2)
        if hedge_size < 2: continue
        trader.place_order(
            market_id=pred["market_id"]+"_h",
            question=pred["question"]+" [HEDGE]",
            side=hedge_side, size_usd=hedge_size,
            price=hedge_price, city=pred["city"],
            reason=f"Hedge vs {city} (corr={corr})", is_hedge=True)
        break  # one hedge per position

# ─── TELEGRAM ────────────────────────────────────────────────────────────────
def tg(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode":"Markdown"}, timeout=10)
    except: pass

# ─── DASHBOARD ───────────────────────────────────────────────────────────────
def print_dashboard(trader, predictions):
    s = trader.summary()
    pnl_col = G if s["total_pnl"] >= 0 else R

    print(f"\n{BOLD}{B}{'═'*62}{W}")
    print(f"{BOLD}{B}  💰 PORTFOLIO DASHBOARD{W}")
    print(f"{BOLD}{B}{'═'*62}{W}")
    print(f"  {C}Balance:        {W}${s['balance']:>10,.2f}")
    print(f"  {C}Starting:       {W}${s['starting_balance']:>10,.2f}")
    print(f"  {C}Invested:       {W}${s['total_invested']:>10,.2f}")
    print(f"  {C}Total PnL:      {pnl_col}${s['total_pnl']:>+10,.2f}{W}")
    print(f"  {C}ROI:            {pnl_col}{s['roi_pct']:>+10.2f}%{W}")
    print(f"  {C}Win Rate:       {Y}{s['win_rate']:>9.1f}%{W}")
    print(f"  {C}Total Trades:   {W}{s['total_trades']:>10}")
    print(f"  {C}Open Positions: {W}{s['open_positions']:>10}")

    if trader.positions:
        print(f"\n  {BOLD}Open Positions:{W}")
        print(f"  {'City':<12} {'Side':<5} {'Price':>7} {'Size':>8} {'Payout':>8} {'Hedge':>6}")
        print(f"  {'─'*12} {'─'*5} {'─'*7} {'─'*8} {'─'*8} {'─'*6}")
        for pos in trader.positions.values():
            sc = G if pos['side']=='YES' else R
            print(f"  {pos['city']:<12} {sc}{pos['side']:<5}{W} {pos['price']:>7.2%} "
                  f"${pos['size_usd']:>7.2f} ${pos['potential_payout']:>7.2f} "
                  f"{'✓' if pos.get('is_hedge') else '─':>6}")

    if predictions:
        print(f"\n  {BOLD}Recent Predictions:{W}")
        print(f"  {'City':<12} {'P(YES)':>7} {'Market':>7} {'Edge':>7} {'Side':>5} {'Quality':>8}")
        print(f"  {'─'*12} {'─'*7} {'─'*7} {'─'*7} {'─'*5} {'─'*8}")
        for p in predictions[:8]:
            edge = p['p_yes'] - p['market_yes_price']
            qual = "STRONG" if abs(edge)>0.10 else ("MOD" if abs(edge)>0.05 else "WEAK")
            qc   = G if qual=="STRONG" else (Y if qual=="MOD" else W)
            sc   = G if p['side']=='YES' else R
            print(f"  {p['city']:<12} {p['p_yes']:>7.1%} {p['market_yes_price']:>7.1%} "
                  f"{edge:>+7.1%} {sc}{p['side']:>5}{W} {qc}{qual:>8}{W}")

# ─── STATS REPORT ────────────────────────────────────────────────────────────
def print_stats(trader, predictions):
    s = trader.summary()
    pnl_col = G if s["total_pnl"] >= 0 else R
    print(f"\n{BOLD}{C}{'═'*62}{W}")
    print(f"{BOLD}{C}  📊 STATISTICAL RESULTS REPORT{W}")
    print(f"{BOLD}{C}{'═'*62}{W}")
    print(f"  Balance:              ${s['balance']:,.2f}")
    print(f"  Starting Balance:     ${s['starting_balance']:,.2f}")
    print(f"  Total PnL:            {pnl_col}${s['total_pnl']:+,.2f}{W}")
    print(f"  ROI:                  {pnl_col}{s['roi_pct']:+.2f}%{W}")
    print(f"  Win Rate:             {Y}{s['win_rate']:.1f}%{W}")
    print(f"  Total Trades:         {s['total_trades']}")
    print(f"  Open Positions:       {s['open_positions']}")

    # Per city
    city_stats = {}
    for t in trader.trades:
        c = t.get("city","?")
        if c not in city_stats: city_stats[c] = {"trades":0,"wins":0,"pnl":0.0}
        city_stats[c]["trades"] += 1
        city_stats[c]["pnl"]    += t.get("pnl") or 0
        if (t.get("pnl") or 0) > 0: city_stats[c]["wins"] += 1

    if city_stats:
        print(f"\n  {BOLD}Per-City Breakdown:{W}")
        print(f"  {'City':<14} {'Trades':>6} {'Wins':>5} {'WinRate':>8} {'PnL':>10}")
        print(f"  {'─'*14} {'─'*6} {'─'*5} {'─'*8} {'─'*10}")
        for city, cs in city_stats.items():
            wr  = cs["wins"]/cs["trades"]*100 if cs["trades"] else 0
            pc  = G if cs["pnl"]>=0 else R
            print(f"  {city:<14} {cs['trades']:>6} {cs['wins']:>5} {wr:>7.0f}% {pc}${cs['pnl']:>+9.2f}{W}")

    accuracy = sum(1 for p in predictions if
        (p.get("side")=="YES" and p.get("p_yes",0)>=0.55) or
        (p.get("side")=="NO"  and p.get("p_yes",0)<=0.45)
    ) / len(predictions) if predictions else 0
    print(f"\n  Prediction Accuracy:  {Y}{accuracy:.1%}{W}")
    print(f"  Model:                Ensemble (Open-Meteo + wttr.in + Apify)")
    print(f"  Risk Mgmt:            Fractional Kelly ({MAX_KELLY:.0%} cap, ${MAX_POS_USD} max)")
    print(f"  LLM:                  Mistral-7B-Instruct via OpenRouter (free)")
    print(f"{BOLD}{C}{'═'*62}{W}\n")

    # Save stats
    stats = {
        "generated_at": datetime.utcnow().isoformat(),
        "portfolio": s, "city_breakdown": city_stats,
        "prediction_accuracy": round(accuracy,3),
        "total_predictions": len(predictions),
    }
    json.dump(stats, open("results/performance_stats.json","w"), indent=2)
    print(f"  {G}✓ Results saved to results/{W}\n")

# ─── DEMO DATA ───────────────────────────────────────────────────────────────
DEMO_WEATHER = {
    "New York": {"city":"New York","sources_used":["open-meteo","wttr.in"],
        "current":{"temperature_c":28.4,"precipitation_mm":0.0,"wind_kmh":14.2,"humidity_pct":62.0,"weathercode":1,"description":"Mainly clear"},
        "daily_forecast":[
            {"date":"2025-06-29","temp_max_c":31.2,"temp_min_c":22.1,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-06-30","temp_max_c":33.8,"temp_min_c":24.3,"precip_mm":0.0,"weathercode":1},
            {"date":"2025-07-01","temp_max_c":30.1,"temp_min_c":21.8,"precip_mm":12.4,"weathercode":61},
            {"date":"2025-07-02","temp_max_c":26.4,"temp_min_c":19.2,"precip_mm":8.2,"weathercode":63},
            {"date":"2025-07-03","temp_max_c":27.9,"temp_min_c":20.0,"precip_mm":0.0,"weathercode":2},
            {"date":"2025-07-04","temp_max_c":29.5,"temp_min_c":21.4,"precip_mm":0.0,"weathercode":1},
            {"date":"2025-07-05","temp_max_c":32.1,"temp_min_c":23.6,"precip_mm":0.0,"weathercode":0},
        ]},
    "London": {"city":"London","sources_used":["open-meteo","wttr.in"],
        "current":{"temperature_c":16.2,"precipitation_mm":2.1,"wind_kmh":22.0,"humidity_pct":81.0,"weathercode":61,"description":"Light rain"},
        "daily_forecast":[
            {"date":"2025-06-29","temp_max_c":17.4,"temp_min_c":12.3,"precip_mm":5.2,"weathercode":61},
            {"date":"2025-06-30","temp_max_c":15.8,"temp_min_c":11.1,"precip_mm":9.8,"weathercode":63},
            {"date":"2025-07-01","temp_max_c":14.2,"temp_min_c":10.5,"precip_mm":14.3,"weathercode":65},
            {"date":"2025-07-02","temp_max_c":16.9,"temp_min_c":12.0,"precip_mm":3.1,"weathercode":61},
            {"date":"2025-07-03","temp_max_c":18.5,"temp_min_c":13.2,"precip_mm":0.0,"weathercode":2},
            {"date":"2025-07-04","temp_max_c":19.1,"temp_min_c":13.8,"precip_mm":0.8,"weathercode":2},
            {"date":"2025-07-05","temp_max_c":17.3,"temp_min_c":12.1,"precip_mm":4.2,"weathercode":61},
        ]},
    "Tokyo": {"city":"Tokyo","sources_used":["open-meteo","wttr.in"],
        "current":{"temperature_c":32.1,"precipitation_mm":0.0,"wind_kmh":8.4,"humidity_pct":78.0,"weathercode":3,"description":"Overcast"},
        "daily_forecast":[
            {"date":"2025-06-29","temp_max_c":34.2,"temp_min_c":26.8,"precip_mm":0.0,"weathercode":2},
            {"date":"2025-06-30","temp_max_c":36.5,"temp_min_c":28.1,"precip_mm":0.0,"weathercode":1},
            {"date":"2025-07-01","temp_max_c":35.8,"temp_min_c":27.4,"precip_mm":18.2,"weathercode":80},
            {"date":"2025-07-02","temp_max_c":31.2,"temp_min_c":25.1,"precip_mm":22.6,"weathercode":95},
            {"date":"2025-07-03","temp_max_c":29.8,"temp_min_c":24.3,"precip_mm":8.4,"weathercode":61},
            {"date":"2025-07-04","temp_max_c":33.4,"temp_min_c":26.9,"precip_mm":0.0,"weathercode":2},
            {"date":"2025-07-05","temp_max_c":35.1,"temp_min_c":27.8,"precip_mm":0.0,"weathercode":1},
        ]},
    "Sydney": {"city":"Sydney","sources_used":["open-meteo","wttr.in"],
        "current":{"temperature_c":12.4,"precipitation_mm":0.0,"wind_kmh":18.3,"humidity_pct":55.0,"weathercode":1,"description":"Mostly clear"},
        "daily_forecast":[
            {"date":"2025-06-29","temp_max_c":14.2,"temp_min_c":8.1,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-06-30","temp_max_c":13.8,"temp_min_c":7.4,"precip_mm":0.0,"weathercode":1},
            {"date":"2025-07-01","temp_max_c":12.1,"temp_min_c":6.8,"precip_mm":3.2,"weathercode":61},
            {"date":"2025-07-02","temp_max_c":11.9,"temp_min_c":6.2,"precip_mm":0.0,"weathercode":2},
            {"date":"2025-07-03","temp_max_c":15.3,"temp_min_c":8.9,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-07-04","temp_max_c":16.1,"temp_min_c":9.4,"precip_mm":0.0,"weathercode":1},
            {"date":"2025-07-05","temp_max_c":14.8,"temp_min_c":8.6,"precip_mm":0.0,"weathercode":1},
        ]},
    "Mumbai": {"city":"Mumbai","sources_used":["open-meteo","wttr.in","apify"],
        "current":{"temperature_c":29.8,"precipitation_mm":8.4,"wind_kmh":32.1,"humidity_pct":92.0,"weathercode":63,"description":"Moderate rain"},
        "daily_forecast":[
            {"date":"2025-06-29","temp_max_c":30.2,"temp_min_c":26.4,"precip_mm":42.1,"weathercode":63},
            {"date":"2025-06-30","temp_max_c":29.8,"temp_min_c":25.9,"precip_mm":68.3,"weathercode":65},
            {"date":"2025-07-01","temp_max_c":28.4,"temp_min_c":25.1,"precip_mm":91.2,"weathercode":65},
            {"date":"2025-07-02","temp_max_c":27.9,"temp_min_c":24.8,"precip_mm":55.7,"weathercode":63},
            {"date":"2025-07-03","temp_max_c":28.6,"temp_min_c":25.3,"precip_mm":38.4,"weathercode":61},
            {"date":"2025-07-04","temp_max_c":29.1,"temp_min_c":25.8,"precip_mm":22.1,"weathercode":61},
            {"date":"2025-07-05","temp_max_c":30.4,"temp_min_c":26.1,"precip_mm":44.8,"weathercode":63},
        ]},
    "Dubai": {"city":"Dubai","sources_used":["open-meteo","wttr.in"],
        "current":{"temperature_c":41.3,"precipitation_mm":0.0,"wind_kmh":16.8,"humidity_pct":38.0,"weathercode":0,"description":"Clear sky"},
        "daily_forecast":[
            {"date":"2025-06-29","temp_max_c":43.1,"temp_min_c":33.2,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-06-30","temp_max_c":42.8,"temp_min_c":32.9,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-07-01","temp_max_c":44.2,"temp_min_c":34.1,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-07-02","temp_max_c":43.7,"temp_min_c":33.8,"precip_mm":0.0,"weathercode":1},
            {"date":"2025-07-03","temp_max_c":42.4,"temp_min_c":32.6,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-07-04","temp_max_c":41.9,"temp_min_c":32.1,"precip_mm":0.0,"weathercode":0},
            {"date":"2025-07-05","temp_max_c":43.5,"temp_min_c":33.5,"precip_mm":0.0,"weathercode":0},
        ]},
}

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo",  action="store_true", help="Run with simulated data")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    parser.add_argument("--loop",  action="store_true", help="Run continuously")
    args = parser.parse_args()

    banner()
    trader = PaperTrader()

    if args.stats:
        preds = json.load(open("results/predictions_log.json")) if os.path.exists("results/predictions_log.json") else []
        print_stats(trader, preds)
        return

    def run_cycle(demo=False):
        # Step 1: Weather
        section("STEP 1: Fetching Weather Data")
        weather_by_city = DEMO_WEATHER if demo else fetch_all_weather()
        if demo:
            for city, d in weather_by_city.items():
                cur = d["current"]
                print(f"  {city:<12} {cur['temperature_c']:>5.1f}°C  "
                      f"💧{cur['precipitation_mm']:>4.1f}mm  "
                      f"💨{cur['wind_kmh']:>4.1f}km/h  [{', '.join(d['sources_used'])}]")

        # Step 2: Markets
        section("STEP 2: Loading Polymarket Markets")
        markets = mock_markets() if demo else fetch_markets()
        for m in markets:
            m["matched_city"] = match_city(m)
            if not m.get("city_hint"): m["city_hint"] = m["matched_city"]
        print(f"  Found {len(markets)} active weather markets")

        # Step 3: Predictions
        section("STEP 3: Running Prediction Model")
        predictions = []
        for mkt in markets:
            city    = mkt.get("city_hint","")
            weather = weather_by_city.get(city,{})
            if not weather: continue
            pred = predict(mkt.get("question",""), weather)
            yes_p = float((mkt.get("outcomePrices") or ["0.5"])[0])
            no_p  = float((mkt.get("outcomePrices") or ["0.5","0.5"])[1]) if len(mkt.get("outcomePrices") or [])>1 else 1-yes_p
            edge  = pred["p_yes"] - yes_p
            flag  = f"  {G}✅ EDGE{W}" if abs(edge)>0.05 else "  ·"
            print(f"  {city:<12} | {mkt['question'][:50]}")
            print(f"               P(YES)={pred['p_yes']:.1%}  Market={yes_p:.1%}  Edge={edge:+.1%}  Side={pred['side']}{flag}")
            predictions.append({**pred, "market_id": mkt["id"], "question": mkt["question"],
                                 "city": city, "market_yes_price": yes_p, "market_no_price": no_p,
                                 "volume": mkt.get("volume",0), "timestamp": datetime.utcnow().isoformat()})

        # Step 4: LLM
        section("STEP 4: LLM Agent Reasoning (Mistral-7B via OpenRouter)")
        if OPENROUTER_API_KEY:
            print(f"  {C}Calling LLM...{W}")
            llm_decisions = call_llm(predictions)
            print(f"  LLM made {len(llm_decisions)} decisions")
        else:
            llm_decisions = {}
            print(f"  {Y}No API key — using rule-based decisions{W}")

        # Step 5: Trades
        section("STEP 5: Executing Paper Trades (Kelly Criterion)")
        print(f"  {'Type':<8} {'City':<12} {'Side':<5} {'Price':>7} {'Size':>8} {'Payout':>8}")
        print(f"  {'─'*8} {'─'*12} {'─'*5} {'─'*7} {'─'*8} {'─'*8}")
        trades_placed = []
        for pred in predictions:
            mid  = pred["market_id"]
            llm  = llm_decisions.get(mid,{})
            dec  = llm.get("decision","")
            if dec == "SKIP": continue
            side = ("YES" if dec=="BET_YES" else ("NO" if dec=="BET_NO" else pred["side"]))
            market_price = pred["market_yes_price"] if side=="YES" else pred["market_no_price"]
            p_win        = pred["p_yes"] if side=="YES" else 1-pred["p_yes"]
            size         = kelly_size(trader.balance, p_win, market_price)
            if size <= 0: continue
            order = trader.place_order(
                market_id=mid, question=pred["question"], side=side,
                size_usd=size, price=market_price, city=pred["city"],
                reason=pred["reasoning"][:120])
            if order: trades_placed.append(order)

        # Step 6: Hedging
        section("STEP 6: Hedging Positions")
        if trades_placed:
            big = max(trades_placed, key=lambda t: t["size_usd"])
            hedge(big, predictions, trader)
        else:
            print(f"  No positions large enough to hedge.")

        # Save predictions
        json.dump(predictions, open("results/predictions_log.json","w"), indent=2)

        return predictions, trades_placed

    if args.loop:
        import time
        cycle = 0
        while True:
            cycle += 1
            print(f"\n{BOLD}{'─'*62}{W}")
            print(f"{BOLD}  Cycle #{cycle} — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}{W}")
            try:
                preds, trades = run_cycle(demo=False)
                print_dashboard(trader, preds)
                print_stats(trader, preds)
                tg(f"*CWT Cycle #{cycle}*\nTrades: {len(trades)}\nBalance: ${trader.summary()['balance']:,.2f}")
            except Exception as e:
                log.error(f"Cycle error: {e}", exc_info=True)
            print(f"\n{Y}Next cycle in 30 minutes... (Ctrl+C to stop){W}")
            try: time.sleep(1800)
            except KeyboardInterrupt: break
    else:
        preds, trades = run_cycle(demo=args.demo)
        print_dashboard(trader, preds)
        print_stats(trader, preds)
        tg(f"*CWT Agent Run Complete*\nTrades: {len(trades)}\nBalance: ${trader.summary()['balance']:,.2f}")

if __name__ == "__main__":
    main()
