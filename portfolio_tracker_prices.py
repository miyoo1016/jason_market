"""포트폴리오 트래커 — 가격 조회 모듈
yfinance 병렬 조회, KRX 금현물, USDKRW 환율"""

import threading
import subprocess
import json
import yfinance as yf
from datetime import datetime, timezone


def _fetch_gold_krx(usdkrw: float) -> dict:
    """KRX 금현물 — 네이버 모바일 증권 API (한국거래소 공식, M04020000)"""
    res = {'curr': None, 'prev': None}
    try:
        r = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0',
             'https://api.stock.naver.com/marketindex/metals/M04020000'],
            capture_output=True, timeout=10
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        price_str = d.get('closePrice') or d.get('currentPrice') or ''
        price = float(price_str.replace(',', ''))
        if price > 0:
            res['curr'] = price
            # 네이버 API에서 전일비(compare)를 통해 전일종가 유추
            diff = float(str(d.get('compareToPreviousPrice', '0')).replace(',', ''))
            sign = 1 if d.get('fluctuationCode') in ('1', '2') else -1
            if d.get('fluctuationCode') == '3':
                sign = 0
            res['prev'] = price - (diff * sign)
            return res
    except Exception:
        pass
    # fallback: GC=F 계산
    try:
        gc = yf.Ticker('GC=F').history(period='5d')
        if len(gc) >= 2:
            res['curr'] = round(float(gc['Close'].iloc[-1]) * usdkrw / 31.1035, 0)
            res['prev'] = round(float(gc['Close'].iloc[-2]) * usdkrw / 31.1035, 0)
            return res
    except Exception:
        pass
    return res


def get_usdkrw() -> tuple:
    """실시간 환율(FastInfo) 및 전일 종가 조회 → (현재, 전일)"""
    try:
        tk = yf.Ticker('USDKRW=X')
        # 1. 실시간 가격 (FastInfo)
        curr = tk.fast_info.get('last_price') or tk.fast_info.get('lastPrice')

        # 2. 전일 종가 및 백업 데이터 (History)
        h = tk.history(period='3d')
        if not h.empty:
            if not curr:
                curr = h['Close'].iloc[-1]
            if len(h) >= 2:
                prev = h['Close'].iloc[-2]
            else:
                prev = h['Close'].iloc[-1]
        else:
            prev = curr or 1450.0

        return float(curr or 1450.0), float(prev or 1450.0)
    except Exception:
        return 1450.0, 1450.0


def _reset_yf_cookie():
    """yfinance 쿠키 캐시 초기화 — s키 동기화 후 Invalid Crumb 방지"""
    try:
        from yfinance.cache import get_cookie_cache
        get_cookie_cache().store('curlCffi', None)
    except Exception:
        pass


def fetch_all_prices(holdings: list, usdkrw: float) -> dict:
    """병렬로 모든 종목 현재가+전일종가 조회 (1일 손익용)"""
    _reset_yf_cookie()
    tickers = set()
    for h in holdings:
        t = h.get('ticker', '')
        if t and t not in ('CASH', 'GOLD_KRX', ''):
            tickers.add(t)

    cache = {}  # ticker -> {'curr': float, 'prev': float}

    us_tickers = [t for t in tickers if not t.endswith('.KS') and '^KS' not in t]
    kr_tickers = [t for t in tickers if t.endswith('.KS') or '^KS' in t]

    def _update_cache(t, curr, prev=None):
        if curr != curr:
            return
        if t not in cache:
            cache[t] = {'curr': curr, 'prev': prev}
        else:
            if curr:
                cache[t]['curr'] = curr
            if prev:
                cache[t]['prev'] = prev

    def _fetch_us():
        if not us_tickers:
            return

        # 1. 분봉 데이터 수집 (현재 세션 최우선)
        try:
            data = yf.download(us_tickers, period='1d', interval='1m',
                               prepost=True, auto_adjust=True, progress=False, threads=True)
            closes = data['Close'] if 'Close' in data else data
            for t in us_tickers:
                try:
                    col = closes[t] if hasattr(closes, 'columns') and t in closes.columns else closes
                    valid = col.dropna()
                    if not valid.empty:
                        _update_cache(t, float(valid.iloc[-1]))
                except Exception:
                    pass
        except Exception:
            pass

        # 2. 개별 Ticker 속성으로 보강 (프리/애프터마켓 가격 직접 확인)
        def _fetch_single_info(t):
            try:
                tk = yf.Ticker(t)
                info = tk.info
                live_price = (
                    info.get('preMarketPrice') or
                    info.get('regularMarketPrice') or
                    info.get('postMarketPrice')
                )
                prev = info.get('regularMarketPreviousClose') or info.get('previousClose')

                # 인베스팅닷컴 동기화 보정: 글로벌 자산은 00:00 UTC 기준 % 계산
                is_global = t in ('GC=F', 'CL=F', 'BZ=F', 'USDKRW=X', 'BTC-USD',
                                  'DIA', 'SPY', 'QQQM', 'IWM', '^VIX', '^TNX')
                if is_global:
                    try:
                        h_int = tk.history(period='2d', interval='1h')
                        if not h_int.empty:
                            h_int.index = h_int.index.tz_convert('UTC')
                            today_utc = datetime.now(timezone.utc).replace(
                                hour=0, minute=0, second=0, microsecond=0)
                            today_data = h_int.loc[h_int.index >= today_utc]
                            if not today_data.empty:
                                prev = float(today_data['Open'].iloc[0])
                    except Exception:
                        pass

                if live_price:
                    _update_cache(t, float(live_price), float(prev) if prev else None)
            except Exception:
                pass

        # 병렬로 상세 정보 조회
        info_threads = [threading.Thread(target=_fetch_single_info, args=(t,), daemon=True)
                        for t in us_tickers]
        for th in info_threads:
            th.start()
        for th in info_threads:
            th.join(timeout=5)

    def _fetch_kr():
        if not kr_tickers:
            return
        try:
            data = yf.download(kr_tickers, period='5d', auto_adjust=True,
                               progress=False, threads=True)
            closes = data['Close'] if 'Close' in data else data
            for t in kr_tickers:
                try:
                    col = closes[t] if hasattr(closes, 'columns') and t in closes.columns else closes
                    valid = col.dropna()
                    if len(valid) >= 2:
                        _update_cache(t, float(valid.iloc[-1]), float(valid.iloc[-2]))
                    elif not valid.empty:
                        _update_cache(t, float(valid.iloc[-1]))
                except Exception:
                    pass
        except Exception:
            pass

    # GOLD_KRX 병렬 조회
    gold_result = {'curr': None, 'prev': None}

    def _gold():
        res = _fetch_gold_krx(usdkrw)
        gold_result.update(res)

    t_us = threading.Thread(target=_fetch_us, daemon=True)
    t_kr = threading.Thread(target=_fetch_kr, daemon=True)
    gt = threading.Thread(target=_gold, daemon=True)
    t_us.start()
    t_kr.start()
    gt.start()
    t_us.join(timeout=30)
    t_kr.join(timeout=30)
    gt.join(timeout=30)

    # 누락건 개별 재조회
    for t in tickers:
        if t not in cache or cache[t].get('prev') is None:
            try:
                tk = yf.Ticker(t)
                fi = tk.fast_info
                curr = getattr(fi, 'last_price', None)
                if not curr and hasattr(fi, 'get'):
                    curr = fi.get('lastPrice') or fi.get('last_price')

                prev = getattr(fi, 'previous_close', None)
                if not prev and hasattr(fi, 'get'):
                    prev = fi.get('previousClose') or fi.get('previous_close')

                if not prev:
                    h = tk.history(period='5d')
                    if len(h) >= 2:
                        prev = float(h['Close'].iloc[-2])
                        if not curr:
                            curr = float(h['Close'].iloc[-1])
                _update_cache(t, float(curr) if curr else None,
                              float(prev) if prev else None)
            except Exception:
                pass

    cache['GOLD_KRX_PRICE'] = gold_result
    return cache


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
