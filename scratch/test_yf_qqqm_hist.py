import yfinance as yf
import logging
# logging.getLogger('yfinance').setLevel(logging.CRITICAL)
tk = yf.Ticker("QQQM")
print(tk.history(period="1d", prepost=True))
