import yfinance as yf
import threading
import logging
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
from portfolio_tracker_prices import _reset_yf_cookie
_reset_yf_cookie()

# Sync fetch
_ = yf.Ticker("SPY").info

def fetch(t):
    tk = yf.Ticker(t)
    res = tk.info.get('postMarketPrice')
    print(f"{t}: {res}")

threads = [threading.Thread(target=fetch, args=(t,)) for t in ["QQQM", "GOOGL", "AAPL", "MSFT"]]
for th in threads: th.start()
for th in threads: th.join()
