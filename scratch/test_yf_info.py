import yfinance as yf
tk = yf.Ticker("QQQ")
info = tk.info
print("currentPrice:", info.get('currentPrice'))
print("regularMarketPrice:", info.get('regularMarketPrice'))
print("preMarketPrice:", info.get('preMarketPrice'))
print("postMarketPrice:", info.get('postMarketPrice'))
