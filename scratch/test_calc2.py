from portfolio_tracker_calc import calc_data
from portfolio_tracker import _load_holdings
import json
usdkrw = 1350.0
usdkrw_tuple = (usdkrw, usdkrw)
holdings = _load_holdings()
accounts_data, _ = calc_data(holdings, usdkrw_tuple)
for acc, data in accounts_data.items():
    for row in data['rows']:
        if "Alphabet" in row['name']:
            print(row['name'], row['price'])
