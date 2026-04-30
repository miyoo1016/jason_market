import yfinance as yf
tk = yf.Ticker("QQQ")
print("Fast info last_price:", tk.fast_info.last_price)
print("Fast info pre_market_price:", getattr(tk.fast_info, "pre_market_price", None), getattr(tk.fast_info, "preMarketPrice", None))
print("Fast info post_market_price:", getattr(tk.fast_info, "post_market_price", None), getattr(tk.fast_info, "postMarketPrice", None))
print("Market state:", getattr(tk.fast_info, "market_state", None))
h = tk.history(period='1d', interval='1m', prepost=True)
print("History 1m prepost:")
if not h.empty:
    print(h.tail(2))
else:
    print("Empty history")
