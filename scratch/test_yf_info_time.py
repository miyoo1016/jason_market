import yfinance as yf
import time
start = time.time()
tk = yf.Ticker("QQQ")
print(tk.info.get('postMarketPrice'))
print("Time:", time.time() - start)
