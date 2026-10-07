# Market Monitor

Daily trend check for SPY and QQQ, a live watchlist, market breadth, industry leadership, the NAAIM Exposure Index, and the AAII Investor Sentiment Survey.

Prices for SPY, QQQ, the watchlist, and the sector ETFs come from Yahoo Finance. The latest daily bar is the current session, so the 1-day industry chart moves through the day. Yahoo is usually about 15 minutes behind the tape.

The percent of S&P 500 stocks above the 5, 20, 50, and 200 day averages comes from TradingView. Bars are blue from 25% through 75%, black above 75%, and red below 25%.

The calendar is US net new 52-week highs: stocks at a 52-week high minus stocks at a 52-week low. Positive days are green and negative days are red. Market holidays on weekdays are marked closed. Every session stays in `data/highs-lows.json`.

Charts open on the last three months. Empty space sits to the right of the latest candle so the most recent price is not jammed against the edge. The 10 EMA is red and the 20 EMA is blue. Trend badges stay: uptrend, downtrend, or use caution.

The NAAIM card is the current StockCharts reading, with the euphoria / neutral / panic badge. The table under it lists the last 12 months in a smaller type size. Weeks older than a year leave the table and stay in `data/naaim-history.json` and `data/sentiment_data.csv`.

The AAII block copies the survey page: green bullish, gray neutral, red bearish, recent weeks stacked above the historical view. AAII.com is checked on Thursday at 10:00 AM Eastern. If that week's survey is not up yet, the monitor checks again every two hours.

## Run

```bash
cd market-monitor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## What is stored

- `data/watchlist.json` — sidebar tickers. Add, replace, remove, or reset.
- `data/sentiment_data.csv` — NAAIM readings from StockCharts, including a manual override.
- `data/naaim-history.json` — the public NAAIM series, kept after it ages off the one-year table.
- `data/aaii-history.json` — every AAII week from their spreadsheet, plus the bar chart copied from the survey page.
- `data/aaii-poll.json` — when the AAII check last ran, and when it runs next.
- `data/highs-lows.json` — every daily US net new 52-week high, with the high and low counts. Old days stay in the file.
- `data/breadth.json` — the last percent-above-average reading, used if the live quote is down.
