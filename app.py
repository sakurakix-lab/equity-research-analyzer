"""
Equity Research Analyzer – Online Edition (Password Protected)
Complete toolkit: sector RS, watchlist metrics, PDF export, events,
structure, positioning, FCF history, DCF, help icons.
"""



import streamlit as st
import urllib.request
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

st.set_page_config(
    page_title="Equity Research Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------- Password --------------------
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets.get("APP_PASSWORD", "research2026"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.info("Enter the app password to continue.")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("Incorrect password")
        return False
    return True

if not check_password():
    st.stop()

# -------------------- Helpers --------------------
def finnhub_get(endpoint: str, api_key: str, **params):
    base = "https://finnhub.io/api/v1/"
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{base}{endpoint}?{query}&token={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            data = json.loads(r.read().decode())
            if isinstance(data, dict) and data.get("error"):
                return None
            return data
    except Exception:
        return None

def safe_get(d, *keys, default="—"):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
        d = d.get(k) if isinstance(d, dict) else None
    return default

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line

def compute_atr(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def classify_trend(series, ma_fast=20, ma_slow=50):
    if len(series) < ma_slow + 5:
        return "Insufficient data"
    price = float(series.iloc[-1])
    ma_f = float(series.rolling(ma_fast).mean().iloc[-1])
    ma_s = float(series.rolling(ma_slow).mean().iloc[-1])
    if price > ma_f > ma_s:
        return "Uptrend"
    if price < ma_f < ma_s:
        return "Downtrend"
    return "Sideways / Transition"

def relative_strength(stock_closes, bench_closes, lookback=63):
    if len(stock_closes) < lookback or len(bench_closes) < lookback:
        return None
    s_ret = float(stock_closes.iloc[-1] / stock_closes.iloc[-lookback] - 1)
    b_ret = float(bench_closes.iloc[-1] / bench_closes.iloc[-lookback] - 1)
    return (s_ret - b_ret) * 100

SECTOR_ETF_MAP = {
    "technology": "XLK", "software": "XLK", "semiconductor": "XLK", "electronics": "XLK",
    "bank": "XLF", "financial": "XLF", "insurance": "XLF", "capital markets": "XLF",
    "energy": "XLE", "oil": "XLE", "gas": "XLE",
    "health": "XLV", "biotech": "XLV", "pharma": "XLV", "medical": "XLV",
    "industrial": "XLI", "aerospace": "XLI", "machinery": "XLI", "defense": "XLI",
    "consumer cyclical": "XLY", "retail": "XLY", "automobile": "XLY", "apparel": "XLY",
    "consumer defensive": "XLP", "food": "XLP", "beverage": "XLP", "household": "XLP",
    "utilities": "XLU", "utility": "XLU",
    "basic materials": "XLB", "chemical": "XLB", "mining": "XLB", "metals": "XLB",
    "real estate": "XLRE", "reit": "XLRE",
    "communication": "XLC", "media": "XLC", "telecom": "XLC",
}

def industry_to_sector_etf(industry):
    if not industry or industry == "—":
        return None
    s = str(industry).lower()
    for key, etf in SECTOR_ETF_MAP.items():
        if key in s:
            return etf
    return None

HELP = {
    "price": "Current last traded price. Compare to your cost basis and to key moving averages.",
    "market_cap": "Total market value of the company’s equity. Useful for sizing and liquidity context.",
    "pe": "Price divided by trailing twelve-month earnings. High P/E can mean growth expectations or expensive valuation.",
    "fcf": "Free Cash Flow = Operating Cash Flow − Capital Expenditure. Cash available after maintaining the business.",
    "rsi": "Relative Strength Index (0–100). Above 70 often overbought; below 30 oversold. Price/RSI divergences can signal exhaustion.",
    "macd": "MACD line crossing above its signal is commonly treated as bullish momentum; the reverse as bearish.",
    "atr": "Average True Range measures volatility. Rising ATR = expanding volatility (wider stops). Falling ATR = quieter conditions.",
    "rel_strength": "Stock performance versus a benchmark (e.g. SPY or sector ETF). Positive = outperformance. Leaders often hold up better in pullbacks.",
    "sector_rs": "Relative strength versus the stock’s sector ETF (e.g. XLK for tech). Shows whether the name is leading or lagging its own industry.",
    "trend": "Classification using price vs 20-day and 50-day moving averages. Defines short/intermediate directional bias.",
    "volume": "Trading activity. Above-average volume on up days supports buying; high volume on down days can signal distribution.",
    "earnings_surprise": "Actual EPS minus estimate. Consistent beats can support multiple expansion; repeated misses often pressure the stock.",
    "dcf": "Estimates intrinsic value from projected free cash flows. Highly sensitive to growth and discount-rate assumptions.",
    "peer": "Comparing valuation and profitability to similar companies. Always verify business models are comparable.",
    "scorecard": "Structured scoring to force balanced analysis. Not a prediction of future returns.",
    "spy": "S&P 500 ETF – broad US large-cap proxy. Rising with the stock = market tailwind.",
    "qqq": "Nasdaq-100 ETF – growth/tech heavy. Leadership often signals risk-on appetite.",
    "iwm": "Russell 2000 ETF – small caps. Outperformance can indicate broadening risk appetite.",
    "tlt": "Long-term Treasury ETF. Rising while stocks fall often signals flight-to-safety or falling rate expectations.",
    "insider": "Open-market buys by executives/directors can signal confidence. Heavy selling is more ambiguous (taxes, diversification) but clustered selling after a run-up can be a caution flag.",
    "liquidity": "Average daily volume indicates how easily you can enter/exit without moving the price. Low liquidity increases slippage and risk.",
    "recommendations": "Analyst buy/hold/sell distribution over time. Rising buy counts can support sentiment; the reverse can pressure multiples.",
    "price_target": "Average analyst target price. Compare to current price for implied upside, but targets lag and often cluster around consensus.",
    "short_interest": "Shares sold short as % of float. High or rising short interest can fuel squeezes or reflect negative views. Free-tier data is limited on Finnhub.",
    "positioning": "How institutions, insiders, and short sellers are positioned. Extreme positioning can amplify moves in either direction.",
    "support_resistance": "Price zones where buying (support) or selling (resistance) has historically concentrated. Breaks often attract momentum flows.",
    "ma_distance": "How far price sits from key moving averages. Large extension can mean stretched; price resting on an MA can act as support/resistance.",
    "watchlist": "A short list of tickers you track. Useful for comparing relative strength and catalysts side by side.",
    "score_suggest": "Rules-based starting scores from available data. Always override with your own judgment — these are prompts, not answers.",
    "next_earnings": "Scheduled report date. Stocks often reprice into and after earnings. Position size and stops are usually adjusted when the event is near.",
    "workflow": "A simple checklist to keep analysis disciplined: data → thesis → levels → risk → decision.",
    "entry_exit": "Suggested levels from support, resistance, moving averages, and ATR. Use as a starting framework only — not automated trade signals. Always set your own invalidation.",
}

def help_box(key, label=None):
    text = HELP.get(key, "Description coming soon.")
    title = label or key.replace("_", " ").title()
    with st.expander(f"ⓘ What is {title}?", expanded=False):
        st.caption(text)

def build_pdf_report(ctx):
    """Build a multi-section PDF research report. ctx is a dict of values."""
    if not HAS_PDF:
        return None
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.6*inch, bottomMargin=0.6*inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=16, spaceAfter=6, alignment=TA_CENTER)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=4, textColor=colors.HexColor("#1e3a5f"))
    body = ParagraphStyle("B", parent=styles["Normal"], fontSize=9, leading=12, spaceAfter=3)
    small = ParagraphStyle("S", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.grey)

    story = []
    story.append(Paragraph(f"Equity Research Report: {ctx.get('ticker', '')}", title_style))
    story.append(Paragraph(
        f"{ctx.get('name', '')} · {ctx.get('date', '')} · Horizon: {ctx.get('horizon', '')} · Risk: {ctx.get('risk', '')}",
        small))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1e3a5f")))
    story.append(Spacer(1, 8))

    def sec(title):
        story.append(Paragraph(title, h2))

    def line(txt):
        story.append(Paragraph(str(txt).replace("\n", "<br/>"), body))

    sec("1. Snapshot")
    line(f"Price: ${ctx.get('price')} · Change: {ctx.get('change')} ({ctx.get('change_pct')}%)")
    line(f"Market Cap: {ctx.get('mktcap')} · Industry: {ctx.get('industry')}")
    if ctx.get("next_earn"):
        line(f"Next earnings: {ctx['next_earn']}")

    sec("2. Key Metrics")
    line(f"Trailing P/E: {ctx.get('pe')} · Gross Margin: {ctx.get('gm')}% · ROE: {ctx.get('roe')}%")
    line(f"Rev Growth 5Y: {ctx.get('rev_g')}% · Debt/Equity: {ctx.get('de')}")
    line(f"EV/EBITDA: {ctx.get('ev')} · P/S: {ctx.get('ps')}")

    sec("3. Free Cash Flow & DCF")
    line(f"Latest FCF context: {ctx.get('fcf_note', 'See app for details')}")
    line(f"DCF Bear: ${ctx.get('bear')} · Base: ${ctx.get('base')} · Bull: ${ctx.get('bull')}")

    sec("4. Peers & Analysts")
    line(f"Peers: {ctx.get('peers', 'N/A')}")
    line(f"Analyst target mean: ${ctx.get('target_mean')} · High: ${ctx.get('target_high')} · Low: ${ctx.get('target_low')}")

    sec("5. Qualitative Analysis")
    line(f"<b>Moat:</b> {ctx.get('moat') or '—'}")
    line(f"<b>Bull case:</b> {ctx.get('bull_case') or '—'}")
    line(f"<b>Bear case:</b> {ctx.get('bear_case') or '—'}")
    line(f"<b>Catalysts:</b> {ctx.get('catalysts') or '—'}")

    sec("6. Scorecard & Theses")
    line(f"Total score: {ctx.get('score', '—')} / 100")
    line(f"<b>Bull thesis:</b> {ctx.get('thesis_bull') or '—'}")
    line(f"<b>Base thesis:</b> {ctx.get('thesis_base') or '—'}")
    line(f"<b>Bear thesis:</b> {ctx.get('thesis_bear') or '—'}")

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph(
        "Generated by Equity Research Analyzer · Data via Finnhub free tier · Not investment advice. "
        "Always verify with primary filings (10-K / 10-Q).",
        small))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

def find_swing_levels(df, left=5, right=5, n_levels=3):
    """Simple swing high/low detection for support/resistance."""
    if df is None or len(df) < left + right + 5:
        return [], []
    highs, lows = [], []
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    idx = df.index
    for i in range(left, len(df) - right):
        if h[i] == max(h[i-left:i+right+1]):
            highs.append((idx[i], float(h[i])))
        if l[i] == min(l[i-left:i+right+1]):
            lows.append((idx[i], float(l[i])))
    # Most recent distinct levels
    def top_n(levels, reverse=True):
        vals = sorted({round(v, 2) for _, v in levels}, reverse=reverse)
        return vals[:n_levels]
    resist = top_n(highs, reverse=True)
    support = top_n(lows, reverse=False)
    return support, resist

def ma_distances(close, ma20, ma50, ma200=None):
    """Percent distance of price from MAs."""
    out = {}
    if ma20 and close:
        out["vs MA20"] = (close / ma20 - 1) * 100
    if ma50 and close:
        out["vs MA50"] = (close / ma50 - 1) * 100
    if ma200 and close:
        out["vs MA200"] = (close / ma200 - 1) * 100
    return out

def suggest_entry_exit(candles_payload, price=None):
    """
    From Finnhub candle payload, suggest long entry / stop / target.
    Returns dict with Entry, Stop, Target, R:R, Bias or Nones.
    """
    empty = {"Entry": None, "Stop": None, "Target": None, "R:R": None, "Bias": "—"}
    if not candles_payload or safe_get(candles_payload, "s") != "ok":
        return empty
    try:
        df = pd.DataFrame({
            "Date": pd.to_datetime(candles_payload["t"], unit="s"),
            "Open": candles_payload["o"],
            "High": candles_payload["h"],
            "Low": candles_payload["l"],
            "Close": candles_payload["c"],
        }).set_index("Date").sort_index()
        if len(df) < 30:
            return empty
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA50"] = df["Close"].rolling(50).mean()
        atr = compute_atr(df)
        latest_close = float(price) if price not in (None, "—") else float(df["Close"].iloc[-1])
        atr_v = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else latest_close * 0.02
        support, resist = find_swing_levels(df)
        nearest_sup = None
        if support:
            below = [s for s in support if s < latest_close]
            nearest_sup = max(below) if below else min(support)
        nearest_res = None
        if resist:
            above = [r for r in resist if r > latest_close]
            nearest_res = min(above) if above else max(resist)
        ma20_v = float(df["MA20"].iloc[-1]) if not df["MA20"].isna().iloc[-1] else None
        trend = classify_trend(df["Close"], 20, 50)
        long_entry = nearest_sup if nearest_sup else (ma20_v if ma20_v else latest_close * 0.98)
        if ma20_v and nearest_sup and trend != "Downtrend":
            long_entry = nearest_sup + (latest_close - nearest_sup) * 0.25
        long_stop = (nearest_sup - atr_v) if nearest_sup else (latest_close - 1.5 * atr_v)
        long_t1 = nearest_res if nearest_res else (latest_close + 2 * atr_v)
        risk = abs(long_entry - long_stop) if long_stop else atr_v
        reward = abs(long_t1 - long_entry) if long_t1 else atr_v
        rr = round(reward / risk, 1) if risk and risk > 0 else None
        return {
            "Entry": round(long_entry, 2),
            "Stop": round(long_stop, 2),
            "Target": round(long_t1, 2),
            "R:R": rr,
            "Bias": trend,
        }
    except Exception:
        return empty

def simple_dcf(fcf0, growth_rate, terminal_growth, wacc, shares, net_debt=0, years=5):
    if wacc <= terminal_growth or wacc <= 0 or shares <= 0:
        return None
    fcf = float(fcf0)
    pv_fcfs = 0.0
    for y in range(1, years + 1):
        fcf *= (1 + growth_rate)
        pv_fcfs += fcf / ((1 + wacc) ** y)
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** years)
    equity_value = (pv_fcfs + pv_terminal) - net_debt
    return equity_value / shares

def parse_reported_financials(raw):
    """Extract clean annual history + FCF from Finnhub financials-reported."""
    if not raw or not isinstance(raw, dict):
        return []
    rows = []
    for rep in raw.get("data", []):
        if rep.get("form") not in ("10-K", "20-F") and rep.get("quarter") not in (0, None):
            continue
        year = rep.get("year")
        if not year:
            continue
        report = rep.get("report") or {}
        ic = {x.get("concept"): x.get("value") for x in report.get("ic", []) if x.get("concept")}
        bs = {x.get("concept"): x.get("value") for x in report.get("bs", []) if x.get("concept")}
        cf = {x.get("concept"): x.get("value") for x in report.get("cf", []) if x.get("concept")}

        def first(*keys):
            for k in keys:
                if k in ic and ic[k] is not None:
                    return ic[k]
                if k in bs and bs[k] is not None:
                    return bs[k]
                if k in cf and cf[k] is not None:
                    return cf[k]
            return None

        revenue = first(
            "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap_SalesRevenueNet", "us-gaap_Revenues", "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax"
        )
        gross = first("us-gaap_GrossProfit")
        opinc = first("us-gaap_OperatingIncomeLoss")
        netinc = first("us-gaap_NetIncomeLoss")
        ocf = first("us-gaap_NetCashProvidedByUsedInOperatingActivities")
        capex = first("us-gaap_PaymentsToAcquirePropertyPlantAndEquipment")
        # Capex is usually reported as positive outflow; make FCF = OCF - |Capex|
        fcf = None
        if ocf is not None and capex is not None:
            fcf = ocf - abs(capex)
        elif ocf is not None:
            fcf = ocf

        cash = first("us-gaap_CashAndCashEquivalentsAtCarryingValue", "us-gaap_CashCashEquivalentsAndShortTermInvestments")
        debt = first("us-gaap_LongTermDebtNoncurrent", "us-gaap_LongTermDebt")

        rows.append({
            "Year": year,
            "Revenue": revenue,
            "Gross Profit": gross,
            "Operating Income": opinc,
            "Net Income": netinc,
            "Operating CF": ocf,
            "Capex": abs(capex) if capex is not None else None,
            "Free Cash Flow": fcf,
            "Cash": cash,
            "Long-term Debt": debt,
        })
    # Keep unique years, most recent first
    seen = set()
    clean = []
    for r in sorted(rows, key=lambda x: x["Year"], reverse=True):
        if r["Year"] not in seen:
            seen.add(r["Year"])
            clean.append(r)
    return clean[:6]  # last ~6 years

# -------------------- Sidebar --------------------
with st.sidebar:
    st.title("📈 Equity Research")
    st.caption("Online · Password Protected")

    st.markdown("---")
    st.subheader("Finnhub API Key")
    default_key = ""
    try:
        default_key = st.secrets.get("FINNHUB_API_KEY", "")
    except Exception:
        pass
    api_key = st.text_input(
        "API Key", type="password",
        value=default_key if default_key else st.session_state.get("api_key", ""),
        help="Free key from finnhub.io"
    )
    if api_key:
        st.session_state["api_key"] = api_key

    st.markdown("---")
    st.subheader("Ticker")
    ticker = st.text_input("Symbol", value=st.session_state.get("ticker", "AAPL")).upper().strip()
    st.session_state["ticker"] = ticker
    load_btn = st.button("🔄 Load Free Data", type="primary", use_container_width=True)

    st.markdown("---")
    horizon = st.selectbox("Investment Horizon", ["Short Term", "6–12 Months", "1–3 Years", "5+ Years"])
    risk = st.selectbox("Risk Tolerance", ["Low", "Medium", "High"])

    st.markdown("---")
    st.subheader("Watchlist")
    help_box("watchlist", "Watchlist")
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = []
    wl_input = st.text_input("Add ticker to watchlist", placeholder="e.g. MSFT", key="wl_add")
    if st.button("Add") and wl_input:
        sym = wl_input.strip().upper()
        if sym and sym not in st.session_state["watchlist"]:
            st.session_state["watchlist"].append(sym)
    if st.session_state["watchlist"]:
        st.write(", ".join(st.session_state["watchlist"]))
        c_wl1, c_wl2 = st.columns(2)
        with c_wl1:
            if st.button("Clear watchlist"):
                st.session_state["watchlist"] = []
                st.session_state.pop("wl_batch", None)
        with c_wl2:
            run_batch = st.button(
                "Run batch dashboard",
                type="primary",
                help="Quotes, metrics, next earnings for all watchlist names",
            )
        if run_batch and api_key:
            with st.spinner("Running batch analysis (quotes, levels, earnings)…"):
                today_s = datetime.now().strftime("%Y-%m-%d")
                fwd_s = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
                end_ts = int(datetime.now().timestamp())
                start_ts = int((datetime.now() - timedelta(days=250)).timestamp())
                batch_rows = []
                for sym in st.session_state["watchlist"][:10]:
                    q = finnhub_get("quote", api_key, symbol=sym)
                    m = finnhub_get("stock/metric", api_key, symbol=sym, metric="all")
                    ms = safe_get(m, "metric", default={}) if m else {}
                    p = finnhub_get("stock/profile2", api_key, symbol=sym)
                    cal = finnhub_get(
                        "calendar/earnings",
                        api_key,
                        symbol=sym,
                        **{"from": today_s, "to": fwd_s},
                    )
                    candles_sym = finnhub_get(
                        "stock/candle", api_key, symbol=sym,
                        resolution="D", _from=start_ts, to=end_ts,
                    )
                    next_e = None
                    if cal and isinstance(cal, dict):
                        cl = cal.get("earningsCalendar") or []
                        if cl:
                            next_e = cl[0].get("date")
                    days_to_earn = None
                    if next_e:
                        try:
                            days_to_earn = (
                                datetime.strptime(next_e, "%Y-%m-%d").date()
                                - datetime.now().date()
                            ).days
                        except Exception:
                            pass
                    px = safe_get(q, "c")
                    levels = suggest_entry_exit(candles_sym, px)
                    batch_rows.append({
                        "Ticker": sym,
                        "Name": str(safe_get(p, "name"))[:18] if p else "—",
                        "Price": px,
                        "Chg %": safe_get(q, "dp"),
                        "Bias": levels.get("Bias"),
                        "Entry": levels.get("Entry") if levels.get("Entry") is not None else "—",
                        "Stop": levels.get("Stop") if levels.get("Stop") is not None else "—",
                        "Target": levels.get("Target") if levels.get("Target") is not None else "—",
                        "R:R": levels.get("R:R") if levels.get("R:R") is not None else "—",
                        "P/E": safe_get(ms, "peBasicExclExtraTTM"),
                        "Next Earnings": next_e or "—",
                        "Days to Earn": days_to_earn if days_to_earn is not None else "—",
                    })
                st.session_state["wl_batch"] = batch_rows
                st.session_state["wl_batch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.success(f"Batch done · {len(st.session_state.get('wl_batch', []))} names · entry/stop/target included")
        if st.session_state.get("wl_batch"):
            st.caption(f"Last batch: {st.session_state.get('wl_batch_time', '')}")
            st.dataframe(
                pd.DataFrame(st.session_state["wl_batch"]),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("---")
    st.subheader("Save / Load Analysis")
    notes_data = {
        "ticker": ticker, "horizon": horizon, "risk": risk,
        "moat": st.session_state.get("moat", ""),
        "industry": st.session_state.get("industry", ""),
        "bull": st.session_state.get("bull", ""),
        "bear": st.session_state.get("bear", ""),
        "catalysts": st.session_state.get("catalysts", ""),
        "pricing": st.session_state.get("pricing", ""),
        "watch": st.session_state.get("watch", ""),
        "thesis_bull": st.session_state.get("thesis_bull", ""),
        "thesis_base": st.session_state.get("thesis_base", ""),
        "thesis_bear": st.session_state.get("thesis_bear", ""),
        "timestamp": datetime.now().isoformat()
    }
    st.download_button(
        "💾 Download Notes (JSON)",
        data=json.dumps(notes_data, indent=2),
        file_name=f"{ticker}_notes_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json", use_container_width=True
    )
    uploaded = st.file_uploader("Load previous notes", type=["json"], label_visibility="collapsed")
    if uploaded is not None:
        try:
            loaded = json.load(uploaded)
            for k in ["moat", "industry", "bull", "bear", "catalysts", "pricing", "watch",
                      "thesis_bull", "thesis_base", "thesis_bear"]:
                if k in loaded:
                    st.session_state[k] = loaded[k]
            st.success("Notes loaded")
        except Exception:
            st.error("Could not load file")

# -------------------- Main --------------------
st.title(f"{ticker or '—'}  ·  Equity Research Report")
st.caption(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Horizon: {horizon}  |  Risk: {risk}")

if not api_key:
    st.info("Enter a free Finnhub API key in the sidebar and click **Load Free Data**.")
    st.stop()

# Load company data
if load_btn or "data_loaded" not in st.session_state or st.session_state.get("last_ticker") != ticker:
    with st.spinner(f"Fetching data for {ticker}…"):
        quote = finnhub_get("quote", api_key, symbol=ticker)
        profile = finnhub_get("stock/profile2", api_key, symbol=ticker)
        metrics_raw = finnhub_get("stock/metric", api_key, symbol=ticker, metric="all")
        recs = finnhub_get("stock/recommendation", api_key, symbol=ticker)
        target = finnhub_get("stock/price-target", api_key, symbol=ticker)
        peers = finnhub_get("stock/peers", api_key, symbol=ticker)
        financials_raw = finnhub_get("stock/financials-reported", api_key, symbol=ticker)
        earnings = finnhub_get("stock/earnings", api_key, symbol=ticker)
        insider_raw = finnhub_get("stock/insider-transactions", api_key, symbol=ticker)

        # Next earnings date (Stage 4)
        today_s = datetime.now().strftime("%Y-%m-%d")
        fwd_s = (datetime.now() + timedelta(days=120)).strftime("%Y-%m-%d")
        earn_cal = finnhub_get("calendar/earnings", api_key, symbol=ticker, **{"from": today_s, "to": fwd_s})
        next_earn = None
        if earn_cal and isinstance(earn_cal, dict):
            cal_list = earn_cal.get("earningsCalendar") or []
            if cal_list:
                next_earn = cal_list[0]

        end = int(datetime.now().timestamp())
        start = int((datetime.now() - timedelta(days=250)).timestamp())
        candles = finnhub_get("stock/candle", api_key, symbol=ticker, resolution="D", _from=start, to=end)
        spy_candles = finnhub_get("stock/candle", api_key, symbol="SPY", resolution="D", _from=start, to=end)

        # Sector ETF for relative strength
        sector_etf = industry_to_sector_etf(safe_get(profile, "finnhubIndustry") if profile else None)
        sector_candles = None
        if sector_etf:
            sector_candles = finnhub_get("stock/candle", api_key, symbol=sector_etf, resolution="D", _from=start, to=end)

        # Market snapshot
        market = {}
        for sym in ["SPY", "QQQ", "IWM", "TLT"]:
            market[sym] = finnhub_get("quote", api_key, symbol=sym)

        hist = parse_reported_financials(financials_raw)

        st.session_state.update({
            "quote": quote, "profile": profile, "metrics": metrics_raw,
            "recs": recs, "target": target, "peers": peers, "candles": candles,
            "spy_candles": spy_candles, "sector_candles": sector_candles, "sector_etf": sector_etf,
            "market": market, "hist": hist, "earnings": earnings,
            "insider": insider_raw, "next_earn": next_earn,
            "data_loaded": True, "last_ticker": ticker,
            "peer_table": None, "peer_hist": None
        })

quote = st.session_state.get("quote")
profile = st.session_state.get("profile")
metrics = st.session_state.get("metrics")
recs = st.session_state.get("recs")
target = st.session_state.get("target")
peers = st.session_state.get("peers")
candles = st.session_state.get("candles")
spy_candles = st.session_state.get("spy_candles")
sector_candles = st.session_state.get("sector_candles")
sector_etf = st.session_state.get("sector_etf")
market = st.session_state.get("market", {})
hist = st.session_state.get("hist", [])
earnings = st.session_state.get("earnings")
insider = st.session_state.get("insider")
next_earn = st.session_state.get("next_earn")

if not quote and not profile:
    st.error("Could not load data. Check ticker and API key (or rate limit).")
    st.stop()

# ========== DASHBOARD ==========
col1, col2, col3, col4, col5 = st.columns(5)
price = safe_get(quote, "c")
change = safe_get(quote, "d")
change_pct = safe_get(quote, "dp")

with col1:
    st.metric("Current Price", f"${price}" if price != "—" else "—",
              f"{change} ({change_pct}%)" if change != "—" else None)
with col2:
    mktcap = safe_get(profile, "marketCapitalization")
    mktcap_str = f"${mktcap:,.0f}M" if isinstance(mktcap, (int, float)) and mktcap < 1_000_000 else (
        f"${mktcap/1000:,.1f}B" if isinstance(mktcap, (int, float)) else "—")
    st.metric("Market Cap", mktcap_str)
with col3:
    st.metric("Industry", str(safe_get(profile, "finnhubIndustry"))[:22])
with col4:
    st.metric("Country", safe_get(profile, "country"))
with col5:
    high, low = safe_get(quote, "h"), safe_get(quote, "l")
    st.metric("Day Range", f"{low} – {high}" if high != "—" else "—")

# Stage 4: Event awareness bar
if next_earn and next_earn.get("date"):
    ed = next_earn.get("date")
    hour = next_earn.get("hour", "")
    hour_label = {"bmo": "Before open", "amc": "After close"}.get(str(hour).lower(), str(hour) or "")
    try:
        days_left = (datetime.strptime(ed, "%Y-%m-%d").date() - datetime.now().date()).days
        days_txt = f"in {days_left} day(s)" if days_left >= 0 else f"{abs(days_left)} day(s) ago"
    except Exception:
        days_left, days_txt = None, ""
    eps_est = next_earn.get("epsEstimate")
    st.info(
        f"**Next earnings:** {ed} {hour_label} ({days_txt})"
        + (f" · EPS est. ${eps_est}" if eps_est is not None else "")
    )
    if days_left is not None and 0 <= days_left <= 7:
        st.warning("Earnings within 7 days — expect elevated volatility and wider spreads.")

st.markdown("---")

# ========== TABS ==========
tabs = st.tabs([
    "0. Market",
    "1. Profile",
    "2. Fundamentals",
    "3. Balance & Risk",
    "4. Valuation & DCF",
    "5. Peers & Analysts",
    "5b. Positioning",
    "6. Technicals",
    "7. Your Analysis",
    "8. Scorecard & Thesis",
    "9. Export",
    "10. Watchlist Batch",
])

metric_series = safe_get(metrics, "metric", default={}) if metrics else {}

# ---- Tab 0: Market Environment ----
with tabs[0]:
    st.subheader("Market Environment Snapshot")
    st.caption("Quick risk-on / risk-off context using major ETFs.")

    mcols = st.columns(4)
    labels = {"SPY": "S&P 500 (SPY)", "QQQ": "Nasdaq 100 (QQQ)", "IWM": "Russell 2000 (IWM)", "TLT": "20Y+ Treasury (TLT)"}
    help_keys = {"SPY": "spy", "QQQ": "qqq", "IWM": "iwm", "TLT": "tlt"}
    for i, sym in enumerate(["SPY", "QQQ", "IWM", "TLT"]):
        q = market.get(sym) or {}
        c = safe_get(q, "c")
        dp = safe_get(q, "dp")
        with mcols[i]:
            st.metric(labels[sym], f"${c}" if c != "—" else "—",
                      f"{dp}%" if dp != "—" else None)
            help_box(help_keys[sym], labels[sym])

    st.markdown("---")
    st.markdown("**How to read this**")
    st.write("""
    - **SPY / QQQ rising together** → broad risk-on, growth leadership  
    - **IWM outperforming** → risk appetite broadening into small caps  
    - **TLT rising while equities fall** → flight to safety / rate-cut expectations  
    - **All equities down + TLT down** → tightening / risk-off with rising yields  
    """)
    st.info("Simplified snapshot only. Add full macro commentary (Fed, inflation, breadth) in Your Analysis.")

# ---- Tab 1: Profile ----
with tabs[1]:
    st.subheader("Company Profile")
    if profile:
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Name:** {safe_get(profile, 'name')}")
            st.write(f"**Ticker:** {safe_get(profile, 'ticker')}")
            st.write(f"**Exchange:** {safe_get(profile, 'exchange')}")
            st.write(f"**IPO:** {safe_get(profile, 'ipo')}")
            st.write(f"**Shares Outstanding:** {safe_get(profile, 'shareOutstanding')}")
        with c2:
            st.write(f"**Website:** {safe_get(profile, 'weburl')}")
            st.write(f"**Currency:** {safe_get(profile, 'currency')}")
            st.write(f"**Country:** {safe_get(profile, 'country')}")
        st.info("Add industry context and competitive landscape in the ‘Your Analysis’ tab.")
    else:
        st.warning("Profile data unavailable.")

# ---- Tab 2: Fundamentals ----
with tabs[2]:
    st.subheader("Key Metrics (Latest)")
    if metric_series:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Valuation**")
            st.write(f"Trailing P/E: **{safe_get(metric_series, 'peBasicExclExtraTTM')}**")
            st.write(f"Forward P/E: **{safe_get(metric_series, 'peNormalizedAnnual')}**")
            st.write(f"PEG: **{safe_get(metric_series, 'pegRatio')}**")
            st.write(f"Price/Sales: **{safe_get(metric_series, 'psTTM')}**")
            st.write(f"Price/Book: **{safe_get(metric_series, 'pbAnnual')}**")
            st.write(f"EV/EBITDA: **{safe_get(metric_series, 'currentEv/ebitdaTTM')}**")
        with col_b:
            st.markdown("**Profitability**")
            st.write(f"Gross Margin: **{safe_get(metric_series, 'grossMarginTTM')}%**")
            st.write(f"Operating Margin: **{safe_get(metric_series, 'operatingMarginTTM')}%**")
            st.write(f"Net Margin: **{safe_get(metric_series, 'netProfitMarginTTM')}%**")
            st.write(f"ROE: **{safe_get(metric_series, 'roeTTM')}%**")
            st.write(f"ROA: **{safe_get(metric_series, 'roaTTM')}%**")
            st.write(f"ROIC: **{safe_get(metric_series, 'roiTTM')}%**")
        with col_c:
            st.markdown("**Growth & Leverage**")
            st.write(f"Rev Growth 5Y: **{safe_get(metric_series, 'revenueGrowth5Y')}%**")
            st.write(f"EPS Growth 5Y: **{safe_get(metric_series, 'epsGrowth5Y')}%**")
            st.write(f"Rev Growth YoY: **{safe_get(metric_series, 'revenueGrowthTTMYoy')}%**")
            st.write(f"Debt/Equity: **{safe_get(metric_series, 'totalDebt/totalEquityAnnual')}**")
            st.write(f"Current Ratio: **{safe_get(metric_series, 'currentRatioAnnual')}**")
            st.write(f"Interest Coverage: **{safe_get(metric_series, 'netInterestCoverageTTM')}**")
    else:
        st.warning("No fundamental metrics returned for this ticker.")

    st.markdown("---")
    st.subheader("Historical Financials (Annual, from reported 10-K)")
    if hist:
        # Convert to display-friendly dataframe (values in $ millions)
        display_rows = []
        for r in hist:
            def m(v):
                if v is None:
                    return None
                return round(v / 1_000_000, 1)  # to $ millions
            display_rows.append({
                "Year": r["Year"],
                "Revenue ($M)": m(r["Revenue"]),
                "Gross Profit ($M)": m(r["Gross Profit"]),
                "Op. Income ($M)": m(r["Operating Income"]),
                "Net Income ($M)": m(r["Net Income"]),
                "Operating CF ($M)": m(r["Operating CF"]),
                "Capex ($M)": m(r["Capex"]),
                "Free Cash Flow ($M)": m(r["Free Cash Flow"]),
            })
        df_hist = pd.DataFrame(display_rows)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        # Simple growth rates
        if len(hist) >= 2 and hist[0].get("Revenue") and hist[1].get("Revenue"):
            rev_yoy = (hist[0]["Revenue"] / hist[1]["Revenue"] - 1) * 100
            fcf0 = hist[0].get("Free Cash Flow")
            fcf1 = hist[1].get("Free Cash Flow")
            fcf_yoy = (fcf0 / fcf1 - 1) * 100 if fcf0 and fcf1 and fcf1 != 0 else None
            c1, c2, c3 = st.columns(3)
            c1.metric("Revenue YoY", f"{rev_yoy:.1f}%")
            if fcf_yoy is not None:
                c2.metric("FCF YoY", f"{fcf_yoy:.1f}%")
            if hist[0].get("Free Cash Flow"):
                c3.metric("Latest FCF ($M)", f"{hist[0]['Free Cash Flow']/1e6:,.0f}")
        st.caption("FCF = Operating Cash Flow − Capex (from reported statements). Values in $ millions.")
    else:
        st.info("No historical reported financials available for this ticker on the free tier (common for some foreign or small-cap names).")

# ---- Tab 3: Balance ----
with tabs[3]:
    st.subheader("Balance Sheet & Risk Indicators")
    if metric_series:
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Total Debt / Equity:** {safe_get(metric_series, 'totalDebt/totalEquityAnnual')}")
            st.write(f"**Long-term Debt / Equity:** {safe_get(metric_series, 'longTermDebt/equityAnnual')}")
            st.write(f"**Current Ratio:** {safe_get(metric_series, 'currentRatioAnnual')}")
            st.write(f"**Quick Ratio:** {safe_get(metric_series, 'quickRatioAnnual')}")
        with c2:
            st.write(f"**Net Interest Coverage:** {safe_get(metric_series, 'netInterestCoverageTTM')}")
            st.write(f"**Payout Ratio:** {safe_get(metric_series, 'payoutRatioTTM')}")
            st.write(f"**Dividend Yield:** {safe_get(metric_series, 'dividendYieldIndicatedAnnual')}%")
        st.info("For full line-item balance sheet use the latest 10-K / 10-Q.")
    else:
        st.warning("Metrics unavailable.")

# ---- Tab 4: Valuation & DCF + Sensitivity ----
with tabs[4]:
    st.subheader("Valuation Snapshot")
    if metric_series:
        c1, c2, c3 = st.columns(3)
        c1.metric("Trailing P/E", safe_get(metric_series, "peBasicExclExtraTTM"))
        c1.metric("EV/EBITDA", safe_get(metric_series, "currentEv/ebitdaTTM"))
        c2.metric("Price/Sales", safe_get(metric_series, "psTTM"))
        c2.metric("Price/Book", safe_get(metric_series, "pbAnnual"))
        c3.metric("PEG", safe_get(metric_series, "pegRatio"))
        pfcf = safe_get(metric_series, "pfcfShareTTM")
        if pfcf != "—":
            c3.metric("P/FCF (TTM)", pfcf)

    st.markdown("---")
    st.subheader("Interactive DCF Calculator (5-Year + Gordon Growth)")
    help_box("dcf", "DCF Valuation")

    # Smart defaults – prefer real reported FCF, then fall back
    default_shares = float(safe_get(profile, "shareOutstanding") or 10000)
    default_fcf = 100.0
    fcf_note = "Enter trailing Free Cash Flow in $ millions"

    if hist and hist[0].get("Free Cash Flow"):
        default_fcf = round(hist[0]["Free Cash Flow"] / 1_000_000, 1)
        fcf_note = f"Pre-filled from latest reported FCF (OCF − Capex) = ${default_fcf:,.0f}M"
    else:
        cfps = safe_get(metric_series, "cashFlowPerShareTTM")
        if isinstance(cfps, (int, float)) and default_shares > 0:
            default_fcf = round(cfps * default_shares, 1)
            fcf_note = f"Approx from Cash Flow/Share × shares (≈ ${default_fcf:,.0f}M). Prefer true FCF after Capex."

    default_growth = 0.08
    rev_g = safe_get(metric_series, "revenueGrowth5Y")
    if isinstance(rev_g, (int, float)):
        default_growth = max(0.02, min(0.15, rev_g / 100 * 0.7))

    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.markdown("**Starting Point**")
        fcf0 = st.number_input("Current FCF ($ millions)", value=float(default_fcf), step=10.0, help=fcf_note)
        shares = st.number_input("Shares (millions)", value=default_shares, step=100.0)
        net_debt = st.number_input("Net Debt ($ millions)", value=0.0, step=100.0,
                                   help="Positive = net debt · Negative = net cash")
    with col_d2:
        st.markdown("**Base Case**")
        base_growth = st.number_input("FCF Growth (Base)", value=float(round(default_growth, 2)), step=0.01, format="%.2f")
        base_wacc = st.number_input("WACC (Base)", value=0.09, step=0.005, format="%.3f")
        base_term = st.number_input("Terminal Growth (Base)", value=0.025, step=0.005, format="%.3f")
    with col_d3:
        st.markdown("**Bear / Bull**")
        bear_growth = st.number_input("FCF Growth (Bear)", value=max(0.0, round(default_growth - 0.05, 2)), step=0.01, format="%.2f")
        bear_wacc = st.number_input("WACC (Bear)", value=0.11, step=0.005, format="%.3f")
        bull_growth = st.number_input("FCF Growth (Bull)", value=round(default_growth + 0.04, 2), step=0.01, format="%.2f")
        bull_wacc = st.number_input("WACC (Bull)", value=0.08, step=0.005, format="%.3f")
        bull_term = st.number_input("Terminal Growth (Bull)", value=0.03, step=0.005, format="%.3f")

    bear_val = simple_dcf(fcf0, bear_growth, 0.02, bear_wacc, shares, net_debt)
    base_val = simple_dcf(fcf0, base_growth, base_term, base_wacc, shares, net_debt)
    bull_val = simple_dcf(fcf0, bull_growth, bull_term, bull_wacc, shares, net_debt)

    st.markdown("### DCF Results")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Bear Case", f"${bear_val:,.2f}" if bear_val else "Invalid inputs")
    r2.metric("Base Case", f"${base_val:,.2f}" if base_val else "Invalid inputs")
    r3.metric("Bull Case", f"${bull_val:,.2f}" if bull_val else "Invalid inputs")
    if price != "—" and base_val and float(price) > 0:
        upside = (base_val / float(price) - 1) * 100
        r4.metric("Upside/(Downside) to Base", f"{upside:+.1f}%")

    # Sensitivity table
    st.markdown("### Sensitivity Table (Base terminal growth)")
    st.caption("Shows how per-share value changes with growth rate (rows) and WACC (columns).")
    growth_range = [round(base_growth + d, 3) for d in [-0.04, -0.02, 0.0, 0.02, 0.04]]
    wacc_range = [round(base_wacc + d, 3) for d in [-0.02, -0.01, 0.0, 0.01, 0.02]]
    sens_data = []
    for g in growth_range:
        row = {"FCF Growth": f"{g:.1%}"}
        for w in wacc_range:
            val = simple_dcf(fcf0, g, base_term, w, shares, net_debt)
            row[f"WACC {w:.1%}"] = f"${val:,.0f}" if val else "—"
        sens_data.append(row)
    st.dataframe(pd.DataFrame(sens_data).set_index("FCF Growth"), use_container_width=True)

    with st.expander("DCF methodology & caveats"):
        st.markdown("""
        - 5-year explicit forecast of free cash flow growing at the chosen rate  
        - Terminal value uses Gordon Growth Model: TV = FCF₆ / (WACC − g)  
        - Equity value = Enterprise value − Net Debt  
        - Pre-filled FCF uses Finnhub *Cash Flow per Share × Shares* (closer to operating cash flow).  
          **Always replace with true Free Cash Flow (OCF − Capex)** from the latest 10-K.  
        - This is an educational tool only — not a precise intrinsic value.
        """)

# ---- Tab 5: Peers & Analysts ----
with tabs[5]:
    st.subheader("Analyst Views")
    if recs and isinstance(recs, list) and len(recs) > 0:
        st.dataframe(pd.DataFrame(recs), use_container_width=True)
    else:
        st.write("No recommendation trends available.")

    if target:
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Target Mean", f"${safe_get(target, 'targetMean')}")
        t2.metric("High", f"${safe_get(target, 'targetHigh')}")
        t3.metric("Low", f"${safe_get(target, 'targetLow')}")
        t4.metric("# Analysts", safe_get(target, "numberOfAnalysts"))

    # Earnings Surprise History (NEW)
    st.markdown("---")
    st.subheader("Earnings Surprise History")
    help_box("earnings_surprise", "Earnings Surprise")
    if earnings and isinstance(earnings, list) and len(earnings) > 0:
        earn_rows = []
        for e in earnings[:8]:
            earn_rows.append({
                "Period": e.get("period"),
                "Year": e.get("year"),
                "Q": e.get("quarter"),
                "Estimate": e.get("estimate"),
                "Actual": e.get("actual"),
                "Surprise": e.get("surprise"),
                "Surprise %": e.get("surprisePercent"),
            })
        st.dataframe(pd.DataFrame(earn_rows), use_container_width=True, hide_index=True)

        # Quick summary
        surprises = [e.get("surprisePercent") for e in earnings if e.get("surprisePercent") is not None]
        if surprises:
            beats = sum(1 for s in surprises if s > 0)
            misses = sum(1 for s in surprises if s < 0)
            avg_surp = sum(surprises) / len(surprises)
            c1, c2, c3 = st.columns(3)
            c1.metric("Beats (recent)", beats)
            c2.metric("Misses (recent)", misses)
            c3.metric("Avg Surprise %", f"{avg_surp:.1f}%")
        st.caption("Positive surprise % = beat. Useful for assessing estimate momentum and management guidance quality.")
    else:
        st.info("No earnings surprise data available for this ticker.")

    st.markdown("---")
    st.subheader("Peer Comparison (Multi-metric)")
    peer_list = peers[:5] if isinstance(peers, list) else []
    if peer_list:
        st.write("Peers from Finnhub:", ", ".join(peer_list))
        st.caption("Loads key valuation, profitability and growth metrics for the company + peers.")
        if st.button("Load / Refresh Peer Table", type="primary"):
            with st.spinner("Loading peer data…"):
                peer_rows = []
                all_syms = [ticker] + [p for p in peer_list if p != ticker]
                for sym in all_syms:
                    m = finnhub_get("stock/metric", api_key, symbol=sym, metric="all")
                    ms = safe_get(m, "metric", default={}) if m else {}
                    q = finnhub_get("quote", api_key, symbol=sym)
                    fcf_val = None
                    if sym == ticker and hist and hist[0].get("Free Cash Flow"):
                        fcf_val = round(hist[0]["Free Cash Flow"] / 1e6, 0)
                    peer_rows.append({
                        "Ticker": sym,
                        "Price": safe_get(q, "c"),
                        "P/E": safe_get(ms, "peBasicExclExtraTTM"),
                        "Fwd P/E": safe_get(ms, "peNormalizedAnnual"),
                        "EV/EBITDA": safe_get(ms, "currentEv/ebitdaTTM"),
                        "P/S": safe_get(ms, "psTTM"),
                        "P/FCF": safe_get(ms, "pfcfShareTTM"),
                        "Gross Margin %": safe_get(ms, "grossMarginTTM"),
                        "Op. Margin %": safe_get(ms, "operatingMarginTTM"),
                        "ROE %": safe_get(ms, "roeTTM"),
                        "ROIC %": safe_get(ms, "roiTTM"),
                        "Debt/Equity": safe_get(ms, "totalDebt/totalEquityAnnual"),
                        "Rev Growth 5Y %": safe_get(ms, "revenueGrowth5Y"),
                        "EPS Growth 5Y %": safe_get(ms, "epsGrowth5Y"),
                        "FCF ($M)": fcf_val,
                    })
                st.session_state["peer_table"] = peer_rows

        if st.session_state.get("peer_table"):
            st.dataframe(pd.DataFrame(st.session_state["peer_table"]), use_container_width=True, hide_index=True)
            st.caption("Compare carefully — business models and accounting can differ.")

        # Multi-year peer financials (limited to avoid rate limits)
        st.markdown("#### Multi-year Revenue & FCF (selected peers)")
        st.caption("Fetches reported financials for up to 3 peers. Use sparingly on free tier.")
        if st.button("Load multi-year peer financials"):
            with st.spinner("Fetching reported financials for peers (this may take 10–20s)…"):
                peer_hist_data = {}
                # Always include main ticker (already have hist)
                if hist:
                    peer_hist_data[ticker] = hist[:4]
                for sym in peer_list[:3]:
                    if sym == ticker:
                        continue
                    raw = finnhub_get("stock/financials-reported", api_key, symbol=sym)
                    ph = parse_reported_financials(raw)
                    if ph:
                        peer_hist_data[sym] = ph[:4]
                st.session_state["peer_hist"] = peer_hist_data

        if st.session_state.get("peer_hist"):
            for sym, rows in st.session_state["peer_hist"].items():
                st.markdown(f"**{sym}**")
                disp = []
                for r in rows:
                    def m(v):
                        return round(v / 1e6, 1) if v is not None else None
                    disp.append({
                        "Year": r["Year"],
                        "Revenue ($M)": m(r["Revenue"]),
                        "FCF ($M)": m(r["Free Cash Flow"]),
                        "Op. Income ($M)": m(r["Operating Income"]),
                    })
                st.dataframe(pd.DataFrame(disp), use_container_width=True, hide_index=True)
    else:
        st.write("No peers returned for this ticker.")

# ---- Tab 5b: Positioning (Stage 2) ----
with tabs[6]:
    st.subheader("Positioning & Sentiment")
    help_box("positioning", "Positioning")

    # Liquidity from candles
    st.markdown("#### Liquidity")
    help_box("liquidity", "Liquidity / Average Volume")
    if candles and safe_get(candles, "s") == "ok":
        vols = candles.get("v") or []
        if len(vols) >= 20:
            avg20 = sum(vols[-20:]) / 20
            avg60 = sum(vols[-60:]) / min(60, len(vols)) if len(vols) >= 5 else avg20
            last_vol = vols[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Last Volume", f"{last_vol:,.0f}")
            c2.metric("20-day Avg Volume", f"{avg20:,.0f}")
            c3.metric("vs 20-day Avg", f"{(last_vol/avg20 - 1)*100:+.0f}%" if avg20 else "—")
            if avg20 < 100_000:
                st.warning("Relatively low average volume — expect higher slippage on larger orders.")
            elif avg20 > 5_000_000:
                st.success("High liquidity — suitable for larger position sizes.")
        else:
            st.write("Insufficient volume history.")
    else:
        st.write("Volume data not available.")

    st.markdown("---")
    st.markdown("#### Insider Transactions (recent)")
    help_box("insider", "Insider Transactions")
    if insider and isinstance(insider, dict):
        rows = insider.get("data") or []
        if rows:
            # Summarize last ~90 days style (first 30 records)
            recent = rows[:25]
            buys = [r for r in recent if r.get("transactionCode") in ("P", "A") and (r.get("change") or 0) > 0]
            sells = [r for r in recent if r.get("transactionCode") in ("S", "D") or (r.get("change") or 0) < 0]
            c1, c2 = st.columns(2)
            c1.metric("Recent buy-type filings", len(buys))
            c2.metric("Recent sell-type filings", len(sells))

            display = []
            for r in recent[:15]:
                display.append({
                    "Name": r.get("name"),
                    "Date": r.get("transactionDate"),
                    "Code": r.get("transactionCode"),
                    "Change": r.get("change"),
                    "Shares": r.get("share"),
                    "Price": r.get("transactionPrice"),
                })
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
            st.caption("Codes: P/A ≈ purchase · S/D ≈ sale. Always read footnotes — many sales are planned 10b5-1 or tax-related.")
        else:
            st.info("No recent insider transactions returned.")
    else:
        st.info("Insider data not available for this ticker.")

    st.markdown("---")
    st.markdown("#### Analyst Recommendations & Targets")
    help_box("recommendations", "Analyst Recommendations")
    if recs and isinstance(recs, list) and len(recs) > 0:
        st.dataframe(pd.DataFrame(recs).head(6), use_container_width=True, hide_index=True)
    else:
        st.write("No recommendation trend data.")

    if target:
        help_box("price_target", "Price Target")
        t1, t2, t3 = st.columns(3)
        t1.metric("Mean Target", f"${safe_get(target, 'targetMean')}")
        t2.metric("High / Low", f"${safe_get(target, 'targetHigh')} / ${safe_get(target, 'targetLow')}")
        if price != "—" and safe_get(target, "targetMean") not in ("—", None):
            try:
                implied = (float(target["targetMean"]) / float(price) - 1) * 100
                t3.metric("Implied Upside", f"{implied:+.1f}%")
            except Exception:
                t3.metric("Implied Upside", "—")

    st.markdown("---")
    st.markdown("#### Short Interest")
    help_box("short_interest", "Short Interest")
    st.info("Short interest detail is not available on the Finnhub free tier (403). Use exchange or broker data for days-to-cover and % of float.")

# ---- Tab 6: Technicals (Stage 1) ----
with tabs[7]:
    st.subheader("Price, Trend, Volatility & Relative Strength")
    if candles and safe_get(candles, "s") == "ok":
        df = pd.DataFrame({
            "Date": pd.to_datetime(candles["t"], unit="s"),
            "Open": candles["o"], "High": candles["h"], "Low": candles["l"],
            "Close": candles["c"], "Volume": candles["v"]
        }).set_index("Date").sort_index()

        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA50"] = df["Close"].rolling(50).mean()
        if len(df) >= 200:
            df["MA200"] = df["Close"].rolling(200).mean()
        df["RSI"] = compute_rsi(df["Close"])
        macd_line, signal_line, macd_hist = compute_macd(df["Close"])
        df["MACD"] = macd_line
        df["Signal"] = signal_line
        df["ATR"] = compute_atr(df)

        # --- Summary metrics row ---
        short_trend = classify_trend(df["Close"], 10, 20)
        inter_trend = classify_trend(df["Close"], 20, 50)
        primary_trend = classify_trend(df["Close"], 50, 200) if len(df) >= 200 else "Insufficient data"

        latest_atr = df["ATR"].dropna().iloc[-1] if not df["ATR"].dropna().empty else None
        latest_close = float(df["Close"].iloc[-1])
        atr_pct = (latest_atr / latest_close * 100) if latest_atr and latest_close else None

        avg_vol = df["Volume"].tail(20).mean()
        latest_vol = df["Volume"].iloc[-1]
        vol_ratio = latest_vol / avg_vol if avg_vol and avg_vol > 0 else None

        # Relative strength vs SPY and sector
        rs_val = None
        if spy_candles and safe_get(spy_candles, "s") == "ok":
            spy_df = pd.DataFrame({
                "Date": pd.to_datetime(spy_candles["t"], unit="s"),
                "Close": spy_candles["c"]
            }).set_index("Date").sort_index()
            common = df.index.intersection(spy_df.index)
            if len(common) >= 63:
                rs_val = relative_strength(df.loc[common, "Close"], spy_df.loc[common, "Close"], 63)

        rs_sector = None
        if sector_candles and safe_get(sector_candles, "s") == "ok":
            sec_df = pd.DataFrame({
                "Date": pd.to_datetime(sector_candles["t"], unit="s"),
                "Close": sector_candles["c"]
            }).set_index("Date").sort_index()
            common_s = df.index.intersection(sec_df.index)
            if len(common_s) >= 63:
                rs_sector = relative_strength(df.loc[common_s, "Close"], sec_df.loc[common_s, "Close"], 63)

        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.metric("Short-term Trend", short_trend)
        s2.metric("Intermediate Trend", inter_trend)
        s3.metric("Primary Trend", primary_trend)
        s4.metric("ATR (14)", f"{latest_atr:.2f}" if latest_atr else "—",
                  f"{atr_pct:.1f}% of price" if atr_pct else None)
        s5.metric("RS vs SPY (3M)", f"{rs_val:+.1f}%" if rs_val is not None else "—")
        s6.metric(f"RS vs {sector_etf or 'Sector'} (3M)", f"{rs_sector:+.1f}%" if rs_sector is not None else "—")

        help_box("trend", "Trend Classification")
        help_box("atr", "ATR (Average True Range)")
        help_box("rel_strength", "Relative Strength vs SPY")
        help_box("sector_rs", "Relative Strength vs Sector")

        if vol_ratio is not None:
            st.caption(f"Volume today vs 20-day average: **{vol_ratio:.1f}x** "
                       f"{'(elevated)' if vol_ratio > 1.5 else '(quiet)' if vol_ratio < 0.7 else ''}")
            help_box("volume", "Volume Context")

        # --- Stage 3: Structure & Levels ---
        st.markdown("#### Key Levels & Structure")
        help_box("support_resistance", "Support & Resistance")
        help_box("ma_distance", "Distance from Moving Averages")

        ma20_v = float(df["MA20"].iloc[-1]) if not df["MA20"].isna().iloc[-1] else None
        ma50_v = float(df["MA50"].iloc[-1]) if not df["MA50"].isna().iloc[-1] else None
        ma200_v = float(df["MA200"].iloc[-1]) if "MA200" in df.columns and not df["MA200"].isna().iloc[-1] else None
        dists = ma_distances(latest_close, ma20_v, ma50_v, ma200_v)

        dcols = st.columns(len(dists) if dists else 1)
        for i, (label, val) in enumerate(dists.items()):
            dcols[i].metric(label, f"{val:+.1f}%")

        support, resist = find_swing_levels(df)
        lc1, lc2 = st.columns(2)
        with lc1:
            st.markdown("**Nearby Support (swing lows)**")
            if support:
                for s in support:
                    dist = (latest_close / s - 1) * 100
                    st.write(f"${s:,.2f}  ({dist:+.1f}% from price)")
            else:
                st.write("—")
        with lc2:
            st.markdown("**Nearby Resistance (swing highs)**")
            if resist:
                for r in resist:
                    dist = (latest_close / r - 1) * 100
                    st.write(f"${r:,.2f}  ({dist:+.1f}% from price)")
            else:
                st.write("—")
        st.caption("Swing levels are approximate. Combine with volume and higher-timeframe structure.")

        # --- Entry / Exit framework ---
        st.markdown("#### Entry & Exit Levels")
        help_box("entry_exit", "Entry & Exit")
        st.caption("Framework levels from structure + ATR. Not trade advice — adjust to your plan.")

        # Suggested long framework
        nearest_sup = None
        if support:
            below = [s for s in support if s < latest_close]
            nearest_sup = max(below) if below else min(support)
        nearest_res = None
        if resist:
            above = [r for r in resist if r > latest_close]
            nearest_res = min(above) if above else max(resist)

        atr_v = float(latest_atr) if latest_atr else (latest_close * 0.02)
        # Pullback entry zone: between nearest support and a small ATR buffer, or MA20
        long_entry = nearest_sup if nearest_sup else (ma20_v if ma20_v else latest_close * 0.98)
        if ma20_v and nearest_sup:
            long_entry = min(ma20_v, nearest_sup) if short_trend == "Downtrend" else (nearest_sup + (latest_close - nearest_sup) * 0.3)
        long_stop = (nearest_sup - atr_v) if nearest_sup else (latest_close - 1.5 * atr_v)
        long_t1 = nearest_res if nearest_res else (latest_close + 2 * atr_v)
        long_t2 = (nearest_res + atr_v) if nearest_res else (latest_close + 3.5 * atr_v)

        short_entry = nearest_res if nearest_res else (ma20_v if ma20_v else latest_close * 1.02)
        short_stop = (nearest_res + atr_v) if nearest_res else (latest_close + 1.5 * atr_v)
        short_t1 = nearest_sup if nearest_sup else (latest_close - 2 * atr_v)

        bias = "Long-biased structure" if short_trend == "Uptrend" or inter_trend == "Uptrend" else (
            "Short-biased structure" if short_trend == "Downtrend" or inter_trend == "Downtrend" else "Neutral / range"
        )
        st.write(f"**Structure bias (from trends):** {bias}")

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Suggested entry (long)", f"${long_entry:,.2f}")
        e2.metric("Stop (long)", f"${long_stop:,.2f}")
        e3.metric("Target 1 (long)", f"${long_t1:,.2f}")
        e4.metric("Target 2 (long)", f"${long_t2:,.2f}")

        risk = latest_close - long_stop if long_stop < latest_close else atr_v
        reward = long_t1 - latest_close if long_t1 > latest_close else atr_v
        rr = (reward / risk) if risk and risk > 0 else None
        if rr:
            st.caption(f"Illustrative R:R to Target 1 from current price ≈ **{rr:.1f}:1** (using stop ${long_stop:,.2f}).")

        with st.expander("Short-side sketch (if fading strength)"):
            s1, s2, s3 = st.columns(3)
            s1.metric("Suggested entry (short)", f"${short_entry:,.2f}")
            s2.metric("Stop (short)", f"${short_stop:,.2f}")
            s3.metric("Target 1 (short)", f"${short_t1:,.2f}")

        st.markdown("**Your plan (editable)**")
        pc1, pc2, pc3, pc4 = st.columns(4)
        with pc1:
            user_entry = st.number_input("My entry", value=float(round(long_entry, 2)), step=0.01, key="user_entry")
        with pc2:
            user_stop = st.number_input("My stop / exit invalidation", value=float(round(long_stop, 2)), step=0.01, key="user_stop")
        with pc3:
            user_t1 = st.number_input("My target / take-profit", value=float(round(long_t1, 2)), step=0.01, key="user_t1")
        with pc4:
            if user_entry and user_stop and user_entry != user_stop:
                user_rr = abs(user_t1 - user_entry) / abs(user_entry - user_stop)
                st.metric("Your R:R", f"{user_rr:.2f}:1")
            else:
                st.metric("Your R:R", "—")
        st.session_state["plan_entry"] = user_entry
        st.session_state["plan_stop"] = user_stop
        st.session_state["plan_target"] = user_t1

        st.line_chart(df[["Close", "MA20", "MA50"] + (["MA200"] if "MA200" in df.columns else [])])

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**RSI (14)**")
            st.line_chart(df["RSI"].dropna())
            latest_rsi = df["RSI"].dropna().iloc[-1] if not df["RSI"].dropna().empty else None
            if latest_rsi is not None:
                label = "(Overbought)" if latest_rsi > 70 else "(Oversold)" if latest_rsi < 30 else ""
                st.caption(f"Latest RSI: {latest_rsi:.1f} {label}")
            help_box("rsi", "RSI")
        with c2:
            st.markdown("**MACD**")
            st.line_chart(df[["MACD", "Signal"]].dropna())
            help_box("macd", "MACD")

        st.bar_chart(df["Volume"])
        st.dataframe(df[["Close", "MA20", "MA50", "RSI", "MACD", "ATR"]].tail(12), use_container_width=True)
    else:
        st.warning("Price history not available.")

# ---- Tab 7: Your Analysis ----
with tabs[8]:
    st.subheader("Your Qualitative Analysis")
    st.caption("Notes can be saved/loaded via the sidebar.")

    with st.expander("Research workflow checklist", expanded=False):
        help_box("workflow", "Workflow")
        st.markdown("""
1. **Load data** — confirm price, financials, peers, and next earnings date  
2. **Market context** — risk-on/off, relative strength vs SPY  
3. **Fundamentals** — FCF trend, margins, balance sheet  
4. **Valuation** — DCF scenarios + peer multiples  
5. **Positioning** — insiders, liquidity, analyst stance  
6. **Technicals** — trend, levels, ATR for stop distance  
7. **Thesis** — write bull / base / bear; list what would prove you wrong  
8. **Risk** — size, stop, invalidation level, earnings proximity  
9. **Save notes** — download JSON before leaving the session  
        """)
        if next_earn and next_earn.get("date"):
            help_box("next_earnings", "Next Earnings Date")
            st.write(f"Upcoming event: **{next_earn.get('date')}** — factor into timing and position size.")

    st.text_area("Business Quality / Moat", height=120, key="moat")
    st.text_area("Industry & Competitive Position + Market Environment notes", height=110, key="industry")
    st.text_area("Bull Case (5+ specific reasons)", height=140, key="bull")
    st.text_area("Bear Case (5+ specific risks)", height=140, key="bear")
    st.text_area("Key Catalysts (next 2–4 quarters)", height=100, key="catalysts")
    st.text_area("What the market is pricing in", height=100, key="pricing")
    st.text_area("Key metrics to watch + thresholds", height=100, key="watch")

# ---- Tab 8: Scorecard ----
with tabs[9]:
    st.subheader("100-Point Analytical Scorecard")
    st.caption("Research framework only — not a return prediction.")
    help_box("scorecard", "Scorecard")
    help_box("score_suggest", "Score Suggestions")

    # Light rules-based suggestions from available data
    sug = {}
    if metric_series:
        roe = safe_get(metric_series, "roeTTM")
        gm = safe_get(metric_series, "grossMarginTTM")
        de = safe_get(metric_series, "totalDebt/totalEquityAnnual")
        rg = safe_get(metric_series, "revenueGrowth5Y")
        pe = safe_get(metric_series, "peBasicExclExtraTTM")
        if isinstance(roe, (int, float)):
            sug["Profitability"] = 8 if roe > 20 else 6 if roe > 10 else 4
        if isinstance(gm, (int, float)):
            sug["Fundamentals"] = 14 if gm > 40 else 11 if gm > 25 else 8
        if isinstance(de, (int, float)):
            sug["Balance Sheet"] = 8 if de < 0.5 else 6 if de < 1.5 else 3
        if isinstance(rg, (int, float)):
            sug["Growth"] = 12 if rg > 15 else 9 if rg > 8 else 5
        if isinstance(pe, (int, float)):
            sug["Valuation"] = 12 if pe < 15 else 9 if pe < 25 else 5
    if candles and safe_get(candles, "s") == "ok":
        # reuse trend if computed in session — simple fallback
        sug["Technical Setup"] = 3

    if sug:
        st.markdown("**Suggested starting scores** (override freely):")
        st.write(" · ".join([f"{k}: {v}" for k, v in sug.items()]))
        st.caption("Based on simple rules from ROE, margins, leverage, growth, and P/E. Not a recommendation.")

    c1, c2 = st.columns(2)
    with c1:
        s_fund = st.slider("Fundamentals (20)", 0, 20, int(sug.get("Fundamentals", 10)))
        s_growth = st.slider("Growth (15)", 0, 15, int(sug.get("Growth", 8)))
        s_profit = st.slider("Profitability (10)", 0, 10, int(sug.get("Profitability", 6)))
        s_bs = st.slider("Balance Sheet (10)", 0, 10, int(sug.get("Balance Sheet", 7)))
        s_moat = st.slider("Competitive Advantage (10)", 0, 10, 6)
    with c2:
        s_val = st.slider("Valuation (15)", 0, 15, int(sug.get("Valuation", 7)))
        s_ind = st.slider("Industry Outlook (5)", 0, 5, 3)
        s_tech = st.slider("Technical Setup (5)", 0, 5, int(sug.get("Technical Setup", 3)))
        s_cat = st.slider("Catalysts (5)", 0, 5, 3)
        s_rr = st.slider("Risk/Reward (5)", 0, 5, 3)

    total = s_fund + s_growth + s_profit + s_bs + s_moat + s_val + s_ind + s_tech + s_cat + s_rr
    st.metric("Total Score", f"{total} / 100")

    st.subheader("Investment Theses")
    st.text_area("Bull Thesis", height=90, key="thesis_bull")
    st.text_area("Base Thesis", height=90, key="thesis_base")
    st.text_area("Bear Thesis", height=90, key="thesis_bear")

# ---- Tab 9: Export ----
with tabs[10]:
    st.subheader("Export Full Report")
    st.caption("Generate a Markdown or PDF summary of the current analysis.")

    # Safe access to values that may not be set if tabs order varies
    _bear = locals().get("bear_val")
    _base = locals().get("base_val")
    _bull = locals().get("bull_val")
    _total = locals().get("total", "—")
    _ne = ""
    if next_earn and next_earn.get("date"):
        _ne = f"{next_earn.get('date')} ({next_earn.get('hour', '')})"

    report = f"""# Equity Research Report: {ticker}
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Horizon:** {horizon} | **Risk:** {risk}

## Snapshot
- Price: ${price}
- Change: {change} ({change_pct}%)
- Market Cap: {mktcap_str}
- Industry: {safe_get(profile, 'finnhubIndustry')}
- Next earnings: {_ne or 'N/A'}

## Key Metrics
- Trailing P/E: {safe_get(metric_series, 'peBasicExclExtraTTM')}
- Gross Margin: {safe_get(metric_series, 'grossMarginTTM')}%
- ROE: {safe_get(metric_series, 'roeTTM')}%
- Revenue Growth 5Y: {safe_get(metric_series, 'revenueGrowth5Y')}%
- Debt/Equity: {safe_get(metric_series, 'totalDebt/totalEquityAnnual')}
- EV/EBITDA: {safe_get(metric_series, 'currentEv/ebitdaTTM')}
- P/S: {safe_get(metric_series, 'psTTM')}

## DCF Results
- Bear: ${f'{_bear:,.2f}' if _bear else 'N/A'}
- Base: ${f'{_base:,.2f}' if _base else 'N/A'}
- Bull: ${f'{_bull:,.2f}' if _bull else 'N/A'}

## Peers
{', '.join(peers[:10]) if isinstance(peers, list) else 'N/A'}

## Analyst Target
Mean: ${safe_get(target, 'targetMean')} | High: ${safe_get(target, 'targetHigh')} | Low: ${safe_get(target, 'targetLow')}

## Entry / Exit plan (user)
- Entry: ${st.session_state.get('plan_entry', '—')}
- Stop / invalidation: ${st.session_state.get('plan_stop', '—')}
- Target: ${st.session_state.get('plan_target', '—')}

## Qualitative
**Moat:** {st.session_state.get('moat', '')}
**Bull Case:** {st.session_state.get('bull', '')}
**Bear Case:** {st.session_state.get('bear', '')}
**Catalysts:** {st.session_state.get('catalysts', '')}

## Scorecard: {_total}/100

## Theses
**Bull:** {st.session_state.get('thesis_bull', '')}
**Base:** {st.session_state.get('thesis_base', '')}
**Bear:** {st.session_state.get('thesis_bear', '')}

---
*Equity Research Analyzer · Free data via Finnhub · Not investment advice*
"""

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download Markdown (.md)",
            report,
            file_name=f"{ticker}_research_{datetime.now().strftime('%Y%m%d')}.md",
            mime="text/markdown",
            use_container_width=True
        )
    with c2:
        if HAS_PDF:
            pdf_ctx = {
                "ticker": ticker,
                "name": safe_get(profile, "name"),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "horizon": horizon,
                "risk": risk,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "mktcap": mktcap_str,
                "industry": safe_get(profile, "finnhubIndustry"),
                "next_earn": _ne,
                "pe": safe_get(metric_series, "peBasicExclExtraTTM"),
                "gm": safe_get(metric_series, "grossMarginTTM"),
                "roe": safe_get(metric_series, "roeTTM"),
                "rev_g": safe_get(metric_series, "revenueGrowth5Y"),
                "de": safe_get(metric_series, "totalDebt/totalEquityAnnual"),
                "ev": safe_get(metric_series, "currentEv/ebitdaTTM"),
                "ps": safe_get(metric_series, "psTTM"),
                "fcf_note": "See historical FCF table in app",
                "bear": f"{_bear:,.2f}" if _bear else "N/A",
                "base": f"{_base:,.2f}" if _base else "N/A",
                "bull": f"{_bull:,.2f}" if _bull else "N/A",
                "peers": ", ".join(peers[:10]) if isinstance(peers, list) else "N/A",
                "target_mean": safe_get(target, "targetMean"),
                "target_high": safe_get(target, "targetHigh"),
                "target_low": safe_get(target, "targetLow"),
                "moat": st.session_state.get("moat", ""),
                "bull_case": st.session_state.get("bull", ""),
                "bear_case": st.session_state.get("bear", ""),
                "catalysts": st.session_state.get("catalysts", ""),
                "score": _total,
                "thesis_bull": st.session_state.get("thesis_bull", ""),
                "thesis_base": st.session_state.get("thesis_base", ""),
                "thesis_bear": st.session_state.get("thesis_bear", ""),
            }
            try:
                pdf_bytes = build_pdf_report(pdf_ctx)
                st.download_button(
                    "Download PDF Report",
                    pdf_bytes,
                    file_name=f"{ticker}_research_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e:
                st.warning(f"PDF generation issue: {e}")
        else:
            st.info("PDF support requires reportlab. Markdown export still works.")

    with st.expander("Preview Markdown"):
        st.code(report, language="markdown")

# ---- Tab 10: Watchlist Batch Dashboard ----
with tabs[11]:
    st.subheader("Watchlist Batch Dashboard")
    st.caption("Run from the sidebar (**Run batch dashboard**). Includes price, bias, **entry / stop / target**, R:R, and next earnings.")
    help_box("entry_exit", "Entry & Exit (batch)")
    help_box("watchlist", "Watchlist Batch")

    batch = st.session_state.get("wl_batch")
    if not batch:
        st.info("Add tickers in the sidebar watchlist, then click **Run batch dashboard**.")
    else:
        st.caption(f"Last run: {st.session_state.get('wl_batch_time', '')} · {len(batch)} names · levels are framework only, not signals")
        df_b = pd.DataFrame(batch)
        st.dataframe(df_b, use_container_width=True, hide_index=True)

        # Highlight earnings soon
        soon = []
        for r in batch:
            d = r.get("Days to Earn")
            if isinstance(d, int) and 0 <= d <= 14:
                soon.append(f"{r['Ticker']} ({d}d · {r.get('Next Earnings')})")
        if soon:
            st.warning("Earnings within 14 days: " + " · ".join(soon))

        # Compact text summary for copy / future Telegram
        lines = [
            f"Watchlist batch · {st.session_state.get('wl_batch_time', '')}",
            f"Names: {len(batch)} · Entry/Stop/Target = structure+ATR framework (not advice)",
            "",
        ]
        for r in batch:
            chg = r.get("Chg %")
            chg_s = f"{chg}%" if chg not in (None, "—") else "—"
            lines.append(
                f"{r.get('Ticker')}: ${r.get('Price')} ({chg_s}) | {r.get('Bias')} | "
                f"Entry ${r.get('Entry')} / Stop ${r.get('Stop')} / Tgt ${r.get('Target')} "
                f"(R:R {r.get('R:R')}) | Earn {r.get('Next Earnings')} ({r.get('Days to Earn')}d)"
            )
        summary_txt = "\n".join(lines)
        st.download_button(
            "Download batch summary (.txt)",
            summary_txt,
            file_name=f"watchlist_batch_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
        with st.expander("Preview summary text"):
            st.code(summary_txt)

st.markdown("---")
st.caption("Free data via Finnhub. Always cross-check with primary filings. Research framework only — not investment advice.")
