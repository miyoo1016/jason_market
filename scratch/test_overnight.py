import yfinance as yf
info = yf.Ticker("GOOGL").info
print({k:v for k,v in info.items() if 'Market' in k or 'Price' in k or 'price' in k})
