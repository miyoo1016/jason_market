import yfinance as yf
data = yf.download(["QQQ"], period="1d", interval="1m", prepost=True)
print(data.tail(2))
