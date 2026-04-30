"""포트폴리오 트래커 — 가격 조회 모듈
yfinance 병렬 조회, KRX 금현물, USDKRW 환율"""

import threading
import subprocess
import json
import logging
import warnings
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

# yfinance "possibly delisted" 경고 억제 (실제 상장폐지 아님, crumb 재시도로 처리)
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore', category=UserWarning, module='yfinance')


def _fetch_pyth_prices(tickers: list) -> dict:
    """Pyth Network API를 사용하여 US 주식의 실시간 오버나이트(Blue Ocean) 시세 조회"""
    results = {}
    if not tickers:
        return results
    
    try:
        # 1. 각 티커의 Overnight 피드 ID 찾기
        for t in tickers:
            try:
                # Pyth Search API (asset_type은 소문자 'equity'여야 함)
                search_url = f"https://hermes.pyth.network/v2/price_feeds?query={t}&asset_type=equity"
                r = requests.get(search_url, timeout=5)
                if r.status_code == 200:
                    feeds = r.json()
                    feed_id = None
                    
                    # 1순위: "OVERNIGHT"이 포함된 피드 찾기
                    for f in feeds:
                        attr = f.get('attributes', {})
                        base = attr.get('base', '').upper()
                        desc = attr.get('description', '').upper()
                        if base == t.upper() and 'OVERNIGHT' in desc:
                            feed_id = f.get('id')
                            break
                    
                    # 2순위: "OVERNIGHT"이 없으면 티커가 정확히 일치하는 첫 번째 피드 사용
                    if not feed_id:
                        for f in feeds:
                            attr = f.get('attributes', {})
                            base = attr.get('base', '').upper()
                            if base == t.upper():
                                feed_id = f.get('id')
                                break
                    
                    if feed_id:
                        # 2. 실시간 가격 조회
                        price_url = f"https://hermes.pyth.network/v2/updates/price/latest?ids[]={feed_id}"
                        pr = requests.get(price_url, timeout=5)
                        if pr.status_code == 200:
                            parsed = pr.json().get('parsed', [None])[0]
                            if parsed:
                                price_data = parsed.get('price', {})
                                price_raw = int(price_data.get('price', 0))
                                expo = int(price_data.get('expo', 0))
                                if price_raw > 0:
                                    price = price_raw * (10 ** expo)
                                    results[t] = price
            except Exception:
                continue
    except Exception:
        pass
    return results


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
    """yfinance cookies.db 삭제 → Invalid Crumb 방지 (macOS: ~/Library/Caches/py-yfinance)"""
    import os, shutil
    candidates = [
        os.path.join(os.path.expanduser('~/Library/Caches'), 'py-yfinance', 'cookies.db'),
        os.path.join(os.path.expanduser('~/.cache'), 'py-yfinance', 'cookies.db'),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    # yfinance 내부 캐시 API (버전별 시도)
    try:
        from yfinance.cache import get_cookie_cache
        get_cookie_cache().store('curlCffi', None)
    except Exception:
        pass


def fetch_all_prices(holdings: list, usdkrw: float) -> dict:
    """병렬로 모든 종목 현재가+전일종가 조회 (1일 손익용)"""
    _reset_yf_cookie()
    try:
        _ = yf.Ticker("SPY").info  # 동기적으로 쿠키/크럼브 1회 생성 (멀티스레딩 충돌 방지)
    except Exception:
        pass

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

    # 1. 미국 종목 조회 (순차적으로 진행하여 크럼브 충돌 방지 및 상세 정보 확보)
    if us_tickers:
        # (C) 주간거래(Day Market) 시간대라면 Pyth Network에서 오버나이트 시세 우선 조회
        # 한국 시간 09:00 ~ 17:00 사이인 경우
        kst_now = datetime.now(timezone(timedelta(hours=9)))
        is_day_market = 9 <= kst_now.hour < 17
        pyth_prices = {}
        if is_day_market:
            pyth_prices = _fetch_pyth_prices(us_tickers)

        for t in us_tickers:
            try:
                tk = yf.Ticker(t)
                curr, prev = None, None

                # (A) .info 에서 데이터 추출 (가장 상세함)
                try:
                    info = tk.info
                    prev = info.get('previousClose')
                    pre = info.get('preMarketPrice')
                    post = info.get('postMarketPrice')
                    reg = info.get('regularMarketPrice')
                    
                    # 현재 세션에 맞는 가격 선택 (포스트마켓 우선)
                    if post and post > 0:
                        curr = float(post)
                    elif pre and pre > 0:
                        curr = float(pre)
                    elif reg and reg > 0:
                        curr = float(reg)
                    
                    # 만약 .info의 가격이 regularMarketPrice와 같다면, 
                    # 혹시 모를 24시간 장(Overnight) 시세가 history에 있는지 확인
                    if curr == reg or not curr:
                        h1d = tk.history(period='1d', prepost=True)
                        if not h1d.empty:
                            hist_curr = float(h1d['Close'].iloc[-1])
                            if hist_curr and hist_curr != curr:
                                curr = hist_curr
                except Exception:
                    pass

                # (B) .info 실패 시 fast_info 및 history 보완
                if not curr:
                    try:
                        fi = tk.fast_info
                        curr = getattr(fi, 'last_price', None) or getattr(fi, 'lastPrice', None)
                        if not prev:
                            prev = getattr(fi, 'previous_close', None) or getattr(fi, 'previousClose', None)
                        
                        # 데이장 시세 확인을 위해 1d history 재확인
                        h1d = tk.history(period='1d', prepost=True)
                        if not h1d.empty:
                            curr = float(h1d['Close'].iloc[-1])
                    except Exception:
                        pass

                # (D) Pyth Network 오버나이트 시세가 있다면 최우선 적용 (주간거래 시간대 한정)
                if t in pyth_prices:
                    curr = pyth_prices[t]

                if curr:
                    _update_cache(t, float(curr), float(prev) if prev else None)
            except Exception:
                pass

    # 2. 한국 종목 및 금현물 조회 (병렬 가능)
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
                    valid_series = col.dropna()
                    if len(valid_series) >= 2:
                        _update_cache(t, float(valid_series.iloc[-1]), float(valid_series.iloc[-2]))
                    elif not valid_series.empty:
                        _update_cache(t, float(valid_series.iloc[-1]))
                except Exception:
                    pass
        except Exception:
            pass

    gold_result = {'curr': None, 'prev': None}
    def _gold():
        res = _fetch_gold_krx(usdkrw)
        gold_result.update(res)

    t_kr = threading.Thread(target=_fetch_kr, daemon=True)
    gt = threading.Thread(target=_gold, daemon=True)
    t_kr.start()
    gt.start()
    t_kr.join(timeout=20)
    gt.join(timeout=20)

    # 누락건 개별 재조회 (fast_info 우선, history 최소화)
    for t in tickers:
        if t not in cache or cache[t].get('prev') is None:
            try:
                tk = yf.Ticker(t)
                fi = tk.fast_info
                fb_curr = getattr(fi, 'last_price', None) or getattr(fi, 'lastPrice', None)
                fb_prev = getattr(fi, 'previous_close', None) or getattr(fi, 'previousClose', None)

                # 기존 cache에 curr이 있으면 보존 (데이장 시세 덮어쓰기 방지)
                existing_curr = cache.get(t, {}).get('curr')
                curr = existing_curr if existing_curr else fb_curr
                prev = cache.get(t, {}).get('prev') or fb_prev

                # fast_info 에서도 못 얻으면 2일 일봉 (가장 짧은 기간)
                if not prev or not curr:
                    try:
                        h = tk.history(period='2d')
                        if not h.empty:
                            if len(h) >= 2:
                                prev = prev or float(h['Close'].iloc[-2])
                                curr = curr or float(h['Close'].iloc[-1])
                            else:
                                curr = curr or float(h['Close'].iloc[-1])
                    except Exception:
                        pass

                if curr:
                    _update_cache(t, float(curr), float(prev) if prev else None)
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
