# Equity Research Analyzer – Online (Stages 1–5 Complete)

Password-protected professional equity research tool with free live data.

## Features
- Live quote, profile, metrics, historical financials + **true FCF**
- Interactive DCF + sensitivity table
- Peer comparison (metrics + multi-year)
- Earnings surprises + **next earnings date**
- Market snapshot, relative strength vs SPY, ATR, RSI, MACD
- Support/resistance levels, watchlist, scorecard suggestions
- Insider activity, liquidity, positioning
- Help icons (ⓘ) on key metrics
- Research workflow checklist
- **Export: Markdown + PDF report**
- Save/Load qualitative notes (JSON)

## Deploy (Streamlit Cloud)
1. Upload `app.py`, `requirements.txt`, `README.md` to a public GitHub repo  
2. Deploy at https://share.streamlit.io  
3. Set Secrets:
```toml
APP_PASSWORD = "your-password"
FINNHUB_API_KEY = "your-finnhub-key"
```

## Local
```bash
pip install -r requirements.txt
streamlit run app.py
```
Default local password: `research2026`

Not investment advice. Always verify with primary filings.
