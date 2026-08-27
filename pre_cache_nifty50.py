from app.mcp.providers.yfinance_provider import YFinanceProvider
import time

tickers = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", 
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "BAJFINANCE", "L&T", "ASIANPAINT", "HCLTECH", "AXISBANK",
    "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO",
    "CIPLA", "TATASTEEL", "POWERGRID", "M&M", "NTPC"
]

provider = YFinanceProvider()

for ticker in tickers:
    print(f"Fetching {ticker}...")
    try:
        s = provider.get_financial_statements(ticker)
        m = provider.get_market_data(ticker)
        if "error" in s:
            print(f"  statements error: {s['error']}")
        if "error" in m:
            print(f"  market error: {m['error']}")
        time.sleep(2)
    except Exception as e:
        print(f"  exception: {e}")
print("Done.")
