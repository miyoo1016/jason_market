import yfinance as yf
tk = yf.Ticker("QQQM")
print(tk.history(period="5d"))
