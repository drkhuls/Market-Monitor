"""S&P 500 breadth from the same indexes TradingView charts.

Percent of stocks above a moving average comes from the published S&P 500
indexes (5, 20, 50, and 200 day). A 10-day index is not published. New highs
and new lows are the counts on the S&P 500 page for 5 days, 1 month, 3 months,
and 1 year.
"""

from __future__ import annotations

import json
import random
import re
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import websocket

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_PATH = DATA_DIR / "breadth.json"
SPX_URL = "https://www.tradingview.com/symbols/SPX/"
SOCKET_URL = "wss://data.tradingview.com/socket.io/websocket"

MA_SYMBOLS = [
    ("5-day", "INDEX:S5FD"),
    ("20-day", "INDEX:S5TW"),
    ("50-day", "INDEX:S5FI"),
    ("200-day", "INDEX:S5TH"),
]
PERIODS = ("5D", "1M", "3M", "1Y")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html",
}


def _packet(message: str) -> str:
    return f"~m~{len(message)}~m~{message}"


def _send(sock: websocket.WebSocket, method: str, params: list[Any]) -> None:
    sock.send(_packet(json.dumps({"m": method, "p": params})))


def fetch_moving_averages() -> list[dict[str, Any]]:
    symbols = [symbol for _, symbol in MA_SYMBOLS]
    sock = websocket.create_connection(
        SOCKET_URL,
        origin="https://www.tradingview.com",
        timeout=12,
        header=["User-Agent: " + HEADERS["User-Agent"]],
    )
    session = "qs_" + "".join(random.choices(string.ascii_lowercase, k=10))
    try:
        _send(sock, "set_auth_token", ["unauthorized_user_token"])
        _send(sock, "quote_create_session", [session])
        _send(sock, "quote_set_fields", [session, "lp", "ch", "short_name"])
        _send(sock, "quote_add_symbols", [session, *symbols])
        found: dict[str, float] = {}
        while len(found) < len(symbols):
            raw = sock.recv()
            for match in re.finditer(
                r'\{"n":"(INDEX:[^"]+)","s":"ok","v":(\{.*?\})\}',
                raw,
            ):
                payload = json.loads(match.group(2))
                if "lp" in payload:
                    found[match.group(1)] = float(payload["lp"])
            if "critical_error" in raw:
                break
    finally:
        sock.close()
    missing = [symbol for symbol in symbols if symbol not in found]
    if missing:
        raise RuntimeError(f"Missing breadth quotes for {', '.join(missing)}")
    rows = []
    for label, symbol in MA_SYMBOLS:
        value = found[symbol]
        if value >= 70:
            tone = "stretched"
        elif value <= 30:
            tone = "washed"
        else:
            tone = "mixed"
        rows.append({"label": label, "value": round(value, 1), "tone": tone, "symbol": symbol})
    return rows


def parse_highs_lows(html: str) -> list[dict[str, Any]]:
    start = html.find("New highs and lows")
    if start < 0:
        raise ValueError("New highs and lows section was not on the page")
    end = html.find("Above moving averages", start)
    chunk = html[start : end if end > start else start + 20000]
    scale_values: list[int] = []
    for raw in re.findall(r'scaleValue-[^"]*">([^<]+)', chunk):
        cleaned = (
            raw.replace("\u202a", "")
            .replace("\u202c", "")
            .replace("−", "-")
            .replace("%", "")
            .strip()
        )
        if re.fullmatch(r"-?\d+", cleaned):
            scale_values.append(int(cleaned))
    if not scale_values:
        raise ValueError("Could not read the highs and lows scale")
    scale = max(abs(value) for value in scale_values)
    bars = re.findall(
        r'class="([^"]*\bbar-[^"]*)"[^>]*style="height:max\(([0-9.]+)%',
        chunk,
    )
    if len(bars) < len(PERIODS) * 2:
        raise ValueError("Could not read highs and lows bars")
    rows = []
    for index, period in enumerate(PERIODS):
        up_class, up_height = bars[index * 2]
        down_class, down_height = bars[index * 2 + 1]
        span = scale * 2
        highs = int(round(float(up_height) / 100 * span))
        lows = int(round(float(down_height) / 100 * span))
        if "negative" not in down_class and "negative" in up_class:
            highs, lows = lows, highs
        rows.append(
            {
                "period": period,
                "highs": highs,
                "lows": lows,
                "net": highs - lows,
            }
        )
    return rows


def fetch_highs_lows() -> list[dict[str, Any]]:
    response = requests.get(SPX_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return parse_highs_lows(response.text)


def _read_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = CACHE_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2))
    temp.replace(CACHE_PATH)


def load_breadth() -> dict[str, Any]:
    """Current breadth, falling back to the last saved reading."""
    cached = _read_cache()
    averages = None
    highs = None
    error = None
    try:
        averages = fetch_moving_averages()
    except Exception as exc:
        error = str(exc)
    try:
        highs = fetch_highs_lows()
    except Exception as exc:
        error = f"{error}; {exc}" if error else str(exc)
    if averages and highs:
        payload = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "averages": averages,
            "highsLows": highs,
            "note": (
                "S&P 500. A 10-day breadth index is not published, "
                "so the short window is the 5-day and 20-day readings. "
                "Under 30% is washed out. Over 70% is stretched."
            ),
        }
        _write_cache(payload)
        return payload
    if cached and cached.get("averages") and cached.get("highsLows"):
        cached["error"] = error
        return cached
    raise RuntimeError(error or "Breadth data is unavailable")


if __name__ == "__main__":
    print(json.dumps(load_breadth(), indent=2))
