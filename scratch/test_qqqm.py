import yfinance as yf
tk = yf.Ticker("QQQM")
print(tk.info.get("currentPrice"))
