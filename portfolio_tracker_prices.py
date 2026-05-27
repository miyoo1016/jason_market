"""포트폴리오 트래커 — 가격 조회 모듈
Yahoo Finance v8 curl 기반 (yfinance 완전 제거)
"""

import threading
import subprocess
import json
import logging
import os

from jm_lib.yf_helpers import get_price_data, _chart

logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ═══ 환율 ═══

def get_usdkrw() -> tuple:
    """실시간 환율 + 전일종가 → (현재, 전일)"""
    try:
        data = get_price_data('USDKRW=X', is_global=True)
        if data and data.get('curr'):
            curr = float(data['curr'])
            prev = float(data.get('prev') or curr)
            return curr, prev
    except Exception:
        pass
    return 1450.0, 1450.0


# ═══ KRX 금현물 ═══

def _fetch_gold_krx(usdkrw: float) -> dict:
    """KRX 금현물 — 네이버 증권 API (M04020000, 한국거래소 공식)"""
    res = {'curr': None, 'prev': None}

    def _num(v):
        try:
            return float(str(v).replace(',', '').strip())
        except Exception:
            return None

    try:
        r = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0',
             'https://api.stock.naver.com/marketindex/metals/M04020000'],
            capture_output=True, timeout=10
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        price_str = d.get('closePrice') or d.get('currentPrice') or ''
        price = _num(price_str)
        if price and price > 0:
            res['curr'] = price
            prev = None
            for item in d.get('marketIndexTotalInfos') or []:
                if item.get('code') == 'lastClosePrice':
                    prev = _num(item.get('value'))
                    break
            if not prev:
                diff = _num(d.get('fluctuations')) or 0
                prev = price - diff
            if prev and prev > 0:
                res['prev'] = prev
            if os.environ.get('JM_DEBUG_PRICE') == '1':
                print(
                    "PRICE_DIAG "
                    f"symbol=GOLD_KRX selected_price={res['curr']} "
                    f"prev_close={res['prev']} source=naver_krx_gold"
                )
            return res
    except Exception:
        pass

    # fallback: GC=F curl
    try:
        r2 = _chart('GC=F')
        if r2:
            meta = r2.get('meta', {})
            gc_curr = meta.get('regularMarketPrice')
            gc_prev = meta.get('chartPreviousClose') or meta.get('previousClose')
            if gc_curr and usdkrw:
                res['curr'] = round(float(gc_curr) * usdkrw / 31.1035, 0)
                if gc_prev:
                    res['prev'] = round(float(gc_prev) * usdkrw / 31.1035, 0)
                return res
    except Exception:
        pass

    return res


# ═══ 전체 가격 조회 ═══

def fetch_all_prices(holdings: list, usdkrw: float) -> dict:
    """병렬로 모든 종목 현재가+전일종가 조회"""
    tickers = set()
    for h in holdings:
        t = h.get('ticker', '')
        if t and t not in ('CASH', 'GOLD_KRX', ''):
            tickers.add(t)

    cache = {}  # ticker -> {'curr': float, 'prev': float}
    lock = threading.Lock()

    def _store(t, curr, prev, meta=None):
        if curr is None:
            return
        with lock:
            cache[t] = {'curr': float(curr), 'prev': float(prev) if prev else float(curr)}
            if meta:
                cache[t]['price_diag'] = meta

    def _fetch_one(t):
        try:
            is_kr = t.endswith('.KS') or t.startswith('^KS')
            data = get_price_data(t, is_global=False)
            if data and data.get('curr'):
                diag = {
                    'symbol': data.get('symbol', t),
                    'selected_price': data.get('selected_price', data.get('curr')),
                    'selected_field': data.get('selected_field'),
                    'market_state': data.get('market_state'),
                    'source': data.get('source'),
                    'quote_time': data.get('quote_time'),
                    'overnight_price_supported': data.get('overnight_price_supported'),
                    'overnight_warning': data.get('overnight_warning'),
                    'last_extended_price': data.get('last_extended_price'),
                    'last_extended_timestamp': data.get('last_extended_timestamp'),
                    'last_extended_age_sec': data.get('last_extended_age_sec'),
                }
                _store(t, data['curr'], data.get('prev'), diag)
                if os.environ.get('JM_DEBUG_PRICE') == '1':
                    print(
                        "PRICE_DIAG "
                        f"symbol={diag['symbol']} "
                        f"selected_price={diag['selected_price']} "
                        f"selected_field={diag['selected_field']} "
                        f"market_state={diag['market_state']} "
                        f"source={diag['source']} "
                        f"quote_time={diag['quote_time']} "
                        f"overnight_price_supported={diag['overnight_price_supported']} "
                        f"overnight_warning={diag['overnight_warning']} "
                        f"last_extended_price={diag['last_extended_price']} "
                        f"last_extended_timestamp={diag['last_extended_timestamp']} "
                        f"last_extended_age_sec={diag['last_extended_age_sec']}"
                    )
        except Exception:
            pass

    # 병렬 스레드로 모든 티커 조회
    threads = [threading.Thread(target=_fetch_one, args=(t,), daemon=True) for t in tickers]
    for th in threads:
        th.start()

    gold_result = {'curr': None, 'prev': None}
    def _gold():
        res = _fetch_gold_krx(usdkrw)
        gold_result.update(res)

    gt = threading.Thread(target=_gold, daemon=True)
    gt.start()

    for th in threads:
        th.join(timeout=20)
    gt.join(timeout=20)

    cache['GOLD_KRX_PRICE'] = gold_result
    return cache


# ═══ 단일 종목 가격 ═══

def get_price(h: dict, price_cache: dict, usdkrw: float) -> tuple:
    """단일 종목 가격 조회 → (현재가, 전일종가)"""
    ticker = h.get('ticker', '')
    if ticker == 'CASH':
        return None, None

    if ticker == 'GOLD_KRX':
        data = price_cache.get('GOLD_KRX_PRICE', {})
    else:
        data = price_cache.get(ticker, {})

    curr = data.get('curr')
    prev = data.get('prev')

    if curr is None or curr != curr:
        curr = h.get('xlsx_price')

    return curr, prev


__all__ = [
    'get_usdkrw',
    'fetch_all_prices',
    'get_price',
]
