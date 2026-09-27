from __future__ import annotations

import html
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from aaii import aaii_view, ensure_poller, refresh_aaii
from naaim import (
    STOCKCHARTS_CHART as STOCKCHARTS_CHART_URL,
    backfill_naaim_history,
    latest_thursday,
    naaim_year_rows,
    reading_from_csv,
    refresh_sentiment,
    save_sentiment_reading,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"

DEFAULT_WATCHLIST = ["SPY", "QQQ", "TSLA", "NVDA", "AAPL", "AMZN", "GOOGL", "AMD"]
TREND_SYMBOLS = [
    ("SPY", "SPY"),
    ("QQQ", "QQQ"),
]
RIGHT_BLANK_RATIO = 0.23
CHART_PERIODS = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default):
    ensure_data_dir()
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, payload) -> None:
    ensure_data_dir()
    path.write_text(json.dumps(payload, indent=2))


def load_watchlist() -> list[str]:
    raw = load_json(WATCHLIST_PATH, DEFAULT_WATCHLIST)
    symbols = []
    seen = set()
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols or DEFAULT_WATCHLIST.copy()


def save_watchlist(symbols: list[str]) -> None:
    save_json(WATCHLIST_PATH, symbols)


def load_naaim() -> dict:
    reading = reading_from_csv()
    if reading:
        return reading
    return {"value": None, "as_of": None, "note": "", "source": None}


def save_naaim(value: float, as_of: str, note: str = "") -> None:
    save_sentiment_reading(
        {
            "date": as_of,
            "value": value,
            "source": "manual",
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }
    )


def auto_refresh_naaim(force: bool = False) -> dict:
    try:
        refresh_sentiment(force=force)
    except Exception as exc:
        cached = reading_from_csv()
        if cached:
            cached["error"] = str(exc)
            return cached
        return {"value": None, "as_of": None, "note": "", "source": None, "error": str(exc)}
    reading = reading_from_csv() or {"value": None, "as_of": None, "note": "", "source": None}
    return reading


@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    frame = ticker.history(period=period, auto_adjust=True)
    if frame is None or frame.empty:
        raise ValueError(f"No price data returned for {symbol}.")
    frame = frame.rename(columns=str.title)
    required = {"Open", "High", "Low", "Close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Incomplete OHLC data for {symbol}: missing {missing}")
    close = frame["Close"]
    frame["EMA10"] = close.ewm(span=10, adjust=False).mean()
    frame["EMA20"] = close.ewm(span=20, adjust=False).mean()
    return frame


@st.cache_data(ttl=180, show_spinner=False)
def fetch_watchlist_quotes(symbols: tuple[str, ...]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame(columns=["Ticker", "Last", "Change %"])

    raw = yf.download(
        list(symbols),
        period="5d",
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    rows = []
    for symbol in symbols:
        close = extract_close_series(raw, symbol, len(symbols))
        if close is None or close.dropna().shape[0] < 2:
            rows.append({"Ticker": symbol, "Last": None, "Change %": None})
            continue
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = ((last / prev) - 1.0) * 100 if prev else None
        rows.append({"Ticker": symbol, "Last": last, "Change %": change_pct})
    return pd.DataFrame(rows)


def extract_close_series(raw: pd.DataFrame, symbol: str, symbol_count: int) -> pd.Series | None:
    if raw is None or raw.empty:
        return None
    if symbol_count == 1:
        if "Close" in raw.columns:
            return raw["Close"].dropna()
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        if (symbol, "Close") in raw.columns:
            return raw[(symbol, "Close")].dropna()
        if ("Close", symbol) in raw.columns:
            return raw[("Close", symbol)].dropna()
    if "Close" in raw.columns and symbol in getattr(raw["Close"], "columns", []):
        return raw["Close"][symbol].dropna()
    return None


def classify_trend(row: pd.Series) -> tuple[str, str, dict[str, bool]]:
    price = float(row["Close"])
    ema10 = float(row["EMA10"])
    ema20 = float(row["EMA20"])
    above_10 = price > ema10
    above_20 = price > ema20
    ema10_above_ema20 = ema10 > ema20
    checks = {
        "Price above 10 EMA": above_10,
        "Price above 20 EMA": above_20,
        "10 EMA above 20 EMA": ema10_above_ema20,
    }
    if above_10 and above_20 and ema10_above_ema20:
        return "Uptrend", "green", checks
    if (not above_10) and (not above_20) and (not ema10_above_ema20):
        return "Downtrend", "red", checks
    return "Use caution", "orange", checks


def classify_naaim(value: float | None) -> tuple[str, str]:
    if value is None:
        return "Waiting for this week's reading", "gray"
    if value > 100:
        return "Euphoria", "red"
    if value < 60:
        return "Panic", "blue"
    return "Neutral", "green"


def format_price(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def format_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}%"


def signal_card(title: str, frame: pd.DataFrame) -> None:
    latest = frame.iloc[-1]
    label, color, checks = classify_trend(latest)
    prev_close = float(frame["Close"].iloc[-2]) if len(frame) > 1 else None
    last = float(latest["Close"])
    change = ((last / prev_close) - 1.0) * 100 if prev_close else None
    as_of = latest.name
    as_of_text = pd.Timestamp(as_of).strftime("%Y-%m-%d")

    st.markdown(
        f"""
        <div class="signal-card {color}">
            <div class="signal-kicker">{title}</div>
            <div class="signal-price">{format_price(last)} <span>{format_pct(change)}</span></div>
            <div class="signal-badge {color}">{label}</div>
            <div class="signal-meta">As of {as_of_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for check_name, passed in checks.items():
        mark = "Yes" if passed else "No"
        st.caption(f"{check_name}: **{mark}**")
    st.caption(
        f"EMA10 {format_price(float(latest['EMA10']))}  ·  EMA20 {format_price(float(latest['EMA20']))}"
    )


def tradingview_candles(frame: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=frame.index,
            open=frame["Open"],
            high=frame["High"],
            low=frame["Low"],
            close=frame["Close"],
            name=title,
            increasing={"line": {"color": "#089981"}, "fillcolor": "#089981"},
            decreasing={"line": {"color": "#f23645"}, "fillcolor": "#f23645"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["EMA10"],
            name="EMA 10",
            mode="lines",
            line={"color": "#f23645", "width": 1.6},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["EMA20"],
            name="EMA 20",
            mode="lines",
            line={"color": "#2962ff", "width": 1.6},
        )
    )
    xaxis: dict = {"rangeslider": {"visible": False}, "showgrid": True, "gridcolor": "#ececec"}
    if len(frame.index) >= 2:
        start = frame.index[0]
        candle_right = frame.index[-1] + pd.Timedelta(hours=12)
        span = candle_right - start
        pad = span * (RIGHT_BLANK_RATIO / (1 - RIGHT_BLANK_RATIO))
        xaxis["range"] = [start, candle_right + pad]
    fig.update_layout(
        title=title,
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        height=430,
        margin={"l": 10, "r": 10, "t": 48, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        xaxis=xaxis,
        yaxis={"showgrid": True, "gridcolor": "#ececec", "side": "right"},
        font={"color": "#111827"},
    )
    return fig


def inject_css() -> None:
    st.markdown(
        """
        <style>
            .signal-card {
                border: 1px solid #e5e7eb;
                border-left-width: 6px;
                border-radius: 12px;
                padding: 14px 16px;
                background: #fff;
                margin-bottom: 8px;
            }
            .signal-card.green { border-left-color: #16a34a; }
            .signal-card.red { border-left-color: #dc2626; }
            .signal-card.orange { border-left-color: #f59e0b; }
            .signal-kicker { font-size: 0.85rem; color: #6b7280; font-weight: 600; }
            .signal-price { font-size: 1.6rem; font-weight: 700; margin: 4px 0; }
            .signal-price span { font-size: 0.95rem; font-weight: 600; color: #4b5563; }
            .signal-badge {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 999px;
                font-weight: 700;
                font-size: 0.85rem;
                margin: 4px 0;
            }
            .signal-badge.green { background: #dcfce7; color: #166534; }
            .signal-badge.red { background: #fee2e2; color: #991b1b; }
            .signal-badge.orange { background: #fef3c7; color: #92400e; }
            .signal-meta { color: #6b7280; font-size: 0.8rem; }
            .naaim-card {
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 16px 18px;
                background: #fff;
            }
            .naaim-value { font-size: 2.2rem; font-weight: 800; margin: 4px 0; }
            .naaim-badge {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 999px;
                font-weight: 700;
            }
            .naaim-badge.red { background: #fee2e2; color: #991b1b; }
            .naaim-badge.blue { background: #dbeafe; color: #1e3a8a; }
            .naaim-badge.green { background: #dcfce7; color: #166534; }
            .naaim-badge.gray { background: #f3f4f6; color: #374151; }
            .naaim-scroll {
                max-height: 340px;
                overflow: auto;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                background: #fff;
                margin-top: 12px;
            }
            .naaim-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .naaim-table th, .naaim-table td {
                text-align: left;
                padding: 5px 10px;
                border-bottom: 1px solid #eef0f3;
                font-variant-numeric: tabular-nums;
            }
            .naaim-table th {
                position: sticky;
                top: 0;
                background: #f8fafc;
                color: #6b7280;
                font-size: 11px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .naaim-table td.up { color: #16a34a; }
            .naaim-table td.down { color: #dc2626; }
            .aaii { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; }
            .aaii-card {
                background: #fff;
                border-radius: 12px;
                border: 1px solid rgba(14, 42, 67, 0.12);
                padding: 1.3rem;
                margin-bottom: 1.3rem;
            }
            .aaii-card h3 {
                font-size: 12px;
                font-weight: 700;
                color: #5f6b7a;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin: 0 0 0.9rem;
            }
            .aaii-chart { overflow-x: auto; }
            .aaii-week { display: flex; align-items: center; margin-bottom: 0.5rem; }
            .aaii-week-head { align-items: flex-end; }
            .aaii-date {
                display: flex;
                align-items: center;
                width: 168px;
                flex-shrink: 0;
                font-weight: 700;
                font-size: 14px;
                line-height: 1.2;
            }
            .aaii-datebars { display: flex; width: 100%; align-items: center; min-width: 0; }
            .aaii-bars { display: flex; flex: 1; min-width: 0; align-items: stretch; }
            .aaii-bar {
                padding: 0.75rem;
                color: #fff;
                font-weight: 700;
                display: flex;
                align-items: center;
                box-sizing: border-box;
                font-size: 14px;
                line-height: 1;
                white-space: nowrap;
            }
            .aaii-bull { background: green; }
            .aaii-neut { background: #999; }
            .aaii-bear { background: red; }
            .aaii-legend {
                width: 15px;
                height: 15px;
                display: inline-block;
                margin-right: 5px;
                vertical-align: -2px;
            }
            .aaii-votes { flex: 1; min-width: 0; font-size: 14px; }
            .aaii-votes p { margin: 0 0 0.5rem; font-weight: 600; }
            .aaii-key { margin-right: 14px; white-space: nowrap; }
            .aaii-ending {
                display: flex;
                align-items: center;
                margin-left: 0.5rem;
                font-size: 14px;
                color: #5f6b7a;
                white-space: nowrap;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def style_watchlist(frame: pd.DataFrame):
    display = frame.copy()
    display["Last"] = display["Last"].map(lambda x: None if pd.isna(x) else float(x))
    display["Change %"] = display["Change %"].map(lambda x: None if pd.isna(x) else float(x))

    def color_change(val):
        if val is None or pd.isna(val):
            return "color: #6b7280"
        if val > 0:
            return "color: #16a34a; font-weight: 600"
        if val < 0:
            return "color: #dc2626; font-weight: 600"
        return "color: #111827"

    return (
        display.style.format({"Last": lambda v: "—" if v is None else f"{v:,.2f}", "Change %": format_pct})
        .map(color_change, subset=["Change %"])
        .hide(axis="index")
    )


def render_sidebar(watchlist: list[str]) -> list[str]:
    st.sidebar.title("Watchlist")
    st.sidebar.caption("Add, replace, or remove tickers. Changes are saved locally.")

    quotes = fetch_watchlist_quotes(tuple(watchlist))
    st.sidebar.dataframe(style_watchlist(quotes), width="stretch", height=320)

    st.sidebar.subheader("Add ticker")
    with st.sidebar.form("add_ticker_form", clear_on_submit=True):
        new_symbol = st.text_input("Symbol", placeholder="MSFT").strip().upper()
        added = st.form_submit_button("Add")
        if added and new_symbol:
            if new_symbol in watchlist:
                st.sidebar.warning(f"{new_symbol} is already on the list.")
            else:
                try:
                    test = fetch_history(new_symbol, "1mo")
                    if test.empty:
                        raise ValueError("empty")
                    watchlist = watchlist + [new_symbol]
                    save_watchlist(watchlist)
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.sidebar.error(f"Could not load {new_symbol}. Check the ticker.")

    st.sidebar.subheader("Replace ticker")
    if watchlist:
        with st.sidebar.form("replace_ticker_form"):
            current = st.selectbox("Current symbol", watchlist)
            replacement = st.text_input("New symbol", placeholder="META").strip().upper()
            replaced = st.form_submit_button("Replace")
            if replaced and replacement:
                try:
                    fetch_history(replacement, "1mo")
                    watchlist = [replacement if item == current else item for item in watchlist]
                    deduped = []
                    seen = set()
                    for item in watchlist:
                        if item not in seen:
                            deduped.append(item)
                            seen.add(item)
                    watchlist = deduped
                    save_watchlist(watchlist)
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.sidebar.error(f"Could not load {replacement}.")

    st.sidebar.subheader("Remove ticker")
    if watchlist:
        with st.sidebar.form("remove_ticker_form"):
            to_remove = st.selectbox("Remove symbol", watchlist, key="remove_symbol")
            removed = st.form_submit_button("Remove")
            if removed:
                watchlist = [item for item in watchlist if item != to_remove]
                save_watchlist(watchlist)
                st.cache_data.clear()
                st.rerun()

    if st.sidebar.button("Reset default watchlist"):
        watchlist = DEFAULT_WATCHLIST.copy()
        save_watchlist(watchlist)
        st.cache_data.clear()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("NAAIM this week")
    st.sidebar.caption(
        "Auto-fetched from StockCharts !NAAIM on app refresh. New readings typically post on Thursday. Manual override is optional."
    )
    saved = load_naaim()
    default_value = float(saved["value"]) if saved.get("value") is not None else 0.0
    default_date = date.fromisoformat(saved["as_of"]) if saved.get("as_of") else latest_thursday()
    with st.sidebar.expander("Manual override"):
        with st.form("naaim_form"):
            naaim_value = st.number_input("Exposure index", value=default_value, step=0.1, format="%.2f")
            naaim_date = st.date_input("Week of (typically Thursday)", value=default_date)
            saved_click = st.form_submit_button("Save NAAIM")
            if saved_click:
                save_naaim(float(naaim_value), naaim_date.isoformat())
                st.cache_data.clear()
                st.rerun()

    if st.sidebar.button("Refresh market data"):
        st.cache_data.clear()
        auto_refresh_naaim(force=True)
        try:
            backfill_naaim_history(force=True)
        except Exception:
            pass
        try:
            refresh_aaii(force=True)
        except Exception as exc:
            st.sidebar.warning(f"AAII refresh failed: {exc}")
        st.rerun()

    return watchlist


def render_naaim() -> None:
    saved = auto_refresh_naaim(force=False)
    value = saved.get("value")
    label, tone = classify_naaim(value if value is None else float(value))
    as_of = saved.get("as_of") or "—"
    source = saved.get("source") or "pending"
    st.markdown(
        f"""
        <div class="naaim-card">
            <div class="signal-kicker">NAAIM Exposure Index</div>
            <div class="naaim-value">{'—' if value is None else f'{float(value):.2f}'}</div>
            <div class="naaim-badge {tone}">{label}</div>
            <div class="signal-meta">Week of {as_of} · source {source} · above 100 = euphoria · below 60 = panic</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if saved.get("error") and value is None:
        st.warning(f"Automatic NAAIM fetch failed: {saved['error']}")
    elif saved.get("error"):
        st.caption(f"Using saved reading. Latest fetch note: {saved['error']}")
    st.link_button("Open StockCharts !NAAIM", STOCKCHARTS_CHART_URL)
    render_naaim_table()


def render_naaim_table() -> None:
    rows = naaim_year_rows()
    if not rows:
        st.caption("NAAIM history has not been stored yet.")
        return
    body = []
    for row in rows:
        change = row["change"]
        if change is None:
            change_html = "—"
            tone = ""
        else:
            tone = "up" if change > 0 else "down" if change < 0 else ""
            change_html = f"{change:+.2f}"
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['date']))}</td>"
            f"<td>{float(row['exposure']):.2f}</td>"
            f"<td class='{tone}'>{change_html}</td>"
            "</tr>"
        )
    st.markdown(
        f"""
        <div class="naaim-scroll">
            <table class="naaim-table">
                <thead><tr><th>Week</th><th>Exposure</th><th>Change</th></tr></thead>
                <tbody>{"".join(body)}</tbody>
            </table>
        </div>
        <div class="signal-meta" style="margin-top:6px;">
            Last 12 months · {len(rows)} weeks on screen · older weeks stay in the archive
        </div>
        """,
        unsafe_allow_html=True,
    )


def _pct1(value: float) -> str:
    return f"{float(value):.1f}%"


def _bar(tone: str, value: float) -> str:
    return f'<div class="aaii-bar aaii-{tone}" style="width:{float(value):.1f}%">{_pct1(value)}</div>'


def render_aaii() -> None:
    view = aaii_view()
    chart = view.get("chart")
    st.subheader("AAII Investor Sentiment Survey")
    st.caption("Individual investors, asked each week where the market is headed over the next six months.")
    if not chart:
        st.warning(view.get("message") or "The AAII chart is not available yet.")
        return
    recent_rows = []
    for week in chart["recent"]:
        recent_rows.append(
            "<div class='aaii-week'><div class='aaii-datebars'>"
            f"<div class='aaii-date'>{html.escape(str(week['weekEnding']))}</div>"
            "<div class='aaii-bars'>"
            f"{_bar('bull', week['bullish'])}{_bar('neut', week['neutral'])}{_bar('bear', week['bearish'])}"
            "</div></div></div>"
        )
    highs = chart["highs"]
    high_rows = []
    for label, key, tone in (
        ("1-Year Bullish High", "bullish", "bull"),
        ("1-Year Neutral High", "neutral", "neut"),
        ("1-Year Bearish High", "bearish", "bear"),
    ):
        item = highs[key]
        high_rows.append(
            "<div class='aaii-week'><div class='aaii-datebars'>"
            f"<div class='aaii-date'>{label}</div><div class='aaii-bars'>"
            f"{_bar(tone, item['value'])}"
            f"<div class='aaii-ending'>Week Ending {html.escape(str(item['weekEnding']))}</div>"
            "</div></div></div>"
        )
    averages = chart["averages"]
    st.markdown(
        f"""
        <div class="aaii">
          <div class="aaii-card">
            <h3>Recent weekly results</h3>
            <div class="aaii-chart">
              <div class="aaii-week aaii-week-head">
                <div class="aaii-date">Week Ending</div>
                <div class="aaii-votes">
                  <p>Sentiment Votes</p>
                  <span class="aaii-key"><span class="aaii-legend aaii-bull"></span>Bullish</span>
                  <span class="aaii-key"><span class="aaii-legend aaii-neut"></span>Neutral</span>
                  <span class="aaii-key"><span class="aaii-legend aaii-bear"></span>Bearish</span>
                </div>
              </div>
              {"".join(recent_rows)}
            </div>
          </div>
          <div class="aaii-card">
            <h3>Historical view</h3>
            <div class="aaii-chart">
              <div class="aaii-week"><div class="aaii-datebars">
                <div class="aaii-date">Historical Averages</div>
                <div class="aaii-bars">
                  {_bar("bull", averages["bullish"])}{_bar("neut", averages["neutral"])}{_bar("bear", averages["bearish"])}
                </div>
              </div></div>
              {"".join(high_rows)}
            </div>
          </div>
        </div>
        <div class="signal-meta">{html.escape(str(view.get("message") or ""))}</div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Market Monitor", layout="wide")
    inject_css()
    ensure_data_dir()
    if not WATCHLIST_PATH.exists():
        save_watchlist(DEFAULT_WATCHLIST)

    watchlist = load_watchlist()
    ensure_poller()
    try:
        backfill_naaim_history(force=False)
    except Exception:
        pass
    try:
        refresh_aaii(force=False)
    except Exception:
        pass
    auto_refresh_naaim(force=False)
    render_sidebar(watchlist)

    st.title("Market Monitor")
    st.caption("Daily trend check for SPY and QQQ, plus NAAIM, AAII sentiment, and a live watchlist.")

    period_label = st.radio("Chart range", list(CHART_PERIODS.keys()), index=1, horizontal=True)
    period = CHART_PERIODS[period_label]

    st.subheader("Trend signals")
    cols = st.columns(2)
    for column, (symbol, title) in zip(cols, TREND_SYMBOLS):
        with column:
            try:
                frame = fetch_history(symbol, period)
                signal_card(title, frame)
            except Exception as exc:
                st.error(f"Could not load {title} ({symbol}): {exc}")

    st.subheader("SPY and QQQ charts")
    st.caption("White TradingView-style candles with 10 EMA in red and 20 EMA in blue. Charts open on 3 months.")

    left, right = st.columns(2)
    for column, symbol in zip((left, right), ("SPY", "QQQ")):
        with column:
            try:
                frame = fetch_history(symbol, period)
                st.plotly_chart(tradingview_candles(frame, symbol), width="stretch")
            except Exception as exc:
                st.error(f"Could not draw {symbol}: {exc}")

    st.subheader("NAAIM exposure")
    render_naaim()
    render_aaii()


if __name__ == "__main__":
    main()
