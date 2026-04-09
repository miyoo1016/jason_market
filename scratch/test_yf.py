import yfinance as yf
import pandas as pd

tickers = ["QQQM", "GOOGL"]
print(f"Testing yf.download for {tickers} with 1m interval...")
try:
    data = yf.download(tickers, period='1d', interval='1m', prepost=True)
    print("Columns:", data.columns)
    if not data.empty:
        print("Tail of Close:\n", data['Close'].tail())
    else:
        print("Data is empty!")
except Exception as e:
    print(f"Error in yf.download: {e}")

print("\nTesting yf.Ticker(...).history for QQQM...")
try:
    q = yf.Ticker("QQQM")
    h = q.history(period='2d')
    print("QQQM History:\n", h.tail())
except Exception as e:
    print(f"Error in yf.Ticker.history: {e}")
