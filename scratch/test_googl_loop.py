import yfinance as yf
for i in range(5):
    tk = yf.Ticker("GOOGL")
    info = tk.info
    print(i, info.get('postMarketPrice'), info.get('regularMarketPrice'))
