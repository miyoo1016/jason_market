import yfinance as yf
import pandas as pd
from datetime import datetime

tickers = ['QQQM', 'GOOGL']
print(f"Current KST: {datetime.now()}")

for t in tickers:
    print(f"\n--- Testing {t} ---")
    tk = yf.Ticker(t)
    
    # Check fast_info
    print("Fast Info:")
    try:
        fi = tk.fast_info
        print(f"  last_price: {fi.get('last_price')}")
        print(f"  previous_close: {fi.get('previous_close')}")
    except Exception as e:
        print(f"  Error: {e}")
        
    # Check download 1d 1m
    print("Download 1d 1m prepost:")
    try:
        d = yf.download(t, period='1d', interval='1m', prepost=True, progress=False)
        if not d.empty:
            print(f"  Last price: {d['Close'].iloc[-1]}")
            print(f"  Last time: {d.index[-1]}")
        else:
            print("  Empty data")
    except Exception as e:
        print(f"  Error: {e}")

    # Check download 2d 1m
    print("Download 2d 1m prepost:")
    try:
        d = yf.download(t, period='2d', interval='1m', prepost=True, progress=False)
        if not d.empty:
            print(f"  Last price: {d['Close'].iloc[-1]}")
            print(f"  Last time: {d.index[-1]}")
        else:
            print("  Empty data")
    except Exception as e:
        print(f"  Error: {e}")
