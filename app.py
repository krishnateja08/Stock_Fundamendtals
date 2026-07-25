"""
Stockizen Research - Single-file Flask dashboard (NO LLM / NO AI TEXT GENERATION)
-----------------------------------------------------------------------------------
A trader-terminal-style dashboard for NSE (India) and US stocks. All data comes
live from Yahoo Finance (yfinance). All scoring/badges/verdicts are fixed
if/else rules in Python - there is no LLM call anywhere in this file.

SETUP
1. pip install flask yfinance pandas
2. Run:  python3 app.py   (use python3 explicitly, not a `py` alias/launcher)
3. Open: http://127.0.0.1:7003

MARKETS
- Select "India (NSE)" or "USA" next to the search box.
- Type a company name (small built-in lookup for both markets) or a raw
  symbol. India symbols get ".NS" appended automatically (e.g. RELIANCE ->
  RELIANCE.NS); US symbols are used as-is (e.g. AAPL). You can also type a
  full ticker with an explicit suffix yourself (e.g. "TATASTEEL.BO",
  "RELIANCE.NS") and it will be used exactly as typed, regardless of which
  market radio button is selected.

FEATURES
- Top summary bar: price/change, 52W range slider, analyst target/upside,
  verdict badge, market cap chip
- Three-panel layout: left (recent/quick tickers + sector shortcuts),
  center (metric cards with sparklines/gauges/donuts), right (collapsible
  drawer with bull/bear points, verdict detail, peer comparison)
- Rule-based badges: Verdict / Growth / Risk / Valuation
- Trader Mode vs Investor Mode toggle
- Dark / Light / AMOLED themes + accent color + compact mode (saved in
  the browser via localStorage - this is a local single-user tool, not a
  claude.ai artifact, so localStorage is fine here)
- Data Quality indicator (how many key fields Yahoo actually returned)
- Peer comparison (small hardcoded sector-peer map; optional, on demand)

LIMITATIONS (being upfront about these)
- "Watchlist" is just your last 8 searches, stored in a browser session
  cookie - not a real persisted database.
- Peer comparison only works for ~15 well-known large caps in PEER_MAP
  below; add more tickers to that dict if you want wider coverage.
- Yahoo Finance does not expose exact NSE Promoter/FII/DII splits - the
  closest available fields (Insider % / Institutional %) are shown instead.
"""

import os
import math
import time
from flask import Flask, request, render_template_string, session
import yfinance as yf

APP_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, root_path=APP_DIR, instance_path=os.path.join(APP_DIR, "instance"))
app.secret_key = os.environ.get("STOCKIZEN_SECRET", os.urandom(24))

DISCLAIMER = (
    "SEBI Registered Research Analyst - INH000017675 | BSE Enlistment No: 6309\n"
    "@stockizen_research\n"
    "This report is generated mechanically from public Yahoo Finance data using fixed "
    "rules and thresholds. No AI/LLM was used to write any part of it. Not investment advice."
)

NAME_TO_TICKER = {
    "reliance": "RELIANCE", "reliance industries": "RELIANCE",
    "tcs": "TCS", "tata consultancy services": "TCS",
    "infosys": "INFY", "hdfc bank": "HDFCBANK", "icici bank": "ICICIBANK",
    "sbi": "SBIN", "state bank of india": "SBIN", "itc": "ITC",
    "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR",
    "bharti airtel": "BHARTIARTL", "airtel": "BHARTIARTL",
    "kotak mahindra bank": "KOTAKBANK", "larsen": "LT", "l&t": "LT",
    "asian paints": "ASIANPAINT", "maruti suzuki": "MARUTI", "maruti": "MARUTI",
    "wipro": "WIPRO", "axis bank": "AXISBANK", "bajaj finance": "BAJFINANCE",
    "hcl technologies": "HCLTECH", "hcl tech": "HCLTECH",
    "titan": "TITAN", "sun pharma": "SUNPHARMA", "ntpc": "NTPC",
    "adani enterprises": "ADANIENT", "adani ports": "ADANIPORTS",
    "tata motors": "TATAMOTORS", "tata steel": "TATASTEEL",
    "ultratech cement": "ULTRACEMCO", "power grid": "POWERGRID",
}

# US company-name lookup. Unlike Indian tickers, US tickers are used as-is
# (no exchange suffix), since Yahoo Finance lists them directly (e.g. AAPL).
NAME_TO_TICKER_US = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "tesla": "TSLA", "nvidia": "NVDA", "meta": "META",
    "facebook": "META", "netflix": "NFLX", "berkshire hathaway": "BRK-B",
    "berkshire": "BRK-B", "jpmorgan": "JPM", "jp morgan": "JPM",
    "visa": "V", "mastercard": "MA", "walmart": "WMT", "disney": "DIS",
    "coca cola": "KO", "coca-cola": "KO", "pepsi": "PEP", "pepsico": "PEP",
    "exxon": "XOM", "exxon mobil": "XOM", "intel": "INTC", "amd": "AMD",
    "salesforce": "CRM", "adobe": "ADBE", "oracle": "ORCL", "ibm": "IBM",
    "boeing": "BA", "mcdonalds": "MCD", "mcdonald's": "MCD", "nike": "NKE",
    "starbucks": "SBUX", "paypal": "PYPL", "uber": "UBER", "airbnb": "ABNB",
}

# Quick-pick tickers shown in the left panel
QUICK_PICKS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS", "SBIN.NS"]
US_QUICK_PICKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]

# Broader India watchlist (top NSE names by volume + sector BEES ETFs), shown
# as a scrollable list in the left panel so users aren't limited to the 6
# QUICK_PICKS above.
NIFTY_500_WATCHLIST = [
    # ── Rank 1-10 by Volume ──────────────────────────────────
    "ADANIPOWER.NS", "INFY.NS",       "WIPRO.NS",       "ETERNAL.NS",
    "JIOFIN.NS",     "HDFCBANK.NS",   "UNIONBANK.NS",   "TATASTEEL.NS",
    "KOTAKBANK.NS",  "VEDL.NS",
    # ── Rank 11-20 ───────────────────────────────────────────
    "CANBK.NS",      "ITC.NS",        "COALINDIA.NS",   "IRFC.NS",
    "ICICIBANK.NS",  "SBIN.NS",       "HINDZINC.NS",    "VBL.NS",
    "ADANIGREEN.NS", "ONGC.NS",
    # ── Rank 21-30 ───────────────────────────────────────────
    "RELIANCE.NS",   "BEL.NS",        "PNB.NS",         "MOTHERSON.NS",
    "HCLTECH.NS",    "BPCL.NS",       "POWERGRID.NS",   "SUNPHARMA.NS",
    "GAIL.NS",       "SHRIRAMFIN.NS",
    # ── Rank 31-40 ───────────────────────────────────────────
    "IOC.NS",        "PFC.NS",        "ADANIENSOL.NS",  "BANKBARODA.NS",
    "TATAPOWER.NS",  "BHARTIARTL.NS", "NTPC.NS",        "TATACAP.NS",
    "TMPV.NS",       "DRREDDY.NS",
    # ── Rank 41-50 ───────────────────────────────────────────
    "SBILIFE.NS",    "TCS.NS",        "RECLTD.NS",      "HINDALCO.NS",
    "TMCV.NS",       "CIPLA.NS",      "CGPOWER.NS",     "BAJFINANCE.NS",
    "GODREJCP.NS",   "AMBUJACEM.NS",
    # ── Rank 51-60 ───────────────────────────────────────────
    "TECHM.NS",      "AXISBANK.NS",   "NESTLEIND.NS",   "HDFCLIFE.NS",
    "MAXHEALTH.NS",  "M&M.NS",        "ADANIPORTS.NS",  "MAZDOCK.NS",
    "ADANIENT.NS",   "INDHOTEL.NS",
    # ── Rank 61-70 ───────────────────────────────────────────
    "LT.NS",         "DLF.NS",        "JSWSTEEL.NS",    "HINDUNILVR.NS",
    "TRENT.NS",      "LODHA.NS",      "TATACONSUM.NS",  "CHOLAFIN.NS",
    "JINDALSTEL.NS", "GRASIM.NS",
    # ── Rank 71-80 ───────────────────────────────────────────
    "HYUNDAI.NS",    "HDFCAMC.NS",    "UNITDSPR.NS",    "TITAN.NS",
    "LTM.NS",        "BAJAJFINSV.NS", "HAL.NS",         "TVSMOTOR.NS",
    "INDIGO.NS",     "ZYDUSLIFE.NS",
    # ── Rank 81-90 ───────────────────────────────────────────
    "MUTHOOTFIN.NS", "ENRIN.NS",      "PIDILITIND.NS",  "CUMMINSIND.NS",
    "BRITANNIA.NS",  "MARUTI.NS",     "ASIANPAINT.NS",  "EICHERMOT.NS",
    "APOLLOHOSP.NS", "ULTRACEMCO.NS",
    # ── Rank 91-100 ──────────────────────────────────────────
    "ABB.NS",        "DIVISLAB.NS",   "SIEMENS.NS",     "SOLARINDS.NS",
    "TORNTPHARM.NS", "DMART.NS",      "BAJAJ-AUTO.NS",  "BAJAJHLDNG.NS",
    "BOSCHLTD.NS",   "SHREECEM.NS",
    # ── Sector ETFs (BEES) ───────────────────────────────────
    "NIFTYBEES.NS",  "BANKBEES.NS",   "ITBEES.NS",      "AUTOBEES.NS",
    "PHARMABEES.NS", "GOLDBEES.NS",   "SILVERBEES.NS",
]

# US ticker -> sector ETF map, used to auto-generate "same sector" peers for
# the Peer Comparison drawer when a ticker isn't in the hand-curated PEER_MAP
# below. NOTE: as provided, the Utilities group is incomplete (comment says
# 10 tickers, only 7 listed: EXC, XEL, AEP, SRE, D, PEG, WEC) and the dict may
# have been cut off after Utilities - send the remaining tickers/sectors and
# they'll be appended.
SECTOR_MAP = {
    **{s: "XLK" for s in [
        # Technology (16 + SMCI)
        "NVDA", "MSFT", "AAPL", "AVGO", "AMD", "ORCL", "ADBE", "PANW",
        "NOW", "SNPS", "CRM", "CSCO", "INTC", "QCOM", "AMAT", "LRCX",
        "SMCI",
    ]},
    **{s: "XLC" for s in [
        # Communication Services (12)
        "GOOGL", "GOOG", "META", "NFLX", "CMCSA", "DIS",
        "TMUS", "VZ", "T", "CHTR", "SPOT", "RBLX",
    ]},
    **{s: "XLY" for s in [
        # Consumer Discretionary (13)
        "AMZN", "TSLA", "HD", "MCD", "TJX", "BKNG",
        "LOW", "SBUX", "NKE", "MAR", "ROST", "EBAY", "LULU",
    ]},
    **{s: "XLP" for s in [
        # Consumer Staples (10)
        "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "MNST",
    ]},
    **{s: "XLV" for s in [
        # Health Care (16)
        "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "AMGN", "BMY",
        "GILD", "ISRG", "VRTX", "CVS", "CI", "MDT", "SYK", "REGN",
    ]},
    **{s: "XLF" for s in [
        # Financials (16 + HOOD, SOFI)
        "JPM", "BAC", "MS", "GS", "V", "MA", "AXP", "BLK",
        "SPGI", "C", "WFC", "SCHW", "COF", "PGR", "CB", "MMC",
        "HOOD", "SOFI",
    ]},
    **{s: "XLI" for s in [
        # Industrials (15)
        "GE", "CAT", "UNP", "HON", "LMT", "UPS", "RTX", "DE",
        "FDX", "BA", "GEV", "ETN", "ADP", "FAST", "CTAS",
    ]},
    **{s: "XLE" for s in [
        # Energy (12 — includes some utilities/power names as pasted)
        "XOM", "CVX", "COP", "NEE", "SO", "DUK", "CEG", "VST",
        "SLB", "EOG", "KMI", "PSX",
    ]},
    **{s: "XLB" for s in [
        # Materials (8)
        "LIN", "FCX", "SHW", "NEM", "APD", "ECL", "NUE", "DOW",
    ]},
    **{s: "XLRE" for s in [
        # Real Estate (10)
        "PLD", "AMT", "EQIX", "DLR", "WELL", "SPG", "PSA", "O", "CBRE", "VTR",
    ]},
    **{s: "XLU" for s in [
        # Utilities (incomplete - only 7 of the stated 10 were provided)
        "EXC", "XEL", "AEP", "SRE", "D", "PEG", "WEC",
    ]},
}

# Sector shortcut chips -> a representative ticker for that sector
SECTOR_SHORTCUTS = {
    "IT": "TCS.NS",
    "Banking": "HDFCBANK.NS",
    "FMCG": "HINDUNILVR.NS",
    "Auto": "MARUTI.NS",
    "Energy": "RELIANCE.NS",
    "Pharma": "SUNPHARMA.NS",
    "Infra": "LT.NS",
}

# Sector -> Subsector -> [tickers] hierarchy for the India sector navigator
# in the left panel (click a sector to expand its subsectors/stocks). Banking
# is split into subsectors as an example; other sectors use a single "All"
# bucket for now and can be split further the same way. Tickers here were
# cross-checked against NIFTY_500_WATCHLIST / PEER_MAP / NAME_TO_TICKER for
# consistency; AUBANK.NS and UJJIVANSFB.NS were verified via web search since
# they weren't already present elsewhere in this file.
SECTOR_STOCKS = {
    "IT": {
        "All": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTM.NS"],
    },
    "Banking": {
        "Private Banks": ["HDFCBANK.NS", "KOTAKBANK.NS", "ICICIBANK.NS", "AXISBANK.NS"],
        "PSU Banks": ["SBIN.NS", "CANBK.NS", "UNIONBANK.NS", "BANKBARODA.NS", "PNB.NS"],
        "Small Finance Banks": ["AUBANK.NS", "UJJIVANSFB.NS"],
    },
    "FMCG": {
        "All": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "GODREJCP.NS", "VBL.NS"],
    },
    "Auto": {
        "All": ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "TVSMOTOR.NS", "HYUNDAI.NS"],
    },
    "Energy": {
        "All": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS", "GAIL.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS"],
    },
    "Pharma": {
        "All": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "TORNTPHARM.NS", "ZYDUSLIFE.NS", "APOLLOHOSP.NS"],
    },
    "Infra": {
        "All": ["LT.NS", "ADANIPORTS.NS", "ULTRACEMCO.NS", "SIEMENS.NS", "ABB.NS", "GRASIM.NS", "AMBUJACEM.NS"],
    },
}

# Human-readable sector names for the US sector ETF codes used in SECTOR_MAP.
SECTOR_ETF_NAMES = {
    "XLK": "Technology", "XLC": "Communication Services", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLV": "Health Care", "XLF": "Financials",
    "XLI": "Industrials", "XLE": "Energy", "XLB": "Materials",
    "XLRE": "Real Estate", "XLU": "Utilities",
}

# US Sector -> Stocks hierarchy for the sector navigator, auto-derived from
# SECTOR_MAP (ticker -> ETF code) so it stays in sync with that data instead
# of being hand-duplicated. Same "All" bucket shape as SECTOR_STOCKS so both
# accordions can share one template block.
US_SECTOR_STOCKS = {}
for _tk, _etf in SECTOR_MAP.items():
    _sector_name = SECTOR_ETF_NAMES.get(_etf, _etf)
    US_SECTOR_STOCKS.setdefault(_sector_name, {"All": []})["All"].append(_tk)
for _bucket in US_SECTOR_STOCKS.values():
    _bucket["All"].sort()
US_SECTOR_STOCKS = dict(sorted(US_SECTOR_STOCKS.items()))

# Combined name+ticker list for the search box's autosuggest dropdown.
# Built from data already in this file (no new hardcoding needed).
AUTOSUGGEST_LIST = sorted(set(
    list(NAME_TO_TICKER.keys())
    + list(NAME_TO_TICKER_US.keys())
    + [t.replace(".NS", "") for t in NIFTY_500_WATCHLIST]
    + US_QUICK_PICKS
    + list(SECTOR_MAP.keys())
))

# Small hardcoded peer map for the "Compare with Competitors" drawer.
PEER_MAP = {
    "RELIANCE.NS": ["ONGC.NS", "IOC.NS", "BPCL.NS"],
    "TCS.NS": ["INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
    "INFY.NS": ["TCS.NS", "WIPRO.NS", "HCLTECH.NS"],
    "WIPRO.NS": ["TCS.NS", "INFY.NS", "HCLTECH.NS"],
    "HCLTECH.NS": ["TCS.NS", "INFY.NS", "WIPRO.NS"],
    "HDFCBANK.NS": ["ICICIBANK.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
    "ICICIBANK.NS": ["HDFCBANK.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
    "SBIN.NS": ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS"],
    "KOTAKBANK.NS": ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS"],
    "AXISBANK.NS": ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS"],
    "ITC.NS": ["HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS"],
    "HINDUNILVR.NS": ["ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS"],
    "MARUTI.NS": ["TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS"],
    "TATAMOTORS.NS": ["MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS"],
    "BAJFINANCE.NS": ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS"],
    "ASIANPAINT.NS": ["BERGEPAINT.NS", "ITC.NS"],
    "SUNPHARMA.NS": ["DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
    "BHARTIARTL.NS": ["RELIANCE.NS"],
    "LT.NS": ["ADANIPORTS.NS", "ULTRACEMCO.NS"],
    "NTPC.NS": ["POWERGRID.NS"],
    "ADANIENT.NS": ["ADANIPORTS.NS"],
    "ADANIPORTS.NS": ["ADANIENT.NS", "LT.NS"],
    "TATASTEEL.NS": ["ULTRACEMCO.NS"],
    "ULTRACEMCO.NS": ["TATASTEEL.NS", "LT.NS"],
    "POWERGRID.NS": ["NTPC.NS"],
    "TITAN.NS": ["ASIANPAINT.NS", "ITC.NS"],
    # US mega-caps
    "AAPL": ["MSFT", "GOOGL"],
    "MSFT": ["AAPL", "GOOGL", "ORCL"],
    "GOOGL": ["MSFT", "META", "AMZN"],
    "AMZN": ["GOOGL", "WMT"],
    "TSLA": ["NVDA"],
    "NVDA": ["AMD", "INTC"],
    "META": ["GOOGL"],
    "NFLX": ["DIS"],
}

KEY_FIELDS_FOR_QUALITY = [
    "trailing_pe", "forward_pe", "pb", "ev_ebitda", "profit_margin", "operating_margin",
    "roe", "roa", "debt_to_equity", "current_ratio", "beta", "dividend_yield",
    "revenue_growth_yahoo", "earnings_growth_yahoo", "held_insiders", "held_institutions",
    "target_mean_price", "peg_ratio", "price_to_sales", "gross_margin", "quick_ratio",
]


# ------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------
def resolve_ticker(user_input: str, market: str = "IN") -> str:
    raw = user_input.strip()
    key = raw.lower()

    # Explicit exchange suffix (e.g. "RELIANCE.NS", "TATASTEEL.BO") -> use as-is.
    if "." in raw:
        return raw.upper()

    # Known company name in either lookup table -> use regardless of the
    # market radio button, so a mistaken selection doesn't break a known name.
    if key in NAME_TO_TICKER:
        return NAME_TO_TICKER[key] + ".NS"
    if key in NAME_TO_TICKER_US:
        return NAME_TO_TICKER_US[key]

    # Unrecognized plain symbol/name -> fall back based on selected market.
    if market == "US":
        return raw.upper()
    return raw.upper() + ".NS"


def fnum(value, suffix="", digits=2, na="N/A"):
    if value is None:
        return na
    try:
        return f"{value:,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return na


def fpct(value, digits=2, na="N/A", already_fraction=True):
    if value is None:
        return na
    try:
        v = value * 100 if already_fraction else value
        return f"{v:,.{digits}f}%"
    except (TypeError, ValueError):
        return na


def safe_series_growth(series):
    out = []
    try:
        vals = list(series.dropna())
        cols = list(series.index)
        for i in range(len(vals) - 1):
            newer, older = vals[i], vals[i + 1]
            if older not in (0, None) and newer is not None:
                growth = (newer - older) / abs(older) * 100
                label = f"{cols[i + 1].year}->{cols[i].year}" if hasattr(cols[i], "year") else f"{i}"
                out.append((label, growth))
    except Exception:
        pass
    return out


def ordered_values(series):
    """Return [(label, value), ...] oldest-to-newest for sparklines."""
    out = []
    try:
        pairs = [(c, v) for c, v in series.items() if v is not None]
        pairs.sort(key=lambda p: p[0])  # chronological ascending
        for c, v in pairs:
            label = str(c.year) if hasattr(c, "year") else str(c)
            out.append((label, float(v)))
    except Exception:
        pass
    return out


def find_row(df, candidates):
    if df is None or df.empty:
        return None
    lower_index = {str(i).lower(): i for i in df.index}
    for cand in candidates:
        c = cand.lower()
        for lower_name, real_name in lower_index.items():
            if c == lower_name or c in lower_name:
                return df.loc[real_name]
    return None


def latest_value(series):
    """Most recent non-null value in a yfinance financial-statement row, or None.
    Used for the banking ratios (NIM/CIR/CDR) below, which only need the
    latest reported year rather than a full trend series."""
    if series is None:
        return None
    try:
        pairs = [(c, v) for c, v in series.items() if v is not None]
        if not pairs:
            return None
        pairs.sort(key=lambda p: p[0])
        return float(pairs[-1][1])
    except Exception:
        return None


# ------------------------------------------------------------------
# SVG micro-chart helpers (no external chart library needed)
# ------------------------------------------------------------------
def sparkline_svg(pairs, width=140, height=36, color="#38bdf8"):
    vals = [v for _, v in pairs]
    if len(vals) < 2:
        return '<span class="no-data">No trend data</span>'
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = (i / (n - 1)) * (width - 4) + 2
        y = height - 4 - ((v - mn) / rng) * (height - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    last_x, last_y = pts[-1].split(",")
    up = vals[-1] >= vals[0]
    line_color = "#22c55e" if up else "#ef4444"
    points_str = " ".join(pts)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" class="sparkline">'
        f'<polyline points="{points_str}" fill="none" stroke="{line_color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2.5" fill="{line_color}"/>'
        f'</svg>'
    )


def donut_svg(pct, color, size=64, stroke=8, label=None):
    if pct is None:
        return '<span class="no-data">N/A</span>'
    pct = max(0, min(100, pct))
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    filled = c * (pct / 100)
    remaining = c - filled
    center = size / 2
    txt = label if label is not None else f"{pct:.0f}%"
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<circle cx="{center}" cy="{center}" r="{r}" fill="none" stroke="var(--border)" stroke-width="{stroke}"/>'
        f'<circle cx="{center}" cy="{center}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-dasharray="{filled:.1f} {remaining:.1f}" stroke-linecap="round" '
        f'transform="rotate(-90 {center} {center})"/>'
        f'<text x="50%" y="54%" text-anchor="middle" fill="currentColor" font-size="13" font-weight="700">{txt}</text>'
        f'</svg>'
    )


def gauge_svg(value, max_value, zones, width=170, height=16):
    """zones: list of (start, end, color) covering 0..max_value"""
    if value is None:
        return '<span class="no-data">N/A</span>'
    value_clamped = max(0, min(max_value, value))
    marker_x = (value_clamped / max_value) * width
    segs = []
    for start, end, color in zones:
        x1 = (start / max_value) * width
        x2 = (end / max_value) * width
        segs.append(f'<rect x="{x1:.1f}" y="0" width="{(x2 - x1):.1f}" height="{height}" fill="{color}" opacity="0.85"/>')
    segs_str = "".join(segs)
    return (
        f'<svg viewBox="0 0 {width} {height + 10}" width="{width}" height="{height + 10}">'
        f'<g>{segs_str}</g>'
        f'<polygon points="{marker_x:.1f},{height} {marker_x - 5:.1f},{height + 9} {marker_x + 5:.1f},{height + 9}" fill="var(--text)"/>'
        f'</svg>'
    )


def range_slider_svg(low, current, high, width=180, height=22, color="#38bdf8"):
    if low is None or high is None or current is None or high == low:
        return '<span class="no-data">N/A</span>'
    pct = max(0, min(1, (current - low) / (high - low)))
    x = pct * (width - 12) + 6
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<line x1="6" y1="{height/2}" x2="{width-6}" y2="{height/2}" stroke="var(--border)" stroke-width="4" stroke-linecap="round"/>'
        f'<circle cx="{x:.1f}" cy="{height/2}" r="6" fill="{color}" stroke="var(--panel)" stroke-width="2"/>'
        f'</svg>'
    )


# ------------------------------------------------------------------
# Technical indicators (from daily OHLCV price history, not fundamentals)
# ------------------------------------------------------------------
def compute_technical_indicators(history):
    """Compute SMA/EMA, RSI(14), MACD(12,26,9), Bollinger Bands(20,2) and a
    volume signal from a yfinance daily history frame. Best-effort: any
    indicator that needs more history than is available comes back as None
    instead of raising (e.g. a recently-listed stock won't have 200 days yet)."""
    result = {
        "sma20": None, "sma50": None, "sma200": None, "ema12": None, "ema26": None,
        "rsi14": None, "rsi_signal": None,
        "macd": None, "macd_signal_line": None, "macd_hist": None, "macd_signal_flag": None,
        "bb_upper": None, "bb_mid": None, "bb_lower": None,
        "latest_close": None, "latest_volume": None, "avg_volume20": None, "volume_signal": None,
        "price_vs_sma50": None, "price_vs_sma200": None, "close_series": [],
    }
    try:
        if history is None or history.empty or "Close" not in history.columns:
            return result
        close = history["Close"].dropna()
        if close.empty:
            return result
        result["latest_close"] = float(close.iloc[-1])

        if len(close) >= 20:
            result["sma20"] = float(close.rolling(20).mean().iloc[-1])
        if len(close) >= 50:
            result["sma50"] = float(close.rolling(50).mean().iloc[-1])
        if len(close) >= 200:
            result["sma200"] = float(close.rolling(200).mean().iloc[-1])

        ema12_series = close.ewm(span=12, adjust=False).mean()
        ema26_series = close.ewm(span=26, adjust=False).mean()
        if len(close) >= 12:
            result["ema12"] = float(ema12_series.iloc[-1])
        if len(close) >= 26:
            result["ema26"] = float(ema26_series.iloc[-1])

        # RSI - Wilder's smoothing, 14-period
        if len(close) >= 15:
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, float("nan"))
            rsi = 100 - (100 / (1 + rs))
            rsi_latest = rsi.iloc[-1]
            if rsi_latest == rsi_latest:  # NaN check
                result["rsi14"] = float(rsi_latest)
                if result["rsi14"] >= 70:
                    result["rsi_signal"] = "Overbought"
                elif result["rsi14"] <= 30:
                    result["rsi_signal"] = "Oversold"
                else:
                    result["rsi_signal"] = "Neutral"

        # MACD (12, 26, 9)
        if len(close) >= 26:
            macd_line = ema12_series - ema26_series
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            hist = macd_line - signal_line
            result["macd"] = float(macd_line.iloc[-1])
            result["macd_signal_line"] = float(signal_line.iloc[-1])
            result["macd_hist"] = float(hist.iloc[-1])
            result["macd_signal_flag"] = (
                "Bullish (MACD above signal)" if result["macd"] > result["macd_signal_line"]
                else "Bearish (MACD below signal)"
            )

        # Bollinger Bands (20, 2 std)
        if len(close) >= 20:
            mid = close.rolling(20).mean()
            std = close.rolling(20).std()
            result["bb_mid"] = float(mid.iloc[-1])
            result["bb_upper"] = float((mid + 2 * std).iloc[-1])
            result["bb_lower"] = float((mid - 2 * std).iloc[-1])

        if "Volume" in history.columns:
            vol = history["Volume"].dropna()
            if not vol.empty:
                result["latest_volume"] = float(vol.iloc[-1])
                if len(vol) >= 20:
                    avg_vol = float(vol.rolling(20).mean().iloc[-1])
                    result["avg_volume20"] = avg_vol
                    if avg_vol:
                        ratio = result["latest_volume"] / avg_vol
                        if ratio > 1.5:
                            result["volume_signal"] = "High (>150% of 20d avg)"
                        elif ratio < 0.5:
                            result["volume_signal"] = "Low (<50% of 20d avg)"
                        else:
                            result["volume_signal"] = "Normal"

        if result["latest_close"] is not None and result["sma50"] is not None:
            result["price_vs_sma50"] = "Above" if result["latest_close"] > result["sma50"] else "Below"
        if result["latest_close"] is not None and result["sma200"] is not None:
            result["price_vs_sma200"] = "Above" if result["latest_close"] > result["sma200"] else "Below"

        tail = close.tail(60)
        result["close_series"] = [
            (str(idx.date()) if hasattr(idx, "date") else str(idx), float(v)) for idx, v in tail.items()
        ]
    except Exception:
        pass
    return result


# ------------------------------------------------------------------
# Lightweight in-memory cache for yfinance lookups
# ------------------------------------------------------------------
# yfinance/Yahoo can be slow and will rate-limit repeated requests. Since this
# is a single-process local tool (no DB, no background jobs), a simple
# dict + timestamp cache is enough to avoid re-fetching the same ticker on
# every click within a short window, while still keeping data "fresh enough"
# for a research tool (not a live trading feed).
_TICKER_CACHE = {}
CACHE_TTL_SECONDS = 120


def get_ticker_bundle(ticker_symbol, force_refresh=False):
    """Fetch (or reuse cached) info/financials/balance_sheet/cashflow for a
    ticker in one shot. Returns (bundle_dict, meta_dict).

    meta_dict has:
      - latency_ms: how long the live Yahoo fetch took (0 if served from cache)
      - cache_hit: True if this response came from the in-memory cache
      - cache_age_s: how old the cached data is (0 if this was a live fetch)
    """
    now = time.time()
    cached = _TICKER_CACHE.get(ticker_symbol)
    if cached and not force_refresh and (now - cached["fetched_at"]) < CACHE_TTL_SECONDS:
        age = now - cached["fetched_at"]
        return cached["bundle"], {"latency_ms": 0.0, "cache_hit": True, "cache_age_s": age}

    start = time.time()
    t = yf.Ticker(ticker_symbol)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    try:
        financials = t.financials
    except Exception:
        financials = None
    try:
        balance_sheet = t.balance_sheet
    except Exception:
        balance_sheet = None
    try:
        cashflow = t.cashflow
    except Exception:
        cashflow = None
    try:
        # ~9 months of daily bars is enough for SMA200/RSI14/MACD(12,26,9);
        # wrapped in try/except like everything else here since illiquid or
        # delisted tickers can return an empty/partial frame.
        history = t.history(period="9mo", interval="1d")
    except Exception:
        history = None
    latency_ms = (time.time() - start) * 1000

    bundle = {
        "info": info, "financials": financials,
        "balance_sheet": balance_sheet, "cashflow": cashflow,
        "history": history,
    }
    _TICKER_CACHE[ticker_symbol] = {"bundle": bundle, "fetched_at": time.time()}
    return bundle, {"latency_ms": latency_ms, "cache_hit": False, "cache_age_s": 0.0}


# ------------------------------------------------------------------
# Core: fetch + compute everything from real data
# ------------------------------------------------------------------
def fetch_minimal(ticker_symbol):
    """Lightweight fetch used for peer comparison rows."""
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info or {}
        return {
            "ticker": ticker_symbol,
            "name": info.get("shortName") or ticker_symbol,
            "trailing_pe": info.get("trailingPE"),
            "profit_margin": info.get("profitMargins"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "held_insiders": info.get("heldPercentInsiders"),
            "target_mean_price": info.get("targetMeanPrice"),
        }
    except Exception:
        return {"ticker": ticker_symbol, "name": ticker_symbol, "trailing_pe": None,
                "profit_margin": None, "roe": None, "revenue_growth": None,
                "held_insiders": None, "target_mean_price": None}


def build_report(ticker_symbol: str, force_refresh: bool = False):
    bundle, fetch_meta = get_ticker_bundle(ticker_symbol, force_refresh=force_refresh)
    info = bundle["info"]
    financials = bundle["financials"]
    balance_sheet = bundle["balance_sheet"]
    cashflow = bundle["cashflow"]
    history = bundle.get("history")

    tech = compute_technical_indicators(history)
    svg_price_spark = sparkline_svg(tech["close_series"])

    name = info.get("longName") or info.get("shortName") or ticker_symbol
    sector = info.get("sector", "N/A")
    industry = info.get("industry", "N/A")
    summary = info.get("longBusinessSummary", "Business description not available for this ticker.")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    change = None
    change_pct = None
    if price is not None and prev_close:
        change = price - prev_close
        change_pct = (change / prev_close) * 100
    currency = info.get("currency", "INR")

    revenue_row = find_row(financials, ["Total Revenue", "Revenue"])
    net_income_row = find_row(financials, ["Net Income", "Net Income Common Stockholders"])

    revenue_growth_series = safe_series_growth(revenue_row) if revenue_row is not None else []
    pat_growth_series = safe_series_growth(net_income_row) if net_income_row is not None else []
    revenue_values = ordered_values(revenue_row) if revenue_row is not None else []
    pat_values = ordered_values(net_income_row) if net_income_row is not None else []

    op_cf_row = find_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex_row = find_row(cashflow, ["Capital Expenditure"])
    fcf_series = []
    try:
        if op_cf_row is not None and capex_row is not None:
            for date in op_cf_row.index:
                if date in capex_row.index:
                    ocf = op_cf_row[date]
                    capex = capex_row[date]
                    if ocf is not None and capex is not None:
                        label = str(date.year) if hasattr(date, "year") else str(date)
                        fcf_series.append((date, ocf + capex, label))
    except Exception:
        pass
    fcf_series.sort(key=lambda x: x[0])
    fcf_values = [(label, val) for _, val, label in fcf_series]
    fcf_display = [(label, val) for _, val, label in sorted(fcf_series, key=lambda x: x[0], reverse=True)]

    debt_row = find_row(balance_sheet, ["Total Debt", "Long Term Debt"])
    debt_values = ordered_values(debt_row) if debt_row is not None else []
    debt_display = list(reversed(debt_values))

    # ---------------- Banking-specific metrics (best-effort) ----------------
    # Standard metrics like FCF/D-E/EV-EBITDA are misleading for banks (deposits
    # are liabilities, loans are assets - a balance-sheet business model, not an
    # operating one). NIM, Cost-to-Income and Credit-to-Deposit CAN be derived
    # from Yahoo's standard financial statements, so we compute them here.
    # NPA%, Provision Coverage Ratio, CASA Ratio and CAR/CET1 are deliberately
    # NOT included - they are regulatory/investor-presentation disclosures that
    # Yahoo Finance does not carry at all, so adding them would just be more
    # permanent N/A fields (same reasoning as the incomplete SECTOR_MAP note
    # above - be upfront about data that genuinely isn't available here).
    industry_lower = (industry or "").lower()
    sector_lower = (sector or "").lower()
    is_bank = "bank" in industry_lower or "bank" in sector_lower

    nii_row = find_row(financials, ["Net Interest Income"])
    nii_latest = latest_value(nii_row)
    total_assets_row = find_row(balance_sheet, ["Total Assets"])
    total_assets_values = ordered_values(total_assets_row) if total_assets_row is not None else []
    if len(total_assets_values) >= 2:
        avg_total_assets = (total_assets_values[-1][1] + total_assets_values[-2][1]) / 2
    elif len(total_assets_values) == 1:
        avg_total_assets = total_assets_values[-1][1]
    else:
        avg_total_assets = None
    nim = (nii_latest / avg_total_assets) if (nii_latest is not None and avg_total_assets) else None

    opex_row = find_row(financials, ["Operating Expense", "Total Operating Expenses", "Non Interest Expense"])
    opex_latest = latest_value(opex_row)
    total_revenue_latest = latest_value(revenue_row)
    cir = (opex_latest / total_revenue_latest) if (opex_latest is not None and total_revenue_latest) else None

    loans_row = find_row(balance_sheet, ["Net Loan", "Gross Loan", "Total Loans"])
    loans_latest = latest_value(loans_row)
    deposits_row = find_row(balance_sheet, ["Total Deposits", "Deposits"])
    deposits_latest = latest_value(deposits_row)
    cdr = (loans_latest / deposits_latest) if (loans_latest is not None and deposits_latest) else None

    # ---------------- Ratios / valuation ----------------
    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    pb = info.get("priceToBook")
    ev_ebitda = info.get("enterpriseToEbitda")
    profit_margin = info.get("profitMargins")
    operating_margin = info.get("operatingMargins")
    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    debt_to_equity = info.get("debtToEquity")
    current_ratio = info.get("currentRatio")
    beta = info.get("beta")
    dividend_yield = info.get("dividendYield")
    revenue_growth_yahoo = info.get("revenueGrowth")
    earnings_growth_yahoo = info.get("earningsGrowth")
    fifty2_high = info.get("fiftyTwoWeekHigh")
    fifty2_low = info.get("fiftyTwoWeekLow")
    market_cap = info.get("marketCap")

    held_insiders = info.get("heldPercentInsiders")
    held_institutions = info.get("heldPercentInstitutions")

    # ---------------- Additional core metrics (direct yfinance fields) ----------------
    peg_ratio = info.get("pegRatio")
    price_to_sales = info.get("priceToSalesTrailing12Months")
    gross_margin = info.get("grossMargins")
    quick_ratio = info.get("quickRatio")

    # ---------------- Additional core metrics (computed from statements) ----------------
    # Operating Cash Flow vs Net Income: a classic earnings-quality check - if
    # OCF is meaningfully below reported Net Income over multiple years, profits
    # may be driven by non-cash accounting items rather than real cash generation.
    ocf_latest = latest_value(op_cf_row)
    net_income_latest = latest_value(net_income_row)
    ocf_vs_ni_ratio = (ocf_latest / net_income_latest) if (ocf_latest is not None and net_income_latest not in (None, 0)) else None
    earnings_quality_flag = None
    if ocf_vs_ni_ratio is not None:
        earnings_quality_flag = "Weak (OCF well below Net Income)" if ocf_vs_ni_ratio < 0.8 else "Healthy (OCF covers Net Income)"

    # Interest Coverage Ratio = Operating Income / Interest Expense. Row names
    # vary a lot between companies/regions, so this will legitimately be N/A
    # for a good share of tickers - same caveat as NIM/CIR above.
    operating_income_row = find_row(financials, ["Operating Income", "Total Operating Income As Reported"])
    interest_expense_row = find_row(financials, ["Interest Expense"])
    operating_income_latest = latest_value(operating_income_row)
    interest_expense_latest = latest_value(interest_expense_row)
    interest_coverage = None
    if operating_income_latest is not None and interest_expense_latest not in (None, 0):
        interest_coverage = operating_income_latest / abs(interest_expense_latest)

    # Inventory Turnover = COGS / average Inventory. Mainly meaningful for
    # retail/consumer/manufacturing tickers; will be N/A for banks, services,
    # software, etc. (which is expected/correct, not a data gap).
    cogs_row = find_row(financials, ["Cost Of Revenue", "Reconciled Cost Of Revenue"])
    inventory_row = find_row(balance_sheet, ["Inventory"])
    cogs_latest = latest_value(cogs_row)
    inventory_values = ordered_values(inventory_row) if inventory_row is not None else []
    if len(inventory_values) >= 2:
        avg_inventory = (inventory_values[-1][1] + inventory_values[-2][1]) / 2
    elif len(inventory_values) == 1:
        avg_inventory = inventory_values[-1][1]
    else:
        avg_inventory = None
    inventory_turnover = (cogs_latest / avg_inventory) if (cogs_latest is not None and avg_inventory) else None

    # R&D as % of Revenue - mainly meaningful for pharma/biotech/tech.
    rd_row = find_row(financials, ["Research And Development"])
    rd_latest = latest_value(rd_row)
    rd_pct_revenue = (rd_latest / total_revenue_latest) if (rd_latest is not None and total_revenue_latest) else None

    recommendation_key = info.get("recommendationKey", "N/A")
    recommendation_mean = info.get("recommendationMean")
    num_analysts = info.get("numberOfAnalystOpinions")
    target_mean_price = info.get("targetMeanPrice")

    upside_pct = None
    if target_mean_price is not None and price:
        upside_pct = (target_mean_price - price) / price * 100

    # ---------------- Rule-based scoring ----------------
    moat_score = 5
    if operating_margin is not None:
        if operating_margin > 0.25:
            moat_score += 2
        elif operating_margin > 0.15:
            moat_score += 1
        elif operating_margin < 0.05:
            moat_score -= 1
    if roe is not None:
        if roe > 0.20:
            moat_score += 2
        elif roe > 0.12:
            moat_score += 1
        elif roe < 0.05:
            moat_score -= 1
    if market_cap is not None and market_cap > 2_00_000_00_00_000:
        moat_score += 1
    moat_score = max(1, min(10, moat_score))

    risk_flags = []
    if debt_to_equity is not None and debt_to_equity > 100:
        risk_flags.append(("Debt levels", "High", f"Debt-to-equity is {fnum(debt_to_equity, digits=1)}, above the 100 threshold used here."))
    elif debt_to_equity is not None:
        risk_flags.append(("Debt levels", "Moderate/Low", f"Debt-to-equity is {fnum(debt_to_equity, digits=1)}."))
    else:
        risk_flags.append(("Debt levels", "Unknown", "Debt-to-equity data not available."))

    if beta is not None and beta > 1.3:
        risk_flags.append(("Volatility (beta)", "High", f"Beta of {fnum(beta, digits=2)} indicates higher volatility than the market."))
    elif beta is not None:
        risk_flags.append(("Volatility (beta)", "Moderate/Low", f"Beta of {fnum(beta, digits=2)}."))
    else:
        risk_flags.append(("Volatility (beta)", "Unknown", "Beta data not available."))

    if profit_margin is not None and profit_margin < 0.05:
        risk_flags.append(("Profitability", "High", f"Net profit margin is only {fpct(profit_margin)}."))
    elif profit_margin is not None:
        risk_flags.append(("Profitability", "Moderate/Low", f"Net profit margin is {fpct(profit_margin)}."))
    else:
        risk_flags.append(("Profitability", "Unknown", "Margin data not available."))

    if current_ratio is not None and current_ratio < 1:
        risk_flags.append(("Liquidity", "High", f"Current ratio is {fnum(current_ratio, digits=2)}, below 1.0."))
    elif current_ratio is not None:
        risk_flags.append(("Liquidity", "Moderate/Low", f"Current ratio is {fnum(current_ratio, digits=2)}."))
    else:
        risk_flags.append(("Liquidity", "Unknown", "Current ratio data not available."))

    if trailing_pe is not None and trailing_pe > 50:
        risk_flags.append(("Valuation", "High", f"Trailing P/E of {fnum(trailing_pe, digits=1)} is well above a 50x threshold."))
    elif trailing_pe is not None:
        risk_flags.append(("Valuation", "Moderate/Low", f"Trailing P/E of {fnum(trailing_pe, digits=1)}."))
    else:
        risk_flags.append(("Valuation", "Unknown", "P/E data not available."))

    severity_order = {"High": 0, "Moderate/Low": 1, "Unknown": 2}
    risk_flags_sorted = sorted(risk_flags, key=lambda r: severity_order.get(r[1], 2))
    high_risk_count = sum(1 for _, lvl, _ in risk_flags if lvl == "High")
    unknown_count = sum(1 for _, lvl, _ in risk_flags if lvl == "Unknown")
    if unknown_count == len(risk_flags):
        risk_badge = "NA"
    elif high_risk_count >= 2:
        risk_badge = "HIGH"
    elif high_risk_count == 1:
        risk_badge = "MODERATE"
    else:
        risk_badge = "LOW"

    growth_bucket = "Data not available"
    growth_badge = "NA"
    if revenue_growth_yahoo is not None:
        if revenue_growth_yahoo > 0.15:
            growth_bucket = "High (revenue growth above 15% YoY)"
            growth_badge = "HIGH"
        elif revenue_growth_yahoo > 0.05:
            growth_bucket = "Moderate (revenue growth 5-15% YoY)"
            growth_badge = "MODERATE"
        else:
            growth_bucket = "Low / declining (revenue growth below 5% YoY)"
            growth_badge = "LOW"

    valuation_badge = "NA"
    if trailing_pe is not None:
        valuation_badge = "EXPENSIVE" if trailing_pe > 35 else "FAIR"

    bull_points, bear_points = [], []
    if roe is not None:
        (bull_points if roe > 0.15 else bear_points).append(f"Return on Equity is {fpct(roe)}.")
    if operating_margin is not None:
        (bull_points if operating_margin > 0.15 else bear_points).append(f"Operating margin is {fpct(operating_margin)}.")
    if debt_to_equity is not None:
        (bull_points if debt_to_equity < 60 else bear_points).append(f"Debt-to-equity is {fnum(debt_to_equity, digits=1)}.")
    if revenue_growth_yahoo is not None:
        (bull_points if revenue_growth_yahoo > 0.08 else bear_points).append(f"Revenue growth (YoY) is {fpct(revenue_growth_yahoo)}.")
    if trailing_pe is not None:
        (bear_points if trailing_pe > 40 else bull_points).append(f"Trailing P/E is {fnum(trailing_pe, digits=1)}.")
    if price is not None and fifty2_high is not None:
        pct_off_high = (price - fifty2_high) / fifty2_high * 100
        (bear_points if pct_off_high < -20 else bull_points).append(
            f"Price is {fnum(pct_off_high, suffix='%', digits=1)} versus its 52-week high of {fnum(fifty2_high, digits=1)}."
        )
    if not bull_points:
        bull_points.append("Insufficient data available to identify strong positive signals.")
    if not bear_points:
        bear_points.append("Insufficient data available to identify strong negative signals.")

    score, scoreable = 0, 0
    if roe is not None:
        scoreable += 1; score += 1 if roe > 0.15 else 0
    if operating_margin is not None:
        scoreable += 1; score += 1 if operating_margin > 0.15 else 0
    if debt_to_equity is not None:
        scoreable += 1; score += 1 if debt_to_equity < 80 else 0
    if revenue_growth_yahoo is not None:
        scoreable += 1; score += 1 if revenue_growth_yahoo > 0.08 else 0
    if trailing_pe is not None:
        scoreable += 1; score += 1 if trailing_pe < 40 else 0

    if scoreable == 0:
        verdict, verdict_badge = "Insufficient data", "NA"
    else:
        ratio = score / scoreable
        if ratio >= 0.7:
            verdict, verdict_badge = "Buy (per rule-based score)", "BUY"
        elif ratio >= 0.4:
            verdict, verdict_badge = "Hold (per rule-based score)", "HOLD"
        else:
            verdict, verdict_badge = "Avoid / Caution (per rule-based score)", "SELL"

    # ---------------- Data quality ----------------
    field_values = {
        "trailing_pe": trailing_pe, "forward_pe": forward_pe, "pb": pb, "ev_ebitda": ev_ebitda,
        "profit_margin": profit_margin, "operating_margin": operating_margin, "roe": roe, "roa": roa,
        "debt_to_equity": debt_to_equity, "current_ratio": current_ratio, "beta": beta,
        "dividend_yield": dividend_yield, "revenue_growth_yahoo": revenue_growth_yahoo,
        "earnings_growth_yahoo": earnings_growth_yahoo, "held_insiders": held_insiders,
        "held_institutions": held_institutions, "target_mean_price": target_mean_price,
        "peg_ratio": peg_ratio, "price_to_sales": price_to_sales, "gross_margin": gross_margin,
        "quick_ratio": quick_ratio,
    }
    present = sum(1 for k in KEY_FIELDS_FOR_QUALITY if field_values.get(k) is not None)
    dq_pct = present / len(KEY_FIELDS_FOR_QUALITY) * 100
    if dq_pct >= 80:
        dq_label = "High"
    elif dq_pct >= 50:
        dq_label = "Medium"
    else:
        dq_label = "Low"

    return {
        "name": name, "ticker": ticker_symbol, "sector": sector, "industry": industry, "summary": summary,
        "price": price, "prev_close": prev_close, "change": change, "change_pct": change_pct, "currency": currency,
        "market_cap": market_cap, "trailing_pe": trailing_pe, "forward_pe": forward_pe, "pb": pb, "ev_ebitda": ev_ebitda,
        "profit_margin": profit_margin, "operating_margin": operating_margin, "roe": roe, "roa": roa,
        "debt_to_equity": debt_to_equity, "current_ratio": current_ratio, "beta": beta, "dividend_yield": dividend_yield,
        "revenue_growth_yahoo": revenue_growth_yahoo, "earnings_growth_yahoo": earnings_growth_yahoo,
        "is_bank": is_bank, "nim": nim, "cir": cir, "cdr": cdr,
        "tech": tech, "svg_price_spark": svg_price_spark,
        "peg_ratio": peg_ratio, "price_to_sales": price_to_sales, "gross_margin": gross_margin,
        "quick_ratio": quick_ratio, "ocf_latest": ocf_latest, "net_income_latest": net_income_latest,
        "ocf_vs_ni_ratio": ocf_vs_ni_ratio, "earnings_quality_flag": earnings_quality_flag,
        "interest_coverage": interest_coverage, "inventory_turnover": inventory_turnover,
        "rd_pct_revenue": rd_pct_revenue,
        "fifty2_high": fifty2_high, "fifty2_low": fifty2_low, "held_insiders": held_insiders,
        "held_institutions": held_institutions, "recommendation_key": recommendation_key,
        "recommendation_mean": recommendation_mean, "num_analysts": num_analysts,
        "target_mean_price": target_mean_price, "upside_pct": upside_pct,
        "revenue_growth_series": revenue_growth_series, "pat_growth_series": pat_growth_series,
        "revenue_values": revenue_values, "pat_values": pat_values,
        "fcf_values": fcf_values, "fcf_display": fcf_display,
        "debt_values": debt_values, "debt_display": debt_display,
        "moat_score": moat_score, "risk_flags_sorted": risk_flags_sorted, "risk_badge": risk_badge,
        "growth_bucket": growth_bucket, "growth_badge": growth_badge, "valuation_badge": valuation_badge,
        "bull_points": bull_points, "bear_points": bear_points, "verdict": verdict, "verdict_badge": verdict_badge,
        "dq_pct": dq_pct, "dq_label": dq_label,
        # pre-rendered SVGs (computed once here so the template stays simple)
        "svg_range_slider": range_slider_svg(fifty2_low, price, fifty2_high),
        "svg_revenue_spark": sparkline_svg(revenue_values),
        "svg_pat_spark": sparkline_svg(pat_values),
        "svg_fcf_spark": sparkline_svg(fcf_values),
        "svg_debt_trend_spark": sparkline_svg(debt_values),
        "svg_debt_gauge": gauge_svg(debt_to_equity, 200, [(0, 60, "#22c55e"), (60, 120, "#eab308"), (120, 200, "#ef4444")]),
        "svg_nim_gauge": gauge_svg(nim * 100 if nim is not None else None, 8,
                                     [(0, 2.5, "#ef4444"), (2.5, 3.5, "#eab308"), (3.5, 8, "#22c55e")]),
        "svg_cir_gauge": gauge_svg(cir * 100 if cir is not None else None, 100,
                                     [(0, 45, "#22c55e"), (45, 60, "#eab308"), (60, 100, "#ef4444")]),
        "svg_cdr_gauge": gauge_svg(cdr * 100 if cdr is not None else None, 120,
                                     [(0, 75, "#22c55e"), (75, 90, "#eab308"), (90, 120, "#ef4444")]),
        "svg_margin_gauge": gauge_svg((profit_margin or 0) * 100 if profit_margin is not None else None, 40,
                                       [(0, 10, "#ef4444"), (10, 20, "#eab308"), (20, 40, "#22c55e")]),
        "svg_insider_donut": donut_svg(held_insiders * 100 if held_insiders is not None else None, "#38bdf8"),
        "svg_institution_donut": donut_svg(held_institutions * 100 if held_institutions is not None else None, "#a78bfa"),
        # developer/debug info
        "debug_latency_ms": fetch_meta["latency_ms"],
        "debug_cache_hit": fetch_meta["cache_hit"],
        "debug_cache_age_s": fetch_meta["cache_age_s"],
    }


def build_peers(ticker_symbol, base_report):
    peers = PEER_MAP.get(ticker_symbol)
    if not peers:
        # Fall back to auto-derived same-sector peers for US tickers using
        # SECTOR_MAP (covers ~150 names vs. the ~8 hardcoded US entries in
        # PEER_MAP above).
        sector = SECTOR_MAP.get(ticker_symbol)
        if sector:
            peers = [s for s, sec in SECTOR_MAP.items() if sec == sector and s != ticker_symbol]
    peers = peers or []
    rows = [{
        "ticker": ticker_symbol, "name": base_report["name"] + " (this stock)",
        "trailing_pe": base_report["trailing_pe"], "profit_margin": base_report["profit_margin"],
        "roe": base_report["roe"], "revenue_growth": base_report["revenue_growth_yahoo"],
        "held_insiders": base_report["held_insiders"], "target_mean_price": base_report["target_mean_price"],
    }]
    for p in peers[:3]:
        rows.append(fetch_minimal(p))
    return rows


# ------------------------------------------------------------------
# HTML template
# ------------------------------------------------------------------
PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stockizen Research Terminal (Data-only, no AI)</title>
<style>
  :root[data-theme="dark"] { --bg:#0f172a; --panel:#1e293b; --panel2:#172033; --text:#e2e8f0; --muted:#94a3b8; --border:#334155; --accent:#38bdf8; }
  :root[data-theme="light"] { --bg:#f1f5f9; --panel:#ffffff; --panel2:#f8fafc; --text:#0f172a; --muted:#475569; --border:#e2e8f0; --accent:#0284c7; }
  :root[data-theme="amoled"] { --bg:#000000; --panel:#0a0a0a; --panel2:#050505; --text:#e5e5e5; --muted:#888888; --border:#1f1f1f; --accent:#22d3ee; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); margin: 0; transition: background .2s, color .2s; }
  a { color: var(--accent); }
  .topbar { display:flex; align-items:center; justify-content:space-between; padding: 12px 20px; background: var(--panel); border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 10px; }
  .topbar h1 { font-size: 18px; margin: 0; color: var(--accent); }
  .controls { display:flex; gap:8px; align-items:center; flex-wrap: wrap; }
  .controls button, .controls select { background: var(--panel2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
  .controls button.active { background: var(--accent); color: var(--bg); font-weight: bold; }
  .swatch { width:18px; height:18px; border-radius:50%; border:2px solid var(--border); cursor:pointer; display:inline-block; }

  form.search { background: var(--panel); padding: 16px 20px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  input[type=text] { flex: 1 1 260px; padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--panel2); color: var(--text); font-size: 15px; }
  form.search button { padding: 10px 20px; border-radius: 6px; border: none; background: var(--accent); color: var(--bg); font-weight: bold; cursor: pointer; font-size: 15px; }
  label.check { font-size: 12px; color: var(--muted); display:flex; align-items:center; gap:6px; }

  .error { color: #f87171; padding: 0 20px; }

  /* summary bar */
  .summary { display:flex; gap: 18px; padding: 16px 20px; background: var(--panel2); border-bottom: 1px solid var(--border); flex-wrap: wrap; align-items: center; }
  .summary .price-block .price { font-size: 30px; font-weight: 800; }
  .summary .price-block .change { font-size: 14px; font-weight: 700; }
  .up { color:#22c55e; } .down { color:#ef4444; }
  .chip { background: var(--panel); border: 1px solid var(--border); border-radius: 20px; padding: 6px 14px; font-size: 12px; }
  .badge { display:inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight:bold; }
  .badge-buy, .badge-high-good { background:#166534; color:#dcfce7; }
  .badge-hold, .badge-moderate { background:#854d0e; color:#fef9c3; }
  .badge-sell, .badge-high-bad, .badge-expensive { background:#7f1d1d; color:#fee2e2; }
  .badge-low { background:#166534; color:#dcfce7; }
  .badge-na { background: var(--border); color: var(--muted); }
  .summary-block { display:flex; flex-direction:column; gap:4px; }
  .summary-block .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }

  /* three panel layout */
  .layout { display:flex; align-items:flex-start; }
  .left-panel { width: 220px; flex-shrink:0; padding: 16px; border-right: 1px solid var(--border); position: sticky; top:0; }
  .left-panel h3 { font-size: 12px; text-transform: uppercase; color: var(--muted); margin: 18px 0 8px; }
  .left-panel h3:first-child { margin-top: 0; }
  .pick-btn { display:block; width:100%; text-align:left; background: var(--panel); border:1px solid var(--border); color: var(--text); padding: 8px 10px; border-radius:6px; font-size: 13px; margin-bottom:6px; cursor:pointer; text-decoration:none; }
  .pick-btn:hover { border-color: var(--accent); }
  .chip-row { display:flex; flex-wrap:wrap; gap:6px; }
  .chip-btn { background: var(--panel); border:1px solid var(--border); color: var(--text); padding: 5px 10px; border-radius: 14px; font-size: 12px; cursor:pointer; text-decoration:none; }
  .chip-btn:hover { border-color: var(--accent); }
  .sector-body { display:none; margin-bottom:8px; }
  .sector-body.open { display:block; }
  .sector-toggle { display:flex; justify-content:space-between; align-items:center; }
  .sector-caret { transition: transform .15s; }
  .sector-toggle.open .sector-caret { transform: rotate(180deg); }
  .sector-sub-label { font-size:11px; color: var(--muted); text-transform: uppercase; letter-spacing:.03em; margin: 6px 0 4px 6px; }

  .center-panel { flex: 1 1 auto; padding: 20px; min-width: 0; }
  .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  .card { background: var(--panel); padding: 18px; border-radius: 10px; border: 1px solid var(--border); }
  .card-head { display:flex; align-items:center; justify-content:space-between; margin-bottom: 10px; }
  .card-head .title { display:flex; align-items:center; gap:8px; font-weight:700; }
  .card-head .icon { font-size: 18px; }
  .expand-btn { background:none; border:1px solid var(--border); color: var(--muted); border-radius: 6px; font-size:11px; padding:3px 8px; cursor:pointer; }
  .metric-row { display:flex; justify-content:space-between; align-items:center; padding: 6px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
  .metric-row:last-child { border-bottom:none; }
  .metric-row .val { font-weight:700; }
  .details { display:none; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
  .card.expanded .details { display:block; }
  table.mini { width:100%; border-collapse: collapse; font-size: 12px; }
  table.mini td { padding: 4px 4px; border-bottom: 1px solid var(--border); }
  .no-data { color: var(--muted); font-size: 12px; }
  .dq-wrap { display:flex; align-items:center; gap:8px; font-size:12px; color: var(--muted); margin-top: 14px; }
  .dq-dot { width:8px; height:8px; border-radius:50%; }
  .dq-high { background:#22c55e; } .dq-medium { background:#eab308; } .dq-low { background:#ef4444; }

  body.investor-mode .trader-only { display:none !important; }
  body.trader-mode .investor-only { display:none !important; }

  /* All generated gauge/donut/sparkline/range-slider SVGs use viewBox already -
     letting them scale via CSS (instead of staying pinned to their fixed
     width/height attributes) is what actually makes them responsive on
     narrow screens, since the Python helpers set a fixed pixel size meant
     for desktop card widths. */
  svg { max-width: 100%; height: auto; }

  /* right drawer */
  .right-toggle { position: fixed; right: 0; top: 100px; background: var(--accent); color: var(--bg); border:none; padding: 10px 6px; border-radius: 8px 0 0 8px; cursor:pointer; font-weight:bold; writing-mode: vertical-rl; z-index: 50; }
  .drawer { position: fixed; top:0; right:-380px; width: 360px; height: 100vh; background: var(--panel); border-left: 1px solid var(--border); padding: 20px; overflow-y:auto; transition: right .25s; z-index: 49; }
  .drawer.open { right: 0; }
  .drawer h3 { color: var(--accent); font-size: 14px; margin: 18px 0 8px; }
  .drawer h3:first-child { margin-top: 0; }
  .drawer ul { margin: 6px 0; padding-left: 18px; font-size: 13px; }
  .drawer table { width:100%; font-size:12px; border-collapse: collapse; }
  .drawer td, .drawer th { padding: 4px 6px; border-bottom: 1px solid var(--border); text-align:left; }

  .disclaimer { margin: 20px; font-size: 11px; color: var(--muted); white-space: pre-wrap; border-top: 1px solid var(--border); padding-top: 12px; }

  body.compact .card { padding: 12px; }
  body.compact .metric-row { padding: 4px 0; font-size: 12px; }
  body.compact .grid { gap: 10px; }

  @media (max-width: 900px) {
    .left-panel { display:none; }
    .drawer { width: 88vw; right: -88vw; }
  }

  @media (max-width: 480px) {
    .center-panel { padding: 12px; }
    .card { padding: 14px; }
    .metric-row { flex-wrap: wrap; row-gap: 4px; }
    /* Move the INSIGHTS tab to a bottom-right pill instead of a vertical
       side tab, so it doesn't collide with the wrapped topbar/search
       controls on narrow phone widths. */
    .right-toggle { top: auto; bottom: 14px; right: 14px; border-radius: 20px; writing-mode: horizontal-tb; padding: 10px 16px; }
  }
</style>
</head>
<body class="investor-mode">
<div class="topbar">
  <h1>Stockizen Research Terminal</h1>
  <div class="controls">
    <button id="btnInvestor" class="active" onclick="setMode('investor')">Investor Mode</button>
    <button id="btnTrader" onclick="setMode('trader')">Trader Mode</button>
    <span style="width:1px;height:16px;background:var(--border);"></span>
    <button onclick="setTheme('dark')">Dark</button>
    <button onclick="setTheme('light')">Light</button>
    <button onclick="setTheme('amoled')">AMOLED</button>
    <span class="swatch" style="background:#38bdf8" onclick="setAccent('#38bdf8')"></span>
    <span class="swatch" style="background:#22c55e" onclick="setAccent('#22c55e')"></span>
    <span class="swatch" style="background:#a78bfa" onclick="setAccent('#a78bfa')"></span>
    <button onclick="toggleCompact()">Compact</button>
  </div>
</div>

<form class="search" method="POST" action="/">
  <input type="text" name="stock" placeholder="e.g. Reliance, TCS, AAPL, Apple, Tesla" value="{{ stock or '' }}" list="tickerSuggestions" autocomplete="off" required>
  <datalist id="tickerSuggestions">
    {% for item in autosuggest_list %}<option value="{{ item }}"></option>{% endfor %}
  </datalist>
  <label class="check"><input type="radio" name="market" value="IN" {% if market != 'US' %}checked{% endif %}> India (NSE)</label>
  <label class="check"><input type="radio" name="market" value="US" {% if market == 'US' %}checked{% endif %}> USA</label>
  <label class="check"><input type="checkbox" name="compare" value="1" {% if compare %}checked{% endif %} onchange="autoResubmit(this)"> Include peer comparison</label>
  <label class="check"><input type="checkbox" name="refresh" value="1"> Force refresh (skip cache)</label>
  <label class="check"><input type="checkbox" name="debug" value="1" {% if debug %}checked{% endif %}> Debug mode</label>
  <button type="submit">Analyze</button>
</form>

{% if error %}<p class="error">{{ error }}</p>{% endif %}

{% if r %}
<div class="summary">
  <div class="summary-block price-block">
    <span class="label">{{ r.name }} ({{ r.ticker }})</span>
    <span class="price">{{ '%.2f'|format(r.price) if r.price is not none else 'N/A' }} <small>{{ r.currency }}</small></span>
    {% if r.change is not none %}
      <span class="change {{ 'up' if r.change >= 0 else 'down' }}">{{ '%+.2f'|format(r.change) }} ({{ '%+.2f'|format(r.change_pct) }}%)</span>
    {% endif %}
  </div>
  <div class="summary-block">
    <span class="label">52W Range</span>
    {{ r.svg_range_slider|safe }}
    <span style="font-size:11px;color:var(--muted);">{{ '%.0f'|format(r.fifty2_low) if r.fifty2_low is not none else '-' }} — {{ '%.0f'|format(r.fifty2_high) if r.fifty2_high is not none else '-' }}</span>
  </div>
  <div class="summary-block">
    <span class="label">Analyst Target</span>
    <span style="font-weight:700;">{{ '%.2f'|format(r.target_mean_price) if r.target_mean_price is not none else 'N/A' }}</span>
    {% if r.upside_pct is not none %}<span class="{{ 'up' if r.upside_pct >= 0 else 'down' }}" style="font-size:12px;">{{ '%+.1f'|format(r.upside_pct) }}% upside</span>{% endif %}
  </div>
  <div class="summary-block">
    <span class="label">Verdict</span>
    <span class="badge badge-{{ r.verdict_badge|lower }}">{{ r.verdict_badge }}</span>
  </div>
  <div class="summary-block">
    <span class="label">Market Cap</span>
    <span class="chip">{{ '{:,.0f}'.format(r.market_cap) if r.market_cap is not none else 'N/A' }} {{ r.currency }}</span>
  </div>
  <div class="summary-block">
    <span class="label">Growth</span>
    <span class="badge badge-{{ 'high-good' if r.growth_badge=='HIGH' else ('moderate' if r.growth_badge=='MODERATE' else ('low' if r.growth_badge=='LOW' else 'na')) }}">{{ r.growth_badge }}</span>
  </div>
  <div class="summary-block">
    <span class="label">Risk</span>
    <span class="badge badge-{{ 'high-bad' if r.risk_badge=='HIGH' else ('moderate' if r.risk_badge=='MODERATE' else ('low' if r.risk_badge=='LOW' else 'na')) }}">{{ r.risk_badge }}</span>
  </div>
  <div class="summary-block">
    <span class="label">Valuation</span>
    <span class="badge badge-{{ 'expensive' if r.valuation_badge=='EXPENSIVE' else ('low' if r.valuation_badge=='FAIR' else 'na') }}">{{ r.valuation_badge }}</span>
  </div>
</div>
{% endif %}

<div class="layout">
  <div class="left-panel">
    <h3>Sectors (India)</h3>
    <div class="sector-nav">
      {% for sector, subsectors in sector_stocks.items() %}
      <div class="sector-group">
        <button class="pick-btn sector-toggle" onclick="toggleSector(this, 'in-sec-{{ loop.index }}')">{{ sector }} <span class="sector-caret">▾</span></button>
        <div class="sector-body" id="in-sec-{{ loop.index }}">
          {% for sub, tickers in subsectors.items() %}
            {% if sub != "All" %}<div class="sector-sub-label">{{ sub }}</div>{% endif %}
            <div class="chip-row" style="padding-left:6px; margin-bottom:6px;">
              {% for tk in tickers %}
                <button class="chip-btn" onclick="pick('{{ tk }}')">{{ tk.replace('.NS','') }}</button>
              {% endfor %}
            </div>
          {% endfor %}
        </div>
      </div>
      {% endfor %}
    </div>

    <h3>Sectors (USA)</h3>
    <div class="sector-nav">
      {% for sector, subsectors in us_sector_stocks.items() %}
      <div class="sector-group">
        <button class="pick-btn sector-toggle" onclick="toggleSector(this, 'us-sec-{{ loop.index }}')">{{ sector }} <span class="sector-caret">▾</span></button>
        <div class="sector-body" id="us-sec-{{ loop.index }}">
          {% for sub, tickers in subsectors.items() %}
            {% if sub != "All" %}<div class="sector-sub-label">{{ sub }}</div>{% endif %}
            <div class="chip-row" style="padding-left:6px; margin-bottom:6px;">
              {% for tk in tickers %}
                <button class="chip-btn" onclick="pick('{{ tk }}')">{{ tk }}</button>
              {% endfor %}
            </div>
          {% endfor %}
        </div>
      </div>
      {% endfor %}
    </div>

    {% if recent %}
    <h3>Recent Searches</h3>
    {% for tk in recent %}
      <button class="pick-btn" onclick="pick('{{ tk }}')">{{ tk.replace('.NS','') }}</button>
    {% endfor %}
    {% endif %}
  </div>

  <div class="center-panel">
    {% if r %}
    <p style="color:var(--muted); font-size:13px; max-width: 800px;">{{ r.summary }}</p>

    <div class="dq-wrap" title="How many key fields Yahoo Finance actually returned for this ticker">
      <span class="dq-dot dq-{{ r.dq_label|lower }}"></span>
      Data Quality: <strong>{{ r.dq_label }}</strong> ({{ '%.0f'|format(r.dq_pct) }}% of key fields present) — some fields may show N/A if Yahoo Finance doesn't provide them for this ticker.
    </div>

    <div class="grid" style="margin-top:16px;">

      <div class="card" id="cardFin">
        <div class="card-head"><span class="title"><span class="icon">📊</span> Financial Health</span><button class="expand-btn" onclick="toggleCard('cardFin')">Expand</button></div>
        <div class="metric-row"><span>Operating Margin</span><span class="val">{{ '%.1f'|format(r.operating_margin*100) ~ '%' if r.operating_margin is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Net Margin (gauge)</span>{{ r.svg_margin_gauge|safe }}</div>
        <div class="metric-row"><span>ROE</span><span class="val">{{ '%.1f'|format(r.roe*100) ~ '%' if r.roe is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Debt/Equity (gauge)</span>{{ r.svg_debt_gauge|safe }}</div>
        <div class="metric-row"><span>Revenue trend</span>{{ r.svg_revenue_spark|safe }}</div>
        <div class="metric-row"><span>Debt trend <span style="color:var(--muted); font-size:10px;">(lower = better)</span></span>{{ r.svg_debt_trend_spark|safe }}</div>
        <div class="details">
          <table class="mini">
            <tr><td>Return on Assets</td><td>{{ '%.1f'|format(r.roa*100) ~ '%' if r.roa is not none else 'N/A' }}</td></tr>
            <tr><td>Current Ratio</td><td>{{ '%.2f'|format(r.current_ratio) if r.current_ratio is not none else 'N/A' }}</td></tr>
            <tr><td>Quick Ratio (Acid-Test)</td><td>{{ '%.2f'|format(r.quick_ratio) if r.quick_ratio is not none else 'N/A' }}</td></tr>
            <tr><td>Gross Profit Margin</td><td>{{ '%.1f'|format(r.gross_margin*100) ~ '%' if r.gross_margin is not none else 'N/A' }}</td></tr>
            <tr><td>Interest Coverage Ratio</td><td>{{ '%.1fx'|format(r.interest_coverage) if r.interest_coverage is not none else 'N/A' }}</td></tr>
            <tr><td>Earnings Growth (YoY)</td><td>{{ '%.1f'|format(r.earnings_growth_yahoo*100) ~ '%' if r.earnings_growth_yahoo is not none else 'N/A' }}</td></tr>
            <tr><td>Operating Cash Flow (latest)</td><td>{{ '{:,.0f}'.format(r.ocf_latest) if r.ocf_latest is not none else 'N/A' }}</td></tr>
            <tr><td>Earnings Quality (OCF vs Net Income)</td><td>{{ r.earnings_quality_flag if r.earnings_quality_flag is not none else 'N/A' }}</td></tr>
            <tr><td>Inventory Turnover <span style="color:var(--muted);font-size:10px;">(retail/mfg)</span></td><td>{{ '%.2fx'|format(r.inventory_turnover) if r.inventory_turnover is not none else 'N/A' }}</td></tr>
            <tr><td>R&D as % of Revenue <span style="color:var(--muted);font-size:10px;">(tech/pharma)</span></td><td>{{ '%.1f'|format(r.rd_pct_revenue*100) ~ '%' if r.rd_pct_revenue is not none else 'N/A' }}</td></tr>
          </table>
          <p style="font-size:12px;margin-top:8px;"><strong>Net Income trend</strong></p>
          {{ r.svg_pat_spark|safe }}
        </div>
      </div>

      {% if r.is_bank %}
      <div class="card" id="cardBank">
        <div class="card-head"><span class="title"><span class="icon">🏦</span> Banking Metrics</span><button class="expand-btn" onclick="toggleCard('cardBank')">Expand</button></div>
        <div class="metric-row"><span>Net Interest Margin</span><span class="val">{{ '%.2f'|format(r.nim*100) ~ '%' if r.nim is not none else 'N/A' }}</span></div>
        <div class="metric-row">{{ r.svg_nim_gauge|safe }}</div>
        <div class="metric-row"><span>Cost-to-Income Ratio</span><span class="val">{{ '%.1f'|format(r.cir*100) ~ '%' if r.cir is not none else 'N/A' }}</span></div>
        <div class="metric-row">{{ r.svg_cir_gauge|safe }}</div>
        <div class="metric-row"><span>Credit-to-Deposit Ratio</span><span class="val">{{ '%.1f'|format(r.cdr*100) ~ '%' if r.cdr is not none else 'N/A' }}</span></div>
        <div class="metric-row">{{ r.svg_cdr_gauge|safe }}</div>
        <div class="details">
          <table class="mini">
            <tr><td>Return on Assets</td><td>{{ '%.2f'|format(r.roa*100) ~ '%' if r.roa is not none else 'N/A' }}</td></tr>
            <tr><td>Price to Book</td><td>{{ '%.2f'|format(r.pb) if r.pb is not none else 'N/A' }}</td></tr>
          </table>
          <p style="font-size:12px;color:var(--muted);margin-top:8px;">
            NIM / Cost-to-Income / Credit-to-Deposit are derived from Yahoo Finance's standard
            financial statements and may read N/A if a line item isn't broken out for this ticker.
            Gross/Net NPA%, Provision Coverage Ratio, CASA Ratio and Capital Adequacy Ratio (CAR/CET1)
            are regulatory disclosures not available via Yahoo Finance, so they are intentionally not
            shown here - check the bank's investor-presentation filings for those.
          </p>
        </div>
      </div>
      {% endif %}

      <div class="card" id="cardVal">
        <div class="card-head"><span class="title"><span class="icon">💰</span> Valuation</span><button class="expand-btn" onclick="toggleCard('cardVal')">Expand</button></div>
        <div class="metric-row"><span>Trailing P/E</span><span class="badge badge-{{ 'expensive' if (r.trailing_pe is not none and r.trailing_pe>35) else 'low' }}">{{ '%.1f'|format(r.trailing_pe) if r.trailing_pe is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Forward P/E</span><span class="val">{{ '%.1f'|format(r.forward_pe) if r.forward_pe is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>PEG Ratio</span><span class="badge badge-{{ 'low' if (r.peg_ratio is not none and r.peg_ratio<1) else 'expensive' }}">{{ '%.2f'|format(r.peg_ratio) if r.peg_ratio is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Price to Sales</span><span class="val">{{ '%.2f'|format(r.price_to_sales) if r.price_to_sales is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>52W Range</span>{{ r.svg_range_slider|safe }}</div>
        <div class="metric-row"><span>Dividend Yield</span><span class="chip">{{ '%.2f'|format(r.dividend_yield*100) ~ '%' if r.dividend_yield is not none else 'N/A' }}</span></div>
        <div class="details">
          <table class="mini">
            <tr><td>Price to Book</td><td>{{ '%.2f'|format(r.pb) if r.pb is not none else 'N/A' }}</td></tr>
            <tr><td>EV / EBITDA</td><td>{{ '%.2f'|format(r.ev_ebitda) if r.ev_ebitda is not none else 'N/A' }}</td></tr>
          </table>
        </div>
      </div>

      <div class="card" id="cardOwn">
        <div class="card-head"><span class="title"><span class="icon">🏛️</span> Ownership</span><button class="expand-btn" onclick="toggleCard('cardOwn')">Expand</button></div>
        <div style="display:flex; gap:20px; align-items:center;">
          <div style="text-align:center;">{{ r.svg_insider_donut|safe }}<div style="font-size:11px;color:var(--muted);">Insider</div></div>
          <div style="text-align:center;">{{ r.svg_institution_donut|safe }}<div style="font-size:11px;color:var(--muted);">Institutional</div></div>
        </div>
        <div class="details">
          <p style="font-size:12px;">Yahoo Finance does not expose exact NSE Promoter/FII/DII splits — these are the closest available fields.</p>
        </div>
      </div>

      <div class="card" id="cardRisk">
        <div class="card-head"><span class="title"><span class="icon">⚠️</span> Risk</span><button class="expand-btn" onclick="toggleCard('cardRisk')">Expand</button></div>
        {% for area, level, detail in r.risk_flags_sorted[:3] %}
          <div class="metric-row"><span>{{ area }}</span><span class="badge badge-{{ 'high-bad' if level=='High' else ('moderate' if level=='Moderate/Low' else 'na') }}">{{ level }}</span></div>
        {% endfor %}
        <div class="details">
          <table class="mini">
            {% for area, level, detail in r.risk_flags_sorted %}
            <tr><td>{{ area }}</td><td>{{ level }}</td><td>{{ detail }}</td></tr>
            {% endfor %}
          </table>
        </div>
      </div>

      <div class="card" id="cardGrowth">
        <div class="card-head"><span class="title"><span class="icon">🚀</span> Growth</span><button class="expand-btn" onclick="toggleCard('cardGrowth')">Expand</button></div>
        <div class="metric-row"><span>Revenue Growth (YoY)</span><span class="val">{{ '%.1f'|format(r.revenue_growth_yahoo*100) ~ '%' if r.revenue_growth_yahoo is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Bucket</span><span class="badge badge-{{ 'high-good' if r.growth_badge=='HIGH' else ('moderate' if r.growth_badge=='MODERATE' else 'na') }}">{{ r.growth_badge }}</span></div>
        <div class="metric-row"><span>Moat Score</span><span class="val">{{ r.moat_score }}/10</span></div>
        <div class="details"><p style="font-size:12px;">{{ r.growth_bucket }}</p></div>
      </div>

      <div class="card" id="cardAnalyst">
        <div class="card-head"><span class="title"><span class="icon">🧑‍💼</span> Analyst View</span><button class="expand-btn" onclick="toggleCard('cardAnalyst')">Expand</button></div>
        <div class="metric-row"><span>Recommendation</span><span class="chip">{{ r.recommendation_key }}</span></div>
        <div class="metric-row"><span>Target Price</span><span class="val">{{ '%.2f'|format(r.target_mean_price) if r.target_mean_price is not none else 'N/A' }}</span></div>
        <div class="details">
          <table class="mini">
            <tr><td>Recommendation Mean (1=Strong Buy, 5=Sell)</td><td>{{ '%.2f'|format(r.recommendation_mean) if r.recommendation_mean is not none else 'N/A' }}</td></tr>
            <tr><td># Analyst Opinions</td><td>{{ r.num_analysts if r.num_analysts is not none else 'N/A' }}</td></tr>
          </table>
        </div>
      </div>

      <div class="card trader-only">
        <div class="card-head"><span class="title"><span class="icon">📈</span> Trader Panel</span></div>
        <div class="metric-row"><span>Beta</span><span class="val">{{ '%.2f'|format(r.beta) if r.beta is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Current Ratio (Liquidity)</span><span class="val">{{ '%.2f'|format(r.current_ratio) if r.current_ratio is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>FCF trend</span>{{ r.svg_fcf_spark|safe }}</div>
        <div class="metric-row"><span>Revenue trend</span>{{ r.svg_revenue_spark|safe }}</div>
        <div class="metric-row"><span>Debt trend <span style="color:var(--muted); font-size:10px;">(lower = better)</span></span>{{ r.svg_debt_trend_spark|safe }}</div>
      </div>

      <div class="card trader-only" id="cardTech">
        <div class="card-head"><span class="title"><span class="icon">📉</span> Technical Indicators</span><button class="expand-btn" onclick="toggleCard('cardTech')">Expand</button></div>
        <div class="metric-row"><span>Price (60d)</span>{{ r.svg_price_spark|safe }}</div>
        <div class="metric-row"><span>RSI (14)</span><span class="badge badge-{{ 'high-bad' if r.tech.rsi_signal=='Overbought' else ('high-good' if r.tech.rsi_signal=='Oversold' else 'na') }}">{{ '%.0f'|format(r.tech.rsi14) if r.tech.rsi14 is not none else 'N/A' }}{{ ' - ' ~ r.tech.rsi_signal if r.tech.rsi_signal is not none else '' }}</span></div>
        <div class="metric-row"><span>MACD</span><span class="val">{{ r.tech.macd_signal_flag if r.tech.macd_signal_flag is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Price vs SMA50</span><span class="badge badge-{{ 'high-good' if r.tech.price_vs_sma50=='Above' else ('high-bad' if r.tech.price_vs_sma50=='Below' else 'na') }}">{{ r.tech.price_vs_sma50 if r.tech.price_vs_sma50 is not none else 'N/A' }}</span></div>
        <div class="metric-row"><span>Price vs SMA200</span><span class="badge badge-{{ 'high-good' if r.tech.price_vs_sma200=='Above' else ('high-bad' if r.tech.price_vs_sma200=='Below' else 'na') }}">{{ r.tech.price_vs_sma200 if r.tech.price_vs_sma200 is not none else 'N/A' }}</span></div>
        <div class="details">
          <table class="mini">
            <tr><td>SMA 20</td><td>{{ '%.2f'|format(r.tech.sma20) if r.tech.sma20 is not none else 'N/A' }}</td></tr>
            <tr><td>SMA 50</td><td>{{ '%.2f'|format(r.tech.sma50) if r.tech.sma50 is not none else 'N/A' }}</td></tr>
            <tr><td>SMA 200</td><td>{{ '%.2f'|format(r.tech.sma200) if r.tech.sma200 is not none else 'N/A' }}</td></tr>
            <tr><td>EMA 12 / EMA 26</td><td>{{ '%.2f'|format(r.tech.ema12) if r.tech.ema12 is not none else 'N/A' }} / {{ '%.2f'|format(r.tech.ema26) if r.tech.ema26 is not none else 'N/A' }}</td></tr>
            <tr><td>MACD / Signal / Hist</td><td>{{ '%.2f'|format(r.tech.macd) if r.tech.macd is not none else 'N/A' }} / {{ '%.2f'|format(r.tech.macd_signal_line) if r.tech.macd_signal_line is not none else 'N/A' }} / {{ '%.2f'|format(r.tech.macd_hist) if r.tech.macd_hist is not none else 'N/A' }}</td></tr>
            <tr><td>Bollinger Bands (20, 2σ)</td><td>{{ '%.2f'|format(r.tech.bb_lower) if r.tech.bb_lower is not none else 'N/A' }} - {{ '%.2f'|format(r.tech.bb_upper) if r.tech.bb_upper is not none else 'N/A' }}</td></tr>
            <tr><td>Volume vs 20d avg</td><td>{{ r.tech.volume_signal if r.tech.volume_signal is not none else 'N/A' }}</td></tr>
          </table>
          <p style="font-size:12px;color:var(--muted);margin-top:8px;">
            Computed from ~9 months of daily price history (Yahoo Finance). SMA200/RSI/MACD need
            enough trading history to compute, so recently-listed or thinly-traded tickers may show
            N/A for some of these until more history accumulates.
          </p>
        </div>
      </div>

      {% if debug %}
      <div class="card">
        <div class="card-head"><span class="title"><span class="icon">🧰</span> Developer / Debug</span></div>
        <div class="metric-row"><span>Data source</span><span class="val">{{ 'Cache' if r.debug_cache_hit else 'Live fetch (Yahoo Finance)' }}</span></div>
        <div class="metric-row"><span>API latency</span><span class="val">{{ '%.0f'|format(r.debug_latency_ms) ~ ' ms' if not r.debug_cache_hit else 'n/a (served from cache)' }}</span></div>
        <div class="metric-row"><span>Cache age</span><span class="val">{{ '%.0f'|format(r.debug_cache_age_s) ~ ' s' if r.debug_cache_hit else '0 s (just fetched)' }}</span></div>
        <div class="metric-row"><span>Cache TTL</span><span class="val">120 s</span></div>
        <div class="metric-row"><span>Resolved ticker</span><span class="val">{{ r.ticker }}</span></div>
      </div>
      {% endif %}

    </div>
    {% endif %}
  </div>
</div>

{% if r %}
<button class="right-toggle" onclick="toggleDrawer()">INSIGHTS{% if compare %} <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22c55e;margin-left:4px;"></span>{% endif %}</button>
<div class="drawer" id="rightDrawer">
  <h3>Rule-Based Verdict</h3>
  <span class="badge badge-{{ r.verdict_badge|lower }}">{{ r.verdict }}</span>
  <p style="font-size:12px;color:var(--muted);margin-top:8px;">Score across ROE, operating margin, debt-to-equity, revenue growth and P/E vs fixed thresholds.</p>

  <h3>Bull Points</h3>
  <ul>{% for p in r.bull_points %}<li>{{ p }}</li>{% endfor %}</ul>

  <h3>Bear Points</h3>
  <ul>{% for p in r.bear_points %}<li>{{ p }}</li>{% endfor %}</ul>

  <h3>Free Cash Flow (by year)</h3>
  {{ r.svg_fcf_spark|safe }}
  {% if r.fcf_display %}
  <table><tr><th>Year</th><th>FCF</th></tr>
  {% for label, v in r.fcf_display %}<tr><td>{{ label }}</td><td>{{ '{:,.0f}'.format(v) }}</td></tr>{% endfor %}
  </table>
  {% endif %}

  <h3>Total Debt (by year) <span style="color:var(--muted); font-size:11px; font-weight:normal;">— lower is generally better</span></h3>
  {{ r.svg_debt_trend_spark|safe }}
  {% if r.debt_display %}
  <table><tr><th>Year</th><th>Total Debt</th></tr>
  {% for label, v in r.debt_display %}<tr><td>{{ label }}</td><td>{{ '{:,.0f}'.format(v) }}</td></tr>{% endfor %}
  </table>
  {% endif %}

  {% if peers %}
  <h3>Compare with Competitors</h3>
  <table>
    <tr><th>Ticker</th><th>P/E</th><th>Net Margin</th><th>ROE</th><th>Rev Growth</th><th>Target</th></tr>
    {% for p in peers %}
    <tr>
      <td>{{ p.name }}</td>
      <td>{{ '%.1f'|format(p.trailing_pe) if p.trailing_pe is not none else 'N/A' }}</td>
      <td>{{ '%.1f'|format(p.profit_margin*100) ~ '%' if p.profit_margin is not none else 'N/A' }}</td>
      <td>{{ '%.1f'|format(p.roe*100) ~ '%' if p.roe is not none else 'N/A' }}</td>
      <td>{{ '%.1f'|format(p.revenue_growth*100) ~ '%' if p.revenue_growth is not none else 'N/A' }}</td>
      <td>{{ '%.0f'|format(p.target_mean_price) if p.target_mean_price is not none else 'N/A' }}</td>
    </tr>
    {% endfor %}
  </table>
  {% elif compare %}
  <h3>Compare with Competitors</h3>
  <p style="font-size:12px;color:var(--muted);">No peer list configured for this ticker yet — add it to PEER_MAP in app.py.</p>
  {% endif %}
</div>
{% if compare %}
<script>
  // Auto-open the INSIGHTS drawer when the user asked for peer comparison,
  // so the result isn't hidden behind a tab they have to know to click.
  document.getElementById('rightDrawer').classList.add('open');
</script>
{% endif %}
{% endif %}

<div class="disclaimer">{{ disclaimer }}</div>

<script>
function pick(ticker) {
  const input = document.querySelector('input[name="stock"]');
  input.value = ticker;
  const marketVal = ticker.includes('.') ? 'IN' : 'US';
  const radio = document.querySelector('input[name="market"][value="' + marketVal + '"]');
  if (radio) radio.checked = true;
  input.closest('form').submit();
}
function autoResubmit(checkbox) {
  const input = document.querySelector('input[name="stock"]');
  if (input && input.value.trim()) {
    checkbox.closest('form').submit();
  }
}
function toggleDrawer() { document.getElementById('rightDrawer').classList.toggle('open'); }
function toggleCard(id) { document.getElementById(id).classList.toggle('expanded'); }
function toggleSector(btn, id) { document.getElementById(id).classList.toggle('open'); btn.classList.toggle('open'); }
function setTheme(t) { document.documentElement.setAttribute('data-theme', t); localStorage.setItem('stockizen_theme', t); }
function setAccent(c) { document.documentElement.style.setProperty('--accent', c); localStorage.setItem('stockizen_accent', c); }
function toggleCompact() { document.body.classList.toggle('compact'); localStorage.setItem('stockizen_compact', document.body.classList.contains('compact')); }
function setMode(m) {
  document.body.classList.toggle('trader-mode', m === 'trader');
  document.body.classList.toggle('investor-mode', m === 'investor');
  document.getElementById('btnInvestor').classList.toggle('active', m === 'investor');
  document.getElementById('btnTrader').classList.toggle('active', m === 'trader');
  localStorage.setItem('stockizen_mode', m);
}
(function restore() {
  const theme = localStorage.getItem('stockizen_theme') || 'dark';
  setTheme(theme);
  const accent = localStorage.getItem('stockizen_accent');
  if (accent) setAccent(accent);
  if (localStorage.getItem('stockizen_compact') === 'true') document.body.classList.add('compact');
  const mode = localStorage.getItem('stockizen_mode') || 'investor';
  setMode(mode);
})();
</script>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    stock = None
    r = None
    error = None
    peers = None
    compare = False
    debug = False
    market = "IN"

    if request.method == "POST":
        stock = request.form.get("stock", "").strip()
        compare = request.form.get("compare") == "1"
        debug = request.form.get("debug") == "1"
        force_refresh = request.form.get("refresh") == "1"
        market = request.form.get("market", "IN")
        if not stock:
            error = "Please enter a stock name or symbol."
        else:
            ticker_symbol = resolve_ticker(stock, market)
            try:
                r = build_report(ticker_symbol, force_refresh=force_refresh)
                if r["price"] is None and r["name"] == ticker_symbol:
                    error = (
                        f"Could not find data for '{stock}' (tried ticker {ticker_symbol}). "
                        "For India, try the exact NSE symbol (e.g. RELIANCE). For the US, "
                        "try the exact ticker (e.g. AAPL) and make sure 'USA' is selected."
                    )
                    r = None
                else:
                    recent = session.get("recent", [])
                    if ticker_symbol in recent:
                        recent.remove(ticker_symbol)
                    recent.insert(0, ticker_symbol)
                    session["recent"] = recent[:8]
                    if compare:
                        peers = build_peers(ticker_symbol, r)
            except Exception as e:
                error = f"Could not fetch data for '{stock}' (tried ticker {ticker_symbol}). Error: {e}"

    return render_template_string(
        PAGE, stock=stock, r=r, error=error, disclaimer=DISCLAIMER,
        quick_picks=QUICK_PICKS, us_quick_picks=US_QUICK_PICKS, sector_shortcuts=SECTOR_SHORTCUTS,
        sector_stocks=SECTOR_STOCKS, us_sector_stocks=US_SECTOR_STOCKS, autosuggest_list=AUTOSUGGEST_LIST,
        recent=session.get("recent", []), peers=peers, compare=compare, market=market, debug=debug,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7003))
    app.run(host="0.0.0.0", port=port)
