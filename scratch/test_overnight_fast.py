import yfinance as yf
fi = yf.Ticker("GOOG").fast_info
print(fi.last_price)
print(fi.previous_close)
