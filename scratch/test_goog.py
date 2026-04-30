import yfinance as yf
tk = yf.Ticker("GOOGL")
info = tk.info
print("GOOGL postMarketPrice:", info.get('postMarketPrice'))
print("GOOGL preMarketPrice:", info.get('preMarketPrice'))
print("GOOGL regularMarketPrice:", info.get('regularMarketPrice'))
tk2 = yf.Ticker("GOOG")
info2 = tk2.info
print("GOOG postMarketPrice:", info2.get('postMarketPrice'))
print("GOOG preMarketPrice:", info2.get('preMarketPrice'))
print("GOOG regularMarketPrice:", info2.get('regularMarketPrice'))
