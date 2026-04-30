import yfinance as yf
tk = yf.Ticker("QQQ")
info = tk.info
pre = info.get('preMarketPrice')
post = info.get('postMarketPrice')
reg = info.get('regularMarketPrice')
curr = None
if pre is not None:
    curr = float(pre)
elif post is not None:
    curr = float(post)
elif reg is not None:
    curr = float(reg)
print("Resolved curr:", curr, "| pre:", pre, "post:", post, "reg:", reg)
