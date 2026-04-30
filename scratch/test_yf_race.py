import yfinance as yf
import threading
from portfolio_tracker_prices import _reset_yf_cookie
_reset_yf_cookie()
def fetch(t):
    tk = yf.Ticker(t)
    print(t, tk.info.get('postMarketPrice'))
    print(t, tk.history(period="1d").empty)
threads = [threading.Thread(target=fetch, args=(t,)) for t in ["QQQM", "GOOGL"]]
for th in threads: th.start()
for th in threads: th.join()
