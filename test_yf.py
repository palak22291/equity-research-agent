import yfinance as yf
import requests

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})
stock = yf.Ticker("RELIANCE.NS", session=session)

print("Fetching info...")
try:
    info = stock.info
    print("info OK")
except Exception as e:
    print(f"info failed: {e}")

print("Fetching financials...")
try:
    fin = stock.financials
    print("financials OK")
except Exception as e:
    print(f"financials failed: {e}")
