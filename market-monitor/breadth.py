"""S&P 500 breadth and the daily US net-new-highs archive.

Percent of stocks above a moving average comes from the published S&P 500
indexes (5, 20, 50, and 200 day). The calendar is the daily US net of stocks
at a 52-week high minus stocks at a 52-week low. Every session is kept in
data/highs-lows.json and older days are never dropped.
"""

from __future__ import annotations

import json
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import websocket

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_PATH = DATA_DIR / "breadth.json"
HIGHS_PATH = DATA_DIR / "highs-lows.json"
SOCKET_URL = "wss://data.tradingview.com/socket.io/websocket"
HISTORY_BARS = 1000

MA_SYMBOLS = [
    ("5-day", "INDEX:S5FD"),
    ("20-day", "INDEX:S5TW"),
    ("50-day", "INDEX:S5FI"),
    ("200-day", "INDEX:S5TH"),
]
NET_SYMBOL = "INDEX:MADX"
HIGH_SYMBOL = "INDEX:MAHX"
LOW_SYMBOL = "INDEX:MALX"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
}

# Good Friday is not on a fixed weekday rule.
_GOOD_FRIDAY = {
    2024: date(2024, 3, 29),
    2025: date(2025, 4, 18),
    2026: date(2026, 4, 3),
    2027: date(2027, 3, 26),
    2028: date(2028, 4, 14),
    2029: date(2029, 3, 30),
    2030: date(2030, 4, 19),
    2031: date(2031, 4, 11),
    2032: date(2032, 3, 26),
}


def ma_bar_color(value: float) -> str:
    """Blue from 25% through 75%, black above 75%, red below 25%."""
    if value < 25:
        return "#dc2626"
    if value > 75:
        return "#111827"
    return "#3b82f6"


def _packet(message: str) -> str:
    return f"~m~{len(message)}~m~{message}"


def _send(sock: websocket.WebSocket, method: str, params: list[Any]) -> None:
    sock.send(_packet(json.dumps({"m": method, "p": params}, separators=(",", ":"))))


def _connect() -> websocket.WebSocket:
    return websocket.create_connection(
        SOCKET_URL,
        origin="https://www.tradingview.com",
        timeout=20,
        header=["User-Agent: " + HEADERS["User-Agent"]],
    )


def fetch_moving_averages() -> list[dict[str, Any]]:
    symbols = [symbol for _, symbol in MA_SYMBOLS]
    sock = _connect()
    session = "qs_" + "".join(random.choices(string.ascii_lowercase, k=10))
    try:
        _send(sock, "set_auth_token", ["unauthorized_user_token"])
        _send(sock, "quote_create_session", [session])
        _send(sock, "quote_set_fields", [session, "lp", "ch", "short_name"])
        _send(sock, "quote_add_symbols", [session, *symbols])
        found: dict[str, float] = {}
        while len(found) < len(symbols):
            raw = sock.recv()
            if isinstance(raw, bytes):
                raw = raw.decode()
            if raw.startswith("~h~"):
                sock.send(raw)
                continue
            for match_text in raw.split("~m~"):
                if '"lp"' not in match_text or not match_text.startswith("{"):
                    continue
                try:
                    message = json.loads(match_text)
                except json.JSONDecodeError:
                    continue
                if message.get("m") != "qsd":
                    continue
                body = message["p"][1]
                value = (body.get("v") or {}).get("lp")
                if value is not None and body.get("n"):
                    found[body["n"]] = float(value)
            if "critical_error" in raw:
                break
    finally:
        sock.close()
    missing = [symbol for symbol in symbols if symbol not in found]
    if missing:
        raise RuntimeError(f"Missing breadth quotes for {', '.join(missing)}")
    rows = []
    for label, symbol in MA_SYMBOLS:
        value = round(found[symbol], 1)
        rows.append(
            {
                "label": label,
                "value": value,
                "color": ma_bar_color(value),
                "symbol": symbol,
            }
        )
    return rows


def fetch_daily_closes(symbol: str, bars: int = HISTORY_BARS) -> dict[str, float]:
    """Daily closes keyed by session date (UTC date of the daily bar)."""
    sock = _connect()
    session = "cs_" + "".join(random.choices(string.ascii_lowercase, k=12))
    try:
        _send(sock, "set_auth_token", ["unauthorized_user_token"])
        _send(sock, "chart_create_session", [session, ""])
        payload = json.dumps(
            {"symbol": symbol, "adjustment": "splits", "session": "regular"},
            separators=(",", ":"),
        )
        _send(sock, "resolve_symbol", [session, "sym_0", "=" + payload])
        _send(sock, "create_series", [session, "sds_1", "s1", "sym_0", "1D", bars, ""])
        closes: dict[str, float] = {}
        deadline = datetime.now(timezone.utc).timestamp() + 25
        while datetime.now(timezone.utc).timestamp() < deadline:
            raw = sock.recv()
            if isinstance(raw, bytes):
                raw = raw.decode()
            if raw.startswith("~h~"):
                sock.send(raw)
                continue
            finished = False
            failed = None
            for part in raw.split("~m~"):
                part = part.strip()
                if not part.startswith("{"):
                    continue
                try:
                    message = json.loads(part)
                except json.JSONDecodeError:
                    continue
                kind = message.get("m")
                if kind in ("timescale_update", "du"):
                    body = (message["p"][1] or {}).get("sds_1") or {}
                    for bar in body.get("s") or []:
                        values = bar.get("v") or []
                        if len(values) >= 5 and values[4] is not None:
                            session_day = datetime.fromtimestamp(values[0], timezone.utc).date()
                            closes[session_day.isoformat()] = float(values[4])
                elif kind == "series_completed":
                    finished = True
                elif kind in ("symbol_error", "series_error", "critical_error"):
                    failed = message
                    finished = True
            if finished:
                if failed and not closes:
                    detail = failed.get("p", ["", "", "history unavailable"])[-1]
                    raise RuntimeError(f"{symbol}: {detail}")
                break
        else:
            if not closes:
                raise RuntimeError(f"{symbol}: timed out waiting for daily history")
    finally:
        sock.close()
    return closes


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2))
    temp.replace(path)


def _merge_days(
    existing: list[dict[str, Any]],
    nets: dict[str, float],
    highs: dict[str, float],
    lows: dict[str, float],
) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for row in existing:
        if isinstance(row, dict) and row.get("date"):
            by_date[str(row["date"])] = dict(row)
    for session_day, value in nets.items():
        row = by_date.setdefault(session_day, {"date": session_day})
        row["net"] = int(round(value))
        row["source"] = "tradingview"
    for session_day, value in highs.items():
        row = by_date.setdefault(session_day, {"date": session_day, "source": "tradingview"})
        row["highs"] = int(round(value))
    for session_day, value in lows.items():
        row = by_date.setdefault(session_day, {"date": session_day, "source": "tradingview"})
        row["lows"] = int(round(value))
    for row in by_date.values():
        if "net" not in row and "highs" in row and "lows" in row:
            row["net"] = int(row["highs"]) - int(row["lows"])
            row["source"] = row.get("source") or "tradingview"
    return [by_date[key] for key in sorted(by_date)]


def load_net_highs() -> dict[str, Any]:
    """Daily net new 52-week highs, merged into the permanent archive."""
    cached = _read_json(HIGHS_PATH) or {}
    existing = cached.get("days") if isinstance(cached.get("days"), list) else []
    symbols = {
        "net": NET_SYMBOL,
        "highs": HIGH_SYMBOL,
        "lows": LOW_SYMBOL,
    }
    fetched: dict[str, dict[str, float]] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch_daily_closes, symbol): key for key, symbol in symbols.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                fetched[key] = future.result()
            except Exception as exc:
                errors.append(str(exc))
    if not fetched.get("net") and not any(row.get("net") is not None for row in existing):
        raise RuntimeError("; ".join(errors) or "Net new highs are unavailable")
    days = _merge_days(
        existing,
        fetched.get("net") or {},
        fetched.get("highs") or {},
        fetched.get("lows") or {},
    )
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "series": "US net new 52-week highs",
        "netSymbol": NET_SYMBOL,
        "highsSymbol": HIGH_SYMBOL,
        "lowsSymbol": LOW_SYMBOL,
        "days": days,
    }
    if errors:
        payload["error"] = "; ".join(errors)
    if fetched.get("net"):
        _write_json(HIGHS_PATH, payload)
    elif existing:
        payload["days"] = existing
        payload["updatedAt"] = cached.get("updatedAt")
    return payload


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    shift = (weekday - first.weekday()) % 7
    return first + timedelta(days=shift + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    return cursor - timedelta(days=(cursor.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def nyse_holidays(year: int) -> set[date]:
    days = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _last_weekday(year, 5, 0),
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    friday = _GOOD_FRIDAY.get(year)
    if friday:
        days.add(friday)
    return days


def holiday_set(year: int) -> set[date]:
    found: set[date] = set()
    for offset in (-1, 0, 1):
        found |= nyse_holidays(year + offset)
    return found


def calendar_days(year: int, month: int) -> list[date]:
    """Sunday-first cells covering the month, including leading and trailing blanks."""
    first = date(year, month, 1)
    last = date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    end = last + timedelta(days=(5 - last.weekday()) % 7)
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _read_cache() -> dict[str, Any] | None:
    return _read_json(CACHE_PATH)


def _write_cache(payload: dict[str, Any]) -> None:
    _write_json(CACHE_PATH, payload)


def load_breadth() -> dict[str, Any]:
    """Current percent-above-average readings, falling back to the last save."""
    cached = _read_cache()
    try:
        averages = fetch_moving_averages()
    except Exception as exc:
        if cached and cached.get("averages"):
            cached["error"] = str(exc)
            return cached
        raise RuntimeError(str(exc)) from exc
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "averages": averages,
    }
    _write_cache(payload)
    return payload


if __name__ == "__main__":
    print(json.dumps({"breadth": load_breadth(), "days": len(load_net_highs()["days"])}, indent=2))
