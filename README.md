# CrowdWisdomTrading — Weather Prediction Markets Agent

A Python-based autonomous agent system that trades profitably on **weather prediction markets on Polymarket**, covering 5+ cities, with a full UI dashboard, paper trading, Kelly Criterion risk management, and hedging.

---

## Architecture Overview

```
cwt_weather_agent/
├── agents/
│   ├── weather_agent.py        # Core Hermes-style agent: fetch, reason, trade
│   ├── hedging_agent.py        # Hedging logic across correlated positions
│   └── research_agent.py       # Market research + Polymarket opportunity scanner
├── data/
│   ├── weather_fetcher.py      # Multi-source weather data (Apify + OpenMeteo + wttr.in)
│   └── polymarket_client.py    # Polymarket market data + paper trade order placement
├── models/
│   ├── kelly_criterion.py      # Kelly Criterion position sizing
│   └── prediction_model.py     # Weather prediction model (ensemble)
├── ui/
│   └── dashboard.py            # Rich terminal dashboard (live updates)
├── utils/
│   ├── logger.py               # Structured logging
│   └── config.py               # Config & secrets loader
├── results/                    # Auto-saved trade logs, predictions, stats
├── main.py                     # Entry point — launches the full agent loop
├── requirements.txt
└── .env.example
```

---

## Quickstart

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in:
#   OPENROUTER_API_KEY   — from openrouter.ai (free)
#   APIFY_API_TOKEN      — from apify.com (free)
```

### 3. Run
```bash
python main.py
```

---

## Features

| Feature | Details |
|---|---|
| **5+ Cities** | New York, London, Tokyo, Sydney, Mumbai |
| **Weather Sources** | Apify Weather API, Open-Meteo, wttr.in (local fallback) |
| **Agent Framework** | Hermes-style tool-calling agent (OpenRouter + free LLM) |
| **Risk Management** | Kelly Criterion position sizing with max bet cap |
| **Paper Trading** | Full order simulation with P&L tracking |
| **Hedging** | Cross-city correlation-based hedge positions |
| **Dashboard** | Live Rich terminal UI with positions, predictions, P&L |
| **Telegram** | Optional bot notifications (set TELEGRAM_TOKEN + CHAT_ID) |

---

## Cities Tracked

1. New York, USA
2. London, UK
3. Tokyo, Japan
4. Sydney, Australia
5. Mumbai, India
6. Dubai, UAE *(bonus)*

---

## Statistical Results

Results are auto-saved to `results/` after each run:
- `predictions_log.json` — all predictions with confidence
- `trades_log.json` — paper trades placed
- `performance_stats.json` — win rate, ROI, Sharpe ratio

---

## Submission

- GitHub: *link to your repo*
- APIFY tokens used: see `.env` / submission email
- Output examples: see `results/` folder + demo video

---

*Built for CrowdWisdomTrading Internship Assessment — Gilad @ CWT*
