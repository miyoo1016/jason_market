import requests

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'}
CBOE_URL = 'https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json'

for sym in ['NDX', '$NDX', 'SPX', 'QQQ']:
    try:
        resp = requests.get(CBOE_URL.format(sym=sym), headers=HEADERS, timeout=10)
        print(f"{sym}: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Price: {data.get('data', {}).get('current_price')}")
    except Exception as e:
        print(f"{sym} error: {e}")
