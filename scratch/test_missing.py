from portfolio_tracker_prices import fetch_all_prices
import yfinance as yf
usdkrw = 1350.0
holdings = [{'ticker': 'GOOGL'}, {'ticker': 'QQQM'}]
cache = fetch_all_prices(holdings, usdkrw)
print(cache)
