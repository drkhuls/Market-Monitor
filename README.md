# Market Monitor

SPY and QQQ, the NAAIM Exposure Index, and the AAII Investor Sentiment Survey on one desk.

Charts open on the last three months, with empty space to the right of the latest candle so the most recent price is not jammed against the edge. The AAII block uses the same green, gray, and red bars as the survey page on AAII.com. The NAAIM table shows the last 12 months in a compact type size. Every week we have collected stays in a file after it ages off that table.

## Run

```bash
npm install
npm run dev
```

Then open [http://127.0.0.1:41731](http://127.0.0.1:41731).

The Thursday checks run while this server is up. If it is off when AAII publishes, the next start catches up.

## What is stored

- `data/naaim-history.json` — every NAAIM week collected from the public series, including quartiles and deviation. The table on screen is only the last 12 months.
- `data/aaii-history.json` — the AAII survey history from their spreadsheet, plus the weekly bar chart taken from the survey page.
- `data/poll-state.json` — when the AAII check last ran, and when it runs next.

AAII is read from AAII.com on Thursday at 10:00 AM Eastern. If that week's survey is not up yet, the monitor checks again every two hours until the new reading appears. NAAIM is refreshed on the same pass. Their public series is posted about three months after the survey.

Prices come from Yahoo Finance.
