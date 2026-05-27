#!/usr/bin/env python3
"""지지/저항 레벨 분析 - Jason Market"""

import os, webbrowser, tempfile
import ast
import requests
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from xlsx_sync import load_portfolio as _load_pf
from jm_lib.colors import ALERT, AMBER, CYAN, RESET, GREEN, RED, WARN


EXTREME = ['극도공포','극도탐욕','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

PROXY_MAP = {
    'KODEX 나스닥100': 'QQQ',
    'KODEX S&P500':   'SPY',
    'KODEX 미국반도체': 'SOXX',
}

def _asset_type(ticker, name=''):
    if 'CD금리' in name or ticker == '357870.KS':
        return 'cash_like'
    if ticker == 'USDKRW=X' or ticker.endswith('=X'):
        return 'macro_fx'
    if ticker == '^TNX':
        return 'macro_rate'
    if ticker == '^VIX':
        return 'volatility_index'
    if ticker == 'BTC-USD':
        return 'crypto'
    if ticker in ('GC=F', 'BZ=F', 'CL=F'):
        return 'commodity'
    if ticker.startswith('^') or ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
        return 'index_or_futures'
    return 'equity_or_etf'

def _is_macro(asset_type):
    return asset_type in ('macro_fx', 'macro_rate', 'volatility_index')

def _is_limited_asset(asset_type):
    return asset_type == 'cash_like'

def _data_warnings(name, ticker, hist, curr, prev_close):
    warnings = []
    try:
        if curr is None or prev_close is None or curr <= 0 or prev_close <= 0:
            return ['DATA_INVALID: current/close 없음 또는 0 이하']
        if np.isnan(curr) or np.isnan(prev_close):
            return ['DATA_INVALID: current/close 없음 또는 0 이하']
        if abs((curr - prev_close) / prev_close * 100) >= 20:
            warnings.append('DATA_CHECK: 최근 등락률 ±20% 이상')
        med60 = float(hist['Close'].tail(60).median())
        if med60 <= 0 or np.isnan(med60):
            warnings.append('DATA_INVALID: 60일 중앙값 계산 불가')
        elif curr >= med60 * 2 or curr <= med60 * 0.5:
            warnings.append('DATA_CHECK: 현재가가 60일 중앙값 대비 2배/0.5배 범위 밖')
        if ticker == '^KS11' and (curr >= 20000 or curr <= 500):
            warnings.append('DATA_CHECK: 코스피 지수 통상 범위 이탈')
        if ticker == '005930.KS' and (curr >= 1000000 or curr <= 10000):
            warnings.append('DATA_CHECK: 삼성전자 통상 범위 이탈')
    except Exception as e:
        warnings.append(f'DATA_CHECK: 검증 실패({e})')
    return warnings

def _naver_symbol(ticker):
    if ticker == '^KS11':
        return 'KOSPI'
    if ticker and ticker.endswith('.KS'):
        code = ticker.split('.')[0]
        return code if len(code) == 6 and code.isdigit() else None
    return None

def _fetch_naver_daily(ticker):
    symbol = _naver_symbol(ticker)
    if not symbol:
        return None
    try:
        end = datetime.now()
        start = end - timedelta(days=730)
        resp = requests.get(
            'https://api.finance.naver.com/siseJson.naver',
            params={
                'symbol': symbol,
                'requestType': 1,
                'startTime': start.strftime('%Y%m%d'),
                'endTime': end.strftime('%Y%m%d'),
                'timeframe': 'day',
            },
            timeout=4,
        )
        resp.raise_for_status()
        rows = ast.literal_eval(resp.text.strip())
        if not rows or len(rows) < 121:
            return None
        data = rows[1:]
        df = pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Etc'])
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d', errors='coerce')
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['Date', 'Open', 'High', 'Low', 'Close'])
        if len(df) < 120 or (df[['Open', 'High', 'Low', 'Close']] <= 0).any().any():
            return None
        df = df.sort_values('Date').set_index('Date')
        return df
    except Exception:
        return None

def _build_assets():
    assets = {}
    seen = set()
    try:
        holdings = _load_pf()
        for h in holdings:
            if h.get('is_cash') or h.get('ticker') == 'CASH':
                continue
            ticker = h['ticker']
            name   = h['name']
            if ticker == 'XLSX_PRICE':
                ticker = PROXY_MAP.get(name, 'SPY')
            elif ticker == 'GOLD_KRX':
                ticker = 'GC=F'
                name = '금선물(COMEX)'
            elif ticker == 'GC=F' and '금현물' in name:
                name = '금선물(COMEX)'
            if ticker and ticker not in seen:
                seen.add(ticker)
                assets[f'{name:<10}'] = (ticker, _asset_type(ticker, name))
    except Exception:
        pass

    market = {
        'Bitcoin    ': ('BTC-USD',   'crypto'),
        '금(COMEX선물) ': ('GC=F',      'commodity'),
        '브렌트유(ICE) ': ('BZ=F',      'commodity'),
        'WTI원유(NYMEX)': ('CL=F',      'commodity'),
        '다우지수(CME선물)': ('YM=F',      'index_or_futures'),
        'S&P500(CME선물)': ('ES=F',      'index_or_futures'),
        '나스닥100(CME선물)': ('NQ=F',      'index_or_futures'),
        '러셀2000(CME선물)': ('RTY=F',     'index_or_futures'),
        '코스피      ': ('^KS11',    'index_or_futures'),
        '달러/원    ': ('USDKRW=X', 'macro_fx'),
        '미국 10년물 국채': ('^TNX',     'macro_rate'),
        'VIX(현물)   ': ('^VIX',     'volatility_index'),
    }
    for k, (v, at) in market.items():
        if v not in seen:
            seen.add(v)
            assets[k] = (v, at)
    return assets

ASSETS = _build_assets()

def fmt_level(price, asset_type):
    if asset_type == 'crypto': return f"${price:>12,.0f}"
    if asset_type == 'commodity': return f"${price:>12,.1f}"
    if asset_type == 'index_or_futures': return f"{price:>12,.1f}"
    if asset_type == 'macro_fx': return f"₩{price:>12,.1f}"
    if asset_type in ('macro_rate', 'volatility_index'): return f"{price:>12,.2f}"
    if asset_type in ('cash_like', 'equity_or_etf') and price >= 1000: return f"₩{price:>12,.0f}"
    return f"${price:>12,.2f}"

def _mk_fmt(at):
    """HTML용 간결 포맷 함수 반환"""
    def fmt(v):
        if at == 'crypto': return f"${v:,.0f}"
        if at == 'commodity': return f"${v:,.1f}"
        if at == 'index_or_futures': return f"{v:,.1f}"
        if at == 'macro_fx': return f"₩{v:,.1f}"
        if at in ('macro_rate', 'volatility_index'): return f"{v:,.2f}"
        if at in ('cash_like', 'equity_or_etf') and v >= 1000: return f"₩{v:,.0f}"
        return f"${v:,.2f}"
    return fmt

def find_pivot_highs(high, window=10):
    pivots = []
    for i in range(window, len(high) - window):
        if high[i] == max(high[i - window: i + window + 1]):
            pivots.append(high[i])
    return pivots

def find_pivot_lows(low, window=10):
    pivots = []
    for i in range(window, len(low) - window):
        if low[i] == min(low[i - window: i + window + 1]):
            pivots.append(low[i])
    return pivots

def count_touches(prices_array, level, tolerance_pct=0.015, lookback=252):
    """주어진 레벨에 가격이 근접한 횟수를 계산"""
    arr = prices_array[-lookback:] if len(prices_array) > lookback else prices_array
    count = 0
    for p in arr:
        if abs(p - level) / max(level, 1e-9) <= tolerance_pct:
            count += 1
    return count

def rate_strength(touch_count, recency_score):
    """터치 횟수와 최근성으로 레벨 강도 평가. Returns (stars: int, label: str)"""
    if touch_count >= 6 or (touch_count >= 4 and recency_score >= 0.7):
        return 3, '★★★'
    if touch_count >= 3 and recency_score >= 0.3:
        return 2, '★★'
    return 1, '★'

def find_round_numbers(curr, pct_range=0.15):
    """심리적 라운드 넘버 찾기. Returns (above_curr list, below_curr list)"""
    lo = curr * (1 - pct_range)
    hi = curr * (1 + pct_range)
    if curr >= 100000:       # 한국 고가주 (삼성전자 등)
        steps = [10000, 50000]
    elif curr >= 10000:      # 한국 중가주, 나스닥 선물 등
        steps = [1000, 5000]
    elif curr >= 1000:       # USD/KRW 환율, S&P 선물 등
        steps = [50, 100]
    elif curr >= 100:        # SPY, QQQ, 해외 ETF
        steps = [10, 25, 50]
    elif curr >= 10:
        steps = [5, 10]
    else:
        steps = [0.5, 1]
    candidates = set()
    for step in steps:
        start = int(lo / step) * step
        val = start
        while val <= hi * 1.01:
            if abs(val - curr) / max(curr, 1e-9) > 0.001:
                candidates.add(round(val, 4))
            val = round(val + step, 4)
    above = sorted([v for v in candidates if v > curr])
    below = sorted([v for v in candidates if v < curr], reverse=True)
    return above, below

def _near_observation_lines(curr, high_52w, low_52w, round_res, round_sup):
    upper = []
    lower = []
    if high_52w and not np.isnan(high_52w) and high_52w > curr:
        pct = nearest_pct(curr, high_52w)
        target = upper if abs(pct) <= 5 else None
        if target is not None:
            target.append({'label': '52주 고점', 'price': high_52w, 'pct': pct})
    if low_52w and not np.isnan(low_52w) and low_52w < curr:
        pct = nearest_pct(curr, low_52w)
        target = lower if abs(pct) <= 5 else None
        if target is not None:
            target.append({'label': '52주 저점', 'price': low_52w, 'pct': pct})
    for v in (round_res or []):
        pct = nearest_pct(curr, v)
        if 0 <= pct <= 5:
            upper.append({'label': '심리 가격대', 'price': v, 'pct': pct})
    for v in (round_sup or []):
        pct = nearest_pct(curr, v)
        if -5 <= pct <= 0:
            lower.append({'label': '심리 가격대', 'price': v, 'pct': pct})

    def dedupe(items):
        out = []
        seen = set()
        for item in items:
            key = round(item['price'], 4)
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    upper = sorted(dedupe(upper), key=lambda x: x['pct'])[:4]
    lower = sorted(dedupe(lower), key=lambda x: abs(x['pct']))[:4]
    return upper, lower

def _long_reference_lines(curr, high_52w, low_52w):
    upper = []
    lower = []
    if high_52w and not np.isnan(high_52w) and high_52w > curr:
        pct = nearest_pct(curr, high_52w)
        if abs(pct) > 5:
            upper.append({'label': '52주 고점', 'price': high_52w, 'pct': pct})
    if low_52w and not np.isnan(low_52w) and low_52w < curr:
        pct = nearest_pct(curr, low_52w)
        if abs(pct) > 5:
            lower.append({'label': '52주 저점', 'price': low_52w, 'pct': pct})
    return upper[:1], lower[:1]

def _obs_parts(items, fmt, sign=True):
    if not items:
        return ['N/A']
    parts = []
    for item in items:
        pct = item['pct']
        pct_s = f"{pct:+.1f}%" if sign else f"{pct:.1f}%"
        parts.append(f"{item['label']} {fmt(item['price'])} ({pct_s})")
    return parts

def _obs_text(items, fmt, sign=True):
    return ', '.join(_obs_parts(items, fmt, sign))

def _obs_lines(items, fmt, indent='      '):
    return '\n'.join(f"{indent}- {part}" for part in _obs_parts(items, fmt))

def _obs_html_lines(items, fmt, cls):
    if not items:
        return '<div><span class="rl-badge muted">N/A</span></div>'
    return ''.join(
        f'<div class="obs-line"><span class="rl-badge {cls}">{item["label"]} {fmt(item["price"])} ({item["pct"]:+.1f}%)</span></div>'
        for item in items
    )

def _obs_html(items, fmt, cls):
    if not items:
        return '<span class="rl-badge muted">N/A</span>'
    parts = []
    for item in items:
        pct = item['pct']
        parts.append(
            f'<span class="rl-badge {cls}">{item["label"]} {fmt(item["price"])} ({pct:+.1f}%)</span>'
        )
    return ''.join(parts)

def _fmt_optional(fmt, value):
    return fmt(value) if value is not None else 'N/A'

def _source_text(r):
    text = r.get('data_source', 'yfinance')
    if r.get('source_note'):
        text += f" ({r['source_note']})"
    return text

SCALE_CHECK_MESSAGE = '시계열 스케일 점검: 현재가 대비 52주 저점/MA200이 과도하게 낮아 장기 지지선 해석 신뢰 제한'

def _series_scale_check(ticker, curr, low_52w, ma200):
    if ticker not in ('005930.KS', '^KS11'):
        return False
    try:
        if curr is None or curr <= 0:
            return False
        low_ratio = low_52w / curr if low_52w is not None and not np.isnan(low_52w) else 1
        ma200_pct = nearest_pct(curr, ma200) if ma200 is not None and not np.isnan(ma200) else 0
        return low_ratio <= 0.70 or ma200_pct <= -45
    except Exception:
        return False

def _ma(series, window):
    if len(series) < window:
        return None
    val = float(series.tail(window).mean())
    return None if np.isnan(val) else val

def _ma_side(curr, ma):
    if ma is None or curr is None:
        return 'N/A'
    return '위' if curr >= ma else '아래'

def _calc_atr_pct(hist, window=14):
    if len(hist) < window + 1:
        return None
    high = hist['High']
    low = hist['Low']
    close = hist['Close']
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr = float(tr.tail(window).mean())
    last_close = float(close.iloc[-1])
    if last_close <= 0 or np.isnan(atr):
        return None
    return atr / last_close * 100

def _avg_range_pct(hist, window=20):
    if len(hist) < window:
        return None
    close = hist['Close'].replace(0, np.nan)
    rng = ((hist['High'] - hist['Low']).abs() / close * 100).tail(window)
    val = float(rng.mean())
    return None if np.isnan(val) else val

def _trend_info(hist, curr, asset_type, ticker):
    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    ma20 = _ma(close, 20)
    ma50 = _ma(close, 50)
    ma60 = _ma(close, 60)
    ma120 = _ma(close, 120)
    ma200 = _ma(close, 200)

    if ma50 is None or ma200 is None or len(hist) < 80:
        status = '판단 제한'
        flow = '최근 고점/저점 흐름 데이터 부족'
    else:
        recent_high = float(high.tail(20).max())
        prev_high = float(high.iloc[-40:-20].max())
        recent_low = float(low.tail(20).min())
        prev_low = float(low.iloc[-40:-20].min())
        highs_up = recent_high >= prev_high
        lows_up = recent_low >= prev_low
        highs_down = recent_high <= prev_high
        lows_down = recent_low <= prev_low
        flow = (
            f"최근 고점 {'상승' if highs_up else '하락'} / "
            f"최근 저점 {'상승' if lows_up else '하락'}"
        )
        if curr > ma50 > ma200 and highs_up and lows_up:
            status = '상승추세'
        elif curr < ma50 < ma200 and highs_down and lows_down:
            status = '하락추세'
        elif curr > ma50 and ma50 < ma200 and (highs_up or lows_up):
            status = '반전 시도'
        elif curr < ma50 and ma50 > ma200 and (highs_down or lows_down):
            status = '반전 시도'
        else:
            status = '횡보'

    if ma50 is not None and ma200 is not None:
        long_term = '중장기 우호' if ma50 > ma200 else '중장기 부담' if ma50 < ma200 else '중장기 중립'
    else:
        long_term = '판단 제한'

    kr_ma = ''
    if ticker.endswith('.KS') and ma20 is not None and ma60 is not None and ma120 is not None:
        kr_ma = (
            f"MA20 {_ma_side(curr, ma20)} / MA60 {_ma_side(curr, ma60)} / "
            f"MA120 {_ma_side(curr, ma120)} / MA200 {_ma_side(curr, ma200)}"
        )

    return {
        'status': status,
        'basis': '50일선, 200일선, 최근 고점/저점 흐름',
        'flow': flow,
        'ma20': ma20,
        'ma50': ma50,
        'ma60': ma60,
        'ma120': ma120,
        'ma200': ma200,
        'ma50_side': _ma_side(curr, ma50),
        'ma200_side': _ma_side(curr, ma200),
        'long_term': long_term,
        'kr_ma': kr_ma,
    }

def _box_info(hist, curr):
    recent = hist.tail(60)
    if len(recent) < 20:
        return {'box_high': None, 'box_low': None, 'status': '판단 제한'}
    box_high = float(recent['High'].max())
    box_low = float(recent['Low'].min())
    if curr >= box_high:
        status = '박스 상단 돌파 관찰'
    elif box_high > 0 and (box_high - curr) / curr * 100 <= 3:
        status = '상단 근접'
    elif box_low > 0 and (curr - box_low) / curr * 100 <= 3:
        status = '하단 근접'
    else:
        status = '박스 내부'
    return {'box_high': box_high, 'box_low': box_low, 'status': status}

def _previous_high_info(curr, high_52w, fmt):
    if high_52w is None or np.isnan(high_52w):
        return {'text': '전고점: N/A', 'status': '판단 제한', 'pct': None}
    pct = nearest_pct(curr, high_52w)
    if curr >= high_52w:
        status = '신고가 관찰'
    elif pct <= 3:
        status = '전고점 근접'
    else:
        status = '전고점 거리 확인'
    return {
        'text': f"전고점: 52주 고점 {fmt(high_52w)}까지 {pct:+.1f}% — {status}",
        'status': status,
        'pct': pct,
    }

def _breakout_info(hist, curr):
    if len(hist) < 21:
        return {'text': '돌파 확인: N/A', 'long_candle': False, 'volume_spike': False}
    prev_close = float(hist['Close'].iloc[-2])
    last_open = float(hist['Open'].iloc[-1])
    last_close = float(hist['Close'].iloc[-1])
    day_pct = (curr - prev_close) / prev_close * 100 if prev_close else 0
    atr_pct = _calc_atr_pct(hist)
    avg_range = _avg_range_pct(hist)
    threshold = max(v for v in (atr_pct, avg_range) if v is not None) if (atr_pct or avg_range) else None
    long_candle = bool(threshold is not None and day_pct > threshold and last_close > last_open)

    volume_spike = False
    volume_text = '거래량 N/A'
    if 'Volume' in hist.columns:
        vol = hist['Volume'].tail(21).fillna(0)
        avg_vol20 = float(vol.iloc[:-1].mean()) if len(vol) >= 21 else 0
        last_vol = float(vol.iloc[-1])
        if avg_vol20 > 0 and last_vol > 0:
            volume_spike = last_vol >= avg_vol20 * 1.5
            volume_text = '거래량 동반 관찰' if volume_spike else '거래량 동반 없음'

    candle_text = '장대 양봉' if long_candle else '장대 양봉 아님'
    if long_candle and volume_spike:
        text = '돌파 확인: 장대 양봉 + 거래량 동반 관찰'
    else:
        text = f'돌파 확인: {volume_text} / {candle_text}'
    return {'text': text, 'long_candle': long_candle, 'volume_spike': volume_spike}

def cluster_levels(levels, tolerance_pct=0.015):
    if not levels:
        return []
    levels = sorted(levels)
    clusters = [[levels[0]]]
    for price in levels[1:]:
        if (price - clusters[-1][-1]) / clusters[-1][-1] < tolerance_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return [np.mean(c) for c in clusters]

def analyze_sr(name, ticker, asset_type):
    try:
        # 1년 데이터 사용: 최근 급락 자산도 현재가 아래 지지 레벨 탐색 가능
        hist = yf.Ticker(ticker).history(period='1y')
        data_source = 'yfinance'
        source_note = ''
        if hist.empty or len(hist) < 30:
            naver_hist = _fetch_naver_daily(ticker)
            if naver_hist is None or len(naver_hist) < 120:
                return None
            hist = naver_hist
            data_source = 'naver'
            source_note = '재검증 성공'

        close  = list(hist['Close'])
        high   = list(hist['High'])
        low    = list(hist['Low'])
        curr   = float(close[-1])
        prev_close = float(close[-2])

        # 미국/글로벌 티커: 1분봉 prepost로 실시간 현재가 갱신
        if not (ticker.endswith('.KS') or ticker in ('^KS11',)):
            try:
                h1m = yf.Ticker(ticker).history(period='1d', interval='1m', prepost=True)
                if not h1m.empty:
                    curr = float(h1m['Close'].iloc[-1])
            except Exception:
                pass

        # 1년 데이터 = 52주 고/저점
        high_52w = float(hist['High'].max())
        low_52w  = float(hist['Low'].min())
        data_warnings = _data_warnings(name.strip(), ticker, hist, curr, prev_close)

        if data_warnings and _naver_symbol(ticker):
            naver_hist = _fetch_naver_daily(ticker)
            if naver_hist is not None and len(naver_hist) >= 120:
                naver_curr = float(naver_hist['Close'].iloc[-1])
                naver_prev = float(naver_hist['Close'].iloc[-2])
                naver_warnings = _data_warnings(name.strip(), ticker, naver_hist, naver_curr, naver_prev)
                if not naver_warnings:
                    hist = naver_hist
                    close = list(hist['Close'])
                    high = list(hist['High'])
                    low = list(hist['Low'])
                    curr = naver_curr
                    prev_close = naver_prev
                    high_52w = float(hist['High'].max())
                    low_52w = float(hist['Low'].min())
                    data_warnings = []
                    data_source = 'naver'
                    source_note = '재검증 성공'
                else:
                    data_source = 'yfinance 이상 / naver 실패'
            else:
                data_source = 'yfinance 이상 / naver 실패'

        round_res, round_sup = find_round_numbers(curr)
        near_upper, near_lower = _near_observation_lines(
            curr, high_52w, low_52w, round_res, round_sup
        )
        long_upper, long_lower = _long_reference_lines(curr, high_52w, low_52w)

        base = {
            'name':        name.strip(),
            'ticker':      ticker,
            'asset_type':  asset_type,
            'curr':        curr,
            'resistances': [],
            'supports':    [],
            'high_52w':    high_52w,
            'low_52w':     low_52w,
            'res_data':    [],
            'sup_data':    [],
            'round_res':   round_res,
            'round_sup':   round_sup,
            'near_upper':  near_upper,
            'near_lower':  near_lower,
            'long_upper':  long_upper,
            'long_lower':  long_lower,
            'data_warnings': data_warnings,
            'series_scale_check': False,
            'data_source': data_source,
            'source_note': source_note,
        }

        if data_warnings or _is_limited_asset(asset_type) or _is_macro(asset_type):
            return base

        fmt = _mk_fmt(asset_type)
        trend = _trend_info(hist, curr, asset_type, ticker)
        series_scale_check = _series_scale_check(ticker, curr, low_52w, trend.get('ma200'))
        box = _box_info(hist, curr)
        previous_high = _previous_high_info(curr, high_52w, fmt)
        breakout = _breakout_info(hist, curr)

        pivot_highs = find_pivot_highs(high, window=10)
        pivot_lows  = find_pivot_lows(low,  window=10)

        resistances = cluster_levels([p for p in pivot_highs if p > curr])
        supports    = cluster_levels([p for p in pivot_lows  if p < curr])

        high_arr = list(hist['High'])
        low_arr  = list(hist['Low'])

        # 저항 레벨 강도 계산
        res_data = []
        for lv in resistances[:3]:
            tc = count_touches(high_arr, lv)
            last_idx = 0
            for i, p in enumerate(high_arr):
                if abs(p - lv) / max(lv, 1e-9) <= 0.015:
                    last_idx = i
            recency = last_idx / max(len(high_arr) - 1, 1)
            stars, star_label = rate_strength(tc, recency)
            res_data.append({'price': lv, 'touch': tc, 'stars': stars, 'star_label': star_label, 'recency': recency})

        # 지지 레벨 강도 계산
        sup_data = []
        for lv in supports[-3:]:
            tc = count_touches(low_arr, lv)
            last_idx = 0
            for i, p in enumerate(low_arr):
                if abs(p - lv) / max(lv, 1e-9) <= 0.015:
                    last_idx = i
            recency = last_idx / max(len(low_arr) - 1, 1)
            stars, star_label = rate_strength(tc, recency)
            sup_data.append({'price': lv, 'touch': tc, 'stars': stars, 'star_label': star_label, 'recency': recency})

        base.update({
            'resistances': resistances[:3],
            'supports':    supports[-3:],
            'res_data':    res_data,
            'sup_data':    sup_data,
            'trend':       trend,
            'box':         box,
            'previous_high': previous_high,
            'breakout':    breakout,
            'series_scale_check': series_scale_check,
        })
        return base
    except Exception as e:
        print(f"  ⚠ {name.strip()} 오류: {e}")
        return None

def nearest_pct(curr, level):
    return (level - curr) / curr * 100

# ── SVG 가격 사다리 차트 ─────────────────────────────────────

def _svg_ladder(r):
    """52주 범위 위에 지지/저항/현재가를 시각화하는 SVG 반환."""
    curr = r['curr']
    h52  = r['high_52w']
    l52  = r['low_52w']
    at   = r['asset_type']
    fmt  = _mk_fmt(at)

    if (np.isnan(h52) or np.isnan(l52) or np.isnan(curr)
            or h52 == l52 or h52 < l52):
        return '<p style="color:#aaa;font-size:12px;padding:20px 0">52주 데이터 없음</p>'

    CH = 320   # 차트 높이
    CW = 34    # 가격 바 폭
    PL = 78    # 왼쪽 패딩 (%, 레이블)
    PR = 128   # 오른쪽 패딩 (가격)
    PT = 16    # 상단 여백
    PB = 16    # 하단 여백
    TW = PL + CW + PR
    TH = CH + PT + PB

    def py(price):
        ratio = (price - l52) / (h52 - l52)
        return PT + CH * (1.0 - ratio)

    items = []

    # 배경 그라데이션 (위=빨강, 아래=초록)
    items.append(
        '<defs>'
        '<linearGradient id="sr-grad" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#fdecea" stop-opacity="0.8"/>'
        '<stop offset="45%" stop-color="#f9f9f9"/>'
        '<stop offset="100%" stop-color="#e8f5e9" stop-opacity="0.8"/>'
        '</linearGradient></defs>'
    )
    items.append(
        f'<rect x="{PL}" y="{PT}" width="{CW}" height="{CH}" '
        f'fill="url(#sr-grad)" rx="3" stroke="#e0e0e0" stroke-width="1"/>'
    )

    # 현재가 이하 블루 오버레이
    yc = py(curr)
    fill_h = (PT + CH) - yc
    if fill_h > 0:
        items.append(
            f'<rect x="{PL}" y="{yc:.1f}" width="{CW}" height="{fill_h:.1f}" '
            f'fill="rgba(26,95,168,0.08)" rx="0"/>'
        )

    # 52주 고점 점선
    yh = py(h52)
    items.append(
        f'<line x1="{PL-4}" y1="{yh:.1f}" x2="{PL+CW+4}" y2="{yh:.1f}" '
        f'stroke="#ccc" stroke-width="1" stroke-dasharray="3,3"/>'
    )
    items.append(
        f'<text x="{PL-6}" y="{yh+4:.1f}" text-anchor="end" '
        f'font-size="9" fill="#bbb">52H</text>'
    )
    items.append(
        f'<text x="{PL+CW+6}" y="{yh+4:.1f}" font-size="9" fill="#bbb">{fmt(h52)}</text>'
    )

    # 52주 저점 점선
    yl = py(l52)
    items.append(
        f'<line x1="{PL-4}" y1="{yl:.1f}" x2="{PL+CW+4}" y2="{yl:.1f}" '
        f'stroke="#ccc" stroke-width="1" stroke-dasharray="3,3"/>'
    )
    items.append(
        f'<text x="{PL-6}" y="{yl+4:.1f}" text-anchor="end" '
        f'font-size="9" fill="#bbb">52L</text>'
    )
    items.append(
        f'<text x="{PL+CW+6}" y="{yl+4:.1f}" font-size="9" fill="#bbb">{fmt(l52)}</text>'
    )

    # 저항 레벨 (빨강)
    for lv in sorted(r['resistances']):
        yp  = py(lv)
        pct = nearest_pct(curr, lv)
        items.append(
            f'<line x1="{PL}" y1="{yp:.1f}" x2="{PL+CW}" y2="{yp:.1f}" '
            f'stroke="#ef5350" stroke-width="2.5"/>'
        )
        items.append(
            f'<circle cx="{PL}" cy="{yp:.1f}" r="4.5" fill="#ef5350" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<circle cx="{PL+CW}" cy="{yp:.1f}" r="4.5" fill="#ef5350" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<text x="{PL-8}" y="{yp+4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#ef5350" font-weight="700">+{pct:.1f}%</text>'
        )
        items.append(
            f'<text x="{PL+CW+8}" y="{yp+4:.1f}" font-size="10" fill="#c62828">{fmt(lv)}</text>'
        )

    # 현재가 (파랑, 굵게)
    items.append(
        f'<polygon points="{PL-3},{yc:.1f} {PL-13},{yc-6:.1f} {PL-13},{yc+6:.1f}" fill="#1a5fa8"/>'
    )
    items.append(
        f'<line x1="{PL-3}" y1="{yc:.1f}" x2="{PL+CW+3}" y2="{yc:.1f}" '
        f'stroke="#1a5fa8" stroke-width="3"/>'
    )
    items.append(
        f'<polygon points="{PL+CW+3},{yc:.1f} {PL+CW+13},{yc-6:.1f} {PL+CW+13},{yc+6:.1f}" '
        f'fill="#1a5fa8"/>'
    )
    items.append(
        f'<text x="{PL-16}" y="{yc+4:.1f}" text-anchor="end" '
        f'font-size="11" fill="#1a5fa8" font-weight="800">현재가</text>'
    )
    items.append(
        f'<text x="{PL+CW+16}" y="{yc+4:.1f}" '
        f'font-size="11" fill="#1a5fa8" font-weight="800">{fmt(curr)}</text>'
    )

    # 지지 레벨 (초록)
    for lv in sorted(r['supports'], reverse=True):
        yp  = py(lv)
        pct = nearest_pct(curr, lv)
        items.append(
            f'<line x1="{PL}" y1="{yp:.1f}" x2="{PL+CW}" y2="{yp:.1f}" '
            f'stroke="#26a69a" stroke-width="2.5"/>'
        )
        items.append(
            f'<circle cx="{PL}" cy="{yp:.1f}" r="4.5" fill="#26a69a" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<circle cx="{PL+CW}" cy="{yp:.1f}" r="4.5" fill="#26a69a" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<text x="{PL-8}" y="{yp+4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#26a69a" font-weight="700">{pct:.1f}%</text>'
        )
        items.append(
            f'<text x="{PL+CW+8}" y="{yp+4:.1f}" font-size="10" fill="#1a7a6a">{fmt(lv)}</text>'
        )

    return (f'<svg width="{TW}" height="{TH}" viewBox="0 0 {TW} {TH}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(items)}</svg>')


# ── 요약/HTML 생성 ────────────────────────────────────────

def build_summary_lines(all_results):
    """9번 종합 분석이 읽을 6번 요약 라인."""
    def _normal_results():
        return [
            r for r in all_results
            if r and not r.get('data_warnings')
            and not _is_limited_asset(r.get('asset_type'))
            and not _is_macro(r.get('asset_type'))
        ]

    def _nearest_upper_pct(r):
        vals = [d['price'] for d in r.get('res_data', [])]
        vals += [x['price'] for x in r.get('near_upper', [])]
        vals = [v for v in vals if v and v > r['curr']]
        return min([nearest_pct(r['curr'], v) for v in vals], default=None)

    def _nearest_support_pct(r):
        vals = [d['price'] for d in r.get('sup_data', [])]
        vals = [v for v in vals if v and v < r['curr']]
        return max([nearest_pct(r['curr'], v) for v in vals], default=None)

    clean = _normal_results()
    warned = [r for r in all_results if r and r.get('data_warnings')]
    high_near = [
        r for r in clean
        if r.get('high_52w') and r['high_52w'] > r['curr']
        and nearest_pct(r['curr'], r['high_52w']) <= 5
    ]
    near_res = [(r, _nearest_upper_pct(r)) for r in clean]
    near_res = [(r, p) for r, p in near_res if p is not None and 0 <= p <= 5]
    near_sup = [(r, _nearest_support_pct(r)) for r in clean]
    near_sup = [(r, p) for r, p in near_sup if p is not None and -5 <= p <= 0]
    support_gap = [(r, _nearest_support_pct(r)) for r in clean]
    support_gap = [(r, p) for r, p in support_gap if p is None or p < -10]
    macro = [r for r in all_results if r and _is_macro(r.get('asset_type'))]
    limited = [r for r in all_results if r and _is_limited_asset(r.get('asset_type'))]
    uptrend = [r for r in clean if r.get('trend', {}).get('status') == '상승추세']
    box_upper = [
        r for r in clean
        if r.get('box', {}).get('status') in ('상단 근접', '박스 상단 돌파 관찰')
    ]
    prev_high_watch = [
        r for r in clean
        if r.get('previous_high', {}).get('status') in ('전고점 근접', '신고가 관찰')
    ]
    down_or_reversal = [
        r for r in clean
        if r.get('trend', {}).get('status') in ('하락추세', '반전 시도')
    ]
    volume_breakout = [
        r for r in clean
        if r.get('breakout', {}).get('long_candle') and r.get('breakout', {}).get('volume_spike')
    ]
    series_check = [r for r in clean if r.get('series_scale_check')]
    return [
        f"데이터 경고: {', '.join(r['name'] for r in warned) + ' — 원천 가격 이상으로 계산 제외' if warned else '없음'}",
        f"시계열 점검: {', '.join(r['name'] for r in series_check) or '없음'}",
        f"52주 고점 근접 종목: {', '.join(f'{r['name']} {nearest_pct(r['curr'], r['high_52w']):+.1f}%' for r in high_near[:5]) or '없음'}",
        f"근접 저항 5% 이내 종목: {', '.join(f'{r['name']} +{p:.1f}%' for r, p in near_res[:5]) or '없음'}",
        f"근접 지지 5% 이내 종목: {', '.join(f'{r['name']} {p:.1f}%' for r, p in near_sup[:5]) or '없음'}",
        f"지지 공백: {', '.join(f'{r['name']}({p:.1f}%)' if p is not None else f'{r['name']}(N/A)' for r, p in support_gap[:5]) or '없음'}",
        f"매크로 관찰: {', '.join(f'{r['ticker']} 관찰선' for r in macro) or '없음'}",
        f"해석 제한: {', '.join(r['name'] for r in limited) or '없음'}",
        f"상승추세 종목: {', '.join(r['name'] for r in uptrend[:5]) or '없음'}",
        f"박스 상단 근접: {', '.join(f'{r['name']}({r.get('box', {}).get('status')})' for r in box_upper[:5]) or '없음'}",
        f"전고점/52주 고점 근접: {', '.join(f'{r['name']}({r.get('previous_high', {}).get('status')})' for r in prev_high_watch[:5]) or '없음'}",
        f"하락추세/반전 시도: {', '.join(f'{r['name']}({r.get('trend', {}).get('status')})' for r in down_or_reversal[:5]) or '없음'}",
        f"거래량 동반 돌파 관찰: {', '.join(r['name'] for r in volume_breakout[:5]) or '없음'}",
    ]


def generate_html(all_results, timestamp):
    def _normal_results():
        return [
            r for r in all_results
            if r and not r.get('data_warnings')
            and not _is_limited_asset(r.get('asset_type'))
            and not _is_macro(r.get('asset_type'))
        ]

    def _nearest_upper_pct(r):
        vals = [d['price'] for d in r.get('res_data', [])]
        vals += [x['price'] for x in r.get('near_upper', [])]
        vals = [v for v in vals if v and v > r['curr']]
        return min([nearest_pct(r['curr'], v) for v in vals], default=None)

    def _nearest_support_pct(r):
        vals = [d['price'] for d in r.get('sup_data', [])]
        vals = [v for v in vals if v and v < r['curr']]
        return max([nearest_pct(r['curr'], v) for v in vals], default=None)

    clean = _normal_results()
    warned = [r for r in all_results if r and r.get('data_warnings')]
    high_near = [
        r for r in clean
        if r.get('high_52w') and r['high_52w'] > r['curr']
        and nearest_pct(r['curr'], r['high_52w']) <= 5
    ]
    near_res = [(r, _nearest_upper_pct(r)) for r in clean]
    near_res = [(r, p) for r, p in near_res if p is not None and 0 <= p <= 5]
    near_sup = [(r, _nearest_support_pct(r)) for r in clean]
    near_sup = [(r, p) for r, p in near_sup if p is not None and -5 <= p <= 0]
    support_gap = [(r, _nearest_support_pct(r)) for r in clean]
    support_gap = [(r, p) for r, p in support_gap if p is None or p < -10]
    macro = [r for r in all_results if r and _is_macro(r.get('asset_type'))]
    limited = [r for r in all_results if r and _is_limited_asset(r.get('asset_type'))]
    uptrend = [r for r in clean if r.get('trend', {}).get('status') == '상승추세']
    box_upper = [
        r for r in clean
        if r.get('box', {}).get('status') in ('상단 근접', '박스 상단 돌파 관찰')
    ]
    prev_high_watch = [
        r for r in clean
        if r.get('previous_high', {}).get('status') in ('전고점 근접', '신고가 관찰')
    ]
    down_or_reversal = [
        r for r in clean
        if r.get('trend', {}).get('status') in ('하락추세', '반전 시도')
    ]
    volume_breakout = [
        r for r in clean
        if r.get('breakout', {}).get('long_candle') and r.get('breakout', {}).get('volume_spike')
    ]
    series_check = [r for r in clean if r.get('series_scale_check')]
    series_check = [r for r in clean if r.get('series_scale_check')]
    box_upper_s = ', '.join(
        f"{r['name']}({r.get('box', {}).get('status')})" for r in box_upper[:5]
    )
    prev_high_watch_s = ', '.join(
        f"{r['name']}({r.get('previous_high', {}).get('status')})" for r in prev_high_watch[:5]
    )
    down_or_reversal_s = ', '.join(
        f"{r['name']}({r.get('trend', {}).get('status')})" for r in down_or_reversal[:5]
    )
    volume_breakout_s = ', '.join(r['name'] for r in volume_breakout[:5])

    summary_html = f"""
<div class="summary">
  <div class="summary-title">[요약]</div>
  <div>데이터 경고: {', '.join(r['name'] for r in warned) + ' — 원천 가격 이상으로 계산 제외' if warned else '없음'}</div>
  <div>시계열 점검: {', '.join(r['name'] for r in series_check) or '없음'}</div>
  <div>52주 고점 근접 종목: {', '.join(f"{r['name']} {nearest_pct(r['curr'], r['high_52w']):+.1f}%" for r in high_near[:5]) or '없음'}</div>
  <div>근접 저항 5% 이내 종목: {', '.join(f"{r['name']} +{p:.1f}%" for r, p in near_res[:5]) or '없음'}</div>
  <div>근접 지지 5% 이내 종목: {', '.join(f"{r['name']} {p:.1f}%" for r, p in near_sup[:5]) or '없음'}</div>
  <div>지지 공백: {', '.join(f"{r['name']}({p:.1f}%)" if p is not None else f"{r['name']}(N/A)" for r, p in support_gap[:5]) or '없음'}</div>
  <div>매크로 관찰: {', '.join(f"{r['ticker']} 관찰선" for r in macro) or '없음'}</div>
  <div>해석 제한: {', '.join(r['name'] for r in limited) or '없음'}</div>
  <div>상승추세 종목: {', '.join(r['name'] for r in uptrend[:5]) or '없음'}</div>
  <div>박스 상단 근접: {', '.join(f"{r['name']}({r.get('box', {}).get('status')})" for r in box_upper[:5]) or '없음'}</div>
  <div>전고점/52주 고점 근접: {', '.join(f"{r['name']}({r.get('previous_high', {}).get('status')})" for r in prev_high_watch[:5]) or '없음'}</div>
  <div>하락추세/반전 시도: {', '.join(f"{r['name']}({r.get('trend', {}).get('status')})" for r in down_or_reversal[:5]) or '없음'}</div>
  <div>거래량 동반 돌파 관찰: {', '.join(r['name'] for r in volume_breakout[:5]) or '없음'}</div>
  <div class="method-note">터치 수는 허용범위 내 과거 가격 접근 횟수이며, 강도는 터치 수와 가격 밀집도 기반 참고값입니다. 매매 신호가 아니라 관찰 레벨입니다.</div>
</div>"""

    cards = ''
    for r in all_results:
        if not r:
            continue
        curr   = r['curr']
        at     = r['asset_type']
        ticker = r['ticker']
        name   = r['name']
        h52    = r['high_52w']
        l52    = r['low_52w']
        fmt    = _mk_fmt(at)

        # 52주 위치 %
        pos_pct = 0.0
        if (h52 != l52 and not np.isnan(h52) and not np.isnan(l52)
                and not np.isnan(curr)):
            pos_pct = (curr - l52) / (h52 - l52) * 100
        pos_pct = max(0.0, min(100.0, pos_pct))

        high_pct = nearest_pct(curr, h52) if not np.isnan(h52) else 0
        low_pct  = nearest_pct(curr, l52) if not np.isnan(l52) else 0
        scale_check_html = (
            f'<div class="warn-line">⚠ {SCALE_CHECK_MESSAGE}</div>'
            if r.get('series_scale_check') else ''
        )

        data_warning_html = ''.join(
            f'<div class="warn-line">⚠ {w}</div>' for w in r.get('data_warnings', [])
        )
        if r.get('data_warnings'):
            cards += f"""
<div class="card">
  <div class="chdr">
    <div class="chdr-l"><span class="ctick">{ticker}</span><span class="cname">{name}</span></div>
    <div class="chdr-r"><span class="cprice">{fmt(curr)}</span><span class="cpos">신뢰 제한</span><span class="cpos">데이터 출처: {_source_text(r)}</span></div>
  </div>
  <div class="limited-card">
    {data_warning_html}
    <div class="limit-msg">지지·저항: 신뢰 제한 — 원천 가격 데이터 이상으로 계산 제외</div>
  </div>
</div>"""
            continue

        if _is_limited_asset(at):
            cards += f"""
<div class="card">
  <div class="chdr">
    <div class="chdr-l"><span class="ctick">{ticker}</span><span class="cname">{name}</span></div>
    <div class="chdr-r"><span class="cprice">{fmt(curr)}</span><span class="cpos">해석 제한</span><span class="cpos">데이터 출처: {_source_text(r)}</span></div>
  </div>
  <div class="limited-card">
    <div class="limit-msg">지지·저항: 해석 제한 — 현금성/금리형 상품은 일반 지지·저항 해석 부적합</div>
    <div class="obs-block"><b>근접 관찰선</b><br>상단: N/A<br>하단: N/A</div>
  </div>
</div>"""
            continue

        if _is_macro(at):
            cards += f"""
<div class="card">
  <div class="chdr">
    <div class="chdr-l"><span class="ctick">{ticker}</span><span class="cname">{name}</span></div>
    <div class="chdr-r"><span class="cprice">{fmt(curr)}</span><span class="cpos">매크로 관찰</span><span class="cpos">데이터 출처: {_source_text(r)}</span></div>
  </div>
    <div class="limited-card">
    <div class="limit-msg">매크로 관찰선 — 일반 지지·저항이 아니라 환율/금리/변동성 부담 레벨 참고</div>
    <div class="obs-block">
      <b>근접 상단 관찰선</b>{_obs_html_lines(r.get('near_upper'), fmt, 'rc')}
      <b>근접 하단 관찰선</b>{_obs_html_lines(r.get('near_lower'), fmt, 'sc')}
      <b>장기 참고선</b>{_obs_html_lines((r.get('long_upper') or []) + (r.get('long_lower') or []), fmt, 'muted')}
    </div>
  </div>
</div>"""
            continue

        # 저항 레벨 행 (res_data 사용)
        res_rows = ''
        for d in sorted(r.get('res_data', []), key=lambda x: x['price'], reverse=True):
            lv     = d['price']
            pct    = nearest_pct(curr, lv)
            bar_w  = min(d['touch'] * 15, 100)
            res_rows += (
                f'<tr>'
                f'<td class="lv-price rc">{fmt(lv)}</td>'
                f'<td class="lv-pct rc">+{pct:.2f}%</td>'
                f'<td class="lv-bar"><div class="bar-r" style="width:{bar_w:.0f}%"></div></td>'
                f'<td class="lv-star" title="{d["touch"]}회 터치">{d["star_label"]}</td>'
                f'<td class="lv-touch">{d["touch"]}</td>'
                f'</tr>'
            )
        if not res_rows:
            res_rows = '<tr><td colspan="5" class="empty">근접 저항 부족 — 52주 고점/심리 가격대를 상단 관찰선으로 참고</td></tr>'

        # 지지 레벨 행 (sup_data 사용)
        sup_rows = ''
        for d in sorted(r.get('sup_data', []), key=lambda x: x['price'], reverse=True):
            lv     = d['price']
            pct    = nearest_pct(curr, lv)
            bar_w  = min(d['touch'] * 15, 100)
            sup_rows += (
                f'<tr>'
                f'<td class="lv-price sc">{fmt(lv)}</td>'
                f'<td class="lv-pct sc">{pct:.2f}%</td>'
                f'<td class="lv-bar"><div class="bar-s" style="width:{bar_w:.0f}%"></div></td>'
                f'<td class="lv-star" title="{d["touch"]}회 터치">{d["star_label"]}</td>'
                f'<td class="lv-touch">{d["touch"]}</td>'
                f'</tr>'
            )
        if not sup_rows:
            sup_rows = '<tr><td colspan="5" class="empty">지지 공백 — 52주 저점/심리 가격대를 하단 관찰선으로 참고</td></tr>'

        # 라운드 넘버 HTML
        round_res_html = ''
        for rv in (r.get('round_res') or [])[:5]:
            rpct = nearest_pct(curr, rv)
            round_res_html += f'<span class="rl-badge" style="color:#c62828">{fmt(rv)} (+{rpct:.1f}%)</span>'
        round_sup_html = ''
        for rv in (r.get('round_sup') or [])[:5]:
            rpct = nearest_pct(curr, rv)
            round_sup_html += f'<span class="rl-badge" style="color:#1a7a6a">{fmt(rv)} ({rpct:.1f}%)</span>'
        round_section = ''
        if round_res_html or round_sup_html:
            round_section = f"""<div class="round-section">
            <div class="sec-hdr" style="background:#f3e5f5;color:#6a1b9a">🔮 심리적 가격대 (라운드 넘버)</div>
            <div class="round-levels">
              {round_res_html}
              {round_sup_html}
            </div>
          </div>"""

        near_section = f"""<div class="round-section">
            <div class="sec-hdr" style="background:#eef4ff;color:#1a5fa8">근접 관찰선</div>
            <div class="round-levels">
              <b style="width:100%;font-size:11px;color:#999">상단</b>
              {_obs_html(r.get('near_upper'), fmt, 'rc')}
              <b style="width:100%;font-size:11px;color:#999;margin-top:4px">하단</b>
              {_obs_html(r.get('near_lower'), fmt, 'sc')}
            </div>
          </div>"""
        long_refs = (r.get('long_upper') or []) + (r.get('long_lower') or [])
        long_section = ''
        if long_refs:
            long_section = f"""<div class="round-section">
            <div class="sec-hdr" style="background:#f5f5f5;color:#555">장기 참고선</div>
            <div class="round-levels">{_obs_html(long_refs, fmt, 'muted')}</div>
          </div>"""

        trend = r.get('trend', {})
        box = r.get('box', {})
        previous_high = r.get('previous_high', {})
        breakout = r.get('breakout', {})
        kr_ma_html = (
            f'<div><b>이동평균:</b> {trend.get("kr_ma")}</div>'
            if trend.get('kr_ma') else ''
        )
        trend_section = f"""<div class="trend-section">
            <div class="sec-hdr" style="background:#e8f5e9;color:#1b5e20">추세 / 박스 관찰</div>
            <div class="trend-row"><b>상태:</b> {trend.get('status', '판단 제한')}</div>
            <div class="trend-row"><b>기준:</b> {trend.get('basis', '50일선, 200일선, 최근 고점/저점 흐름')}</div>
            <div class="trend-row"><b>현재가 vs MA50/MA200:</b> MA50 {trend.get('ma50_side', 'N/A')} ({_fmt_optional(fmt, trend.get('ma50'))}) / MA200 {trend.get('ma200_side', 'N/A')} ({_fmt_optional(fmt, trend.get('ma200'))})</div>
            <div class="trend-row"><b>중장기:</b> {trend.get('long_term', '판단 제한')} · {trend.get('flow', '')}</div>
            {kr_ma_html}
            <div class="trend-row"><b>박스:</b> 상단 {_fmt_optional(fmt, box.get('box_high'))} / 하단 {_fmt_optional(fmt, box.get('box_low'))}</div>
            <div class="trend-row"><b>박스 상태:</b> {box.get('status', '판단 제한')}</div>
            <div class="trend-row"><b>{previous_high.get('text', '전고점: N/A')}</b></div>
            <div class="trend-row"><b>{breakout.get('text', '돌파 확인: N/A')}</b></div>
          </div>"""

        svg = _svg_ladder(r)

        cards += f"""
<div class="card">
  <div class="chdr">
    <div class="chdr-l">
      <span class="ctick">{ticker}</span>
      <span class="cname">{name}</span>
    </div>
    <div class="chdr-r">
      <span class="cprice">{fmt(curr)}</span>
      <span class="cpos">52주 {pos_pct:.0f}% 위치</span>
      <span class="cpos">데이터 출처: {_source_text(r)}</span>
    </div>
  </div>
  <div class="cbody">

    <!-- SVG 가격 사다리 -->
    <div class="svg-col">
      <div class="col-title">📈 가격 레벨 차트</div>
      {svg}
      <div class="legend">
        <span class="rc">● 저항</span>
        <span class="blue">● 현재가</span>
        <span class="sc">● 지지</span>
        <span style="color:#ccc">-- 52주 범위</span>
      </div>
    </div>

    <!-- 수치 상세 -->
    <div class="detail-col">

      <div class="sec-block">
        <div class="sec-hdr rh">🔴 저항 레벨 (상승 저항)</div>
        <table class="lv-tbl">
          <thead><tr><th>가격</th><th>거리</th><th>강도바</th><th>강도</th><th>터치</th></tr></thead>
          <tbody>{res_rows}</tbody>
        </table>
      </div>

      <div class="curr-band">▶ 현재가 &nbsp;<strong>{fmt(curr)}</strong></div>
      {scale_check_html}

      <div class="sec-block">
        <div class="sec-hdr sh">🟢 지지 레벨 (하락 지지)</div>
        <table class="lv-tbl">
          <thead><tr><th>가격</th><th>거리</th><th>강도바</th><th>강도</th><th>터치</th></tr></thead>
          <tbody>{sup_rows}</tbody>
        </table>
      </div>

      {round_section}
      {near_section}
      {long_section}
      {trend_section}

      <!-- 52주 통계 -->
      <div class="w52">
        <div class="w52-item">
          <div class="w52-lbl">52주 고점</div>
          <div class="w52-val rc">{fmt(h52)}</div>
          <div class="w52-sub rc">{high_pct:+.1f}%</div>
        </div>
        <div class="w52-item">
          <div class="w52-lbl">현재가 위치</div>
          <div class="w52-val blue">{pos_pct:.0f}%</div>
          <div class="w52-track"><div class="w52-dot" style="left:{pos_pct:.1f}%"></div></div>
        </div>
        <div class="w52-item">
          <div class="w52-lbl">52주 저점</div>
          <div class="w52-val sc">{fmt(l52)}</div>
          <div class="w52-sub sc">{low_pct:+.1f}%</div>
        </div>
      </div>

    </div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason Market — 지지/저항 레벨</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#f0f2f5;color:#222;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;}}

.top-hdr{{padding:14px 24px;background:#1a237e;color:#fff;}}
.top-hdr h1{{font-size:17px;font-weight:700;}}
.top-hdr .sub{{font-size:11px;color:#aaa;margin-top:4px;}}

.page{{max-width:1400px;margin:0 auto;padding:18px 16px;
       display:grid;grid-template-columns:repeat(auto-fill,minmax(600px,1fr));gap:16px;}}

.summary{{max-width:1400px;margin:16px auto 0;background:#fff;border:1px solid #dde3f0;
          border-radius:8px;padding:14px 18px;line-height:1.7;box-shadow:0 1px 5px rgba(0,0,0,.06);}}
.summary-title{{font-size:14px;font-weight:800;color:#1a237e;margin-bottom:4px;}}
.method-note{{margin-top:6px;color:#666;font-size:12px;border-top:1px solid #eee;padding-top:6px;}}

.card{{background:#fff;border:1px solid #ddd;border-radius:8px;overflow:hidden;
       box-shadow:0 1px 5px rgba(0,0,0,.07);}}
.limited-card{{padding:16px 18px;line-height:1.7;}}
.limit-msg{{background:#f8f9fa;border-left:3px solid #90a4ae;border-radius:4px;
            padding:9px 11px;color:#555;font-weight:600;}}
.warn-line{{background:#fff5f5;border-left:3px solid #c62828;border-radius:4px;
            padding:7px 10px;color:#c62828;margin-bottom:8px;font-size:12px;}}
.obs-block{{margin-top:10px;background:#fafafa;border:1px solid #eee;border-radius:5px;
            padding:10px 12px;color:#555;}}
.obs-line{{display:block;margin:4px 0;}}

/* 카드 헤더 */
.chdr{{display:flex;justify-content:space-between;align-items:center;
       padding:12px 18px;background:#fafafa;border-bottom:1px solid #eee;}}
.chdr-l{{display:flex;align-items:baseline;gap:8px;}}
.ctick{{font-size:21px;font-weight:800;color:#1a1a2e;}}
.cname{{font-size:12px;color:#999;}}
.chdr-r{{text-align:right;}}
.cprice{{font-size:18px;font-weight:700;color:#1a5fa8;display:block;}}
.cpos{{font-size:10px;color:#aaa;}}

/* 카드 바디 */
.cbody{{display:flex;}}
.svg-col{{padding:14px 12px 12px 10px;border-right:1px solid #f0f0f0;flex-shrink:0;}}
.col-title{{font-size:10px;font-weight:600;color:#aaa;text-transform:uppercase;
            letter-spacing:.4px;margin-bottom:8px;}}
.legend{{display:flex;gap:10px;font-size:10px;margin-top:8px;flex-wrap:wrap;}}

/* 수치 패널 */
.detail-col{{flex:1;padding:12px 16px;display:flex;flex-direction:column;gap:8px;}}
.sec-block{{}}
.sec-hdr{{font-size:11px;font-weight:700;padding:5px 8px;border-radius:4px;margin-bottom:4px;}}
.rh{{background:#fff0ef;color:#c62828;}}
.sh{{background:#edf9f6;color:#1a7a6a;}}

/* 레벨 테이블 */
.lv-tbl{{width:100%;border-collapse:collapse;font-size:12px;}}
.lv-tbl th{{color:#bbb;font-weight:500;padding:3px 8px;border-bottom:1px solid #f0f0f0;font-size:10px;}}
.lv-tbl th:last-child{{width:70px;}}
.lv-tbl td{{padding:4px 8px;border-bottom:1px solid #f8f8f8;vertical-align:middle;}}
.lv-tbl td.lv-price{{font-family:monospace;font-size:12px;font-weight:600;}}
.lv-tbl td.lv-pct{{font-weight:700;width:64px;font-size:12px;}}
.lv-tbl td.lv-bar{{width:70px;padding:6px 8px;}}
.bar-r{{height:6px;background:#ef5350;border-radius:3px;min-width:2px;}}
.bar-s{{height:6px;background:#26a69a;border-radius:3px;min-width:2px;}}
.lv-tbl td.empty{{color:#bbb;font-style:italic;font-size:11px;}}
.lv-tbl td.lv-star{{font-size:11px;color:#888;padding:4px 4px;}}
.lv-tbl td.lv-touch{{font-size:11px;color:#aaa;text-align:center;}}

.rc{{color:#ef5350;}}.sc{{color:#26a69a;}}.blue{{color:#1a5fa8;}}
.round-section{{margin-top:8px;border:1px solid #e1bee7;border-radius:5px;overflow:hidden;}}
.round-levels{{padding:8px 10px;display:flex;flex-wrap:wrap;gap:5px;background:#fce4ec00;}}
.rl-badge{{font-size:11px;font-weight:600;background:#f5f5f5;padding:3px 8px;border-radius:4px;border:1px solid #eee;}}
.rl-badge.muted{{color:#aaa;}}
.trend-section{{margin-top:8px;border:1px solid #d8ead8;border-radius:5px;overflow:hidden;background:#fbfffb;}}
.trend-row{{font-size:11px;color:#444;line-height:1.55;padding:2px 9px;}}
.trend-row:last-child{{padding-bottom:8px;}}

/* 현재가 구분선 */
.curr-band{{text-align:center;padding:6px 8px;background:#eef4ff;
            border-radius:4px;font-size:12px;color:#1a5fa8;font-weight:600;}}

/* 52주 통계 */
.w52{{display:flex;gap:8px;background:#f8f8f8;border-radius:6px;padding:10px;margin-top:4px;}}
.w52-item{{flex:1;text-align:center;}}
.w52-lbl{{font-size:9px;color:#aaa;text-transform:uppercase;margin-bottom:3px;}}
.w52-val{{font-size:13px;font-weight:700;}}
.w52-sub{{font-size:10px;font-weight:600;margin-top:1px;}}
.w52-track{{height:5px;background:#ddd;border-radius:3px;position:relative;margin-top:6px;}}
.w52-dot{{position:absolute;top:-3px;width:11px;height:11px;background:#1a5fa8;
           border-radius:50%;transform:translateX(-50%);border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.2);}}
</style>
</head>
<body>
<div class="top-hdr">
  <h1>Jason Market — 지지/저항 레벨 분석</h1>
  <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 1년 피봇 레벨 · 52주 고/저점 범위 · 근접 관찰선</div>
</div>
<div id="report-root">
{summary_html}
<div class="page">{cards}</div>
</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('#report-root')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""


def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*60}")
    print(f"  Jason 지지/저항 레벨   {timestamp}")
    print(f"{'━'*60}")
    print("  데이터 수집 중 (약 10-20초)...\n")

    all_results = []
    for name, (ticker, asset_type) in ASSETS.items():
        r = analyze_sr(name, ticker, asset_type)
        if not r:
            continue
        all_results.append(r)

    def _nearest_upper_pct(r):
        vals = [d['price'] for d in r.get('res_data', [])]
        vals += [x['price'] for x in r.get('near_upper', [])]
        vals = [v for v in vals if v and v > r['curr']]
        return min([nearest_pct(r['curr'], v) for v in vals], default=None)

    def _nearest_support_pct(r):
        vals = [d['price'] for d in r.get('sup_data', [])]
        vals = [v for v in vals if v and v < r['curr']]
        return max([nearest_pct(r['curr'], v) for v in vals], default=None)

    clean = [
        r for r in all_results
        if not r.get('data_warnings')
        and not _is_limited_asset(r.get('asset_type'))
        and not _is_macro(r.get('asset_type'))
    ]
    warned = [r for r in all_results if r.get('data_warnings')]
    high_near = [
        r for r in clean
        if r.get('high_52w') and r['high_52w'] > r['curr']
        and nearest_pct(r['curr'], r['high_52w']) <= 5
    ]
    near_res = [(r, _nearest_upper_pct(r)) for r in clean]
    near_res = [(r, p) for r, p in near_res if p is not None and 0 <= p <= 5]
    near_sup = [(r, _nearest_support_pct(r)) for r in clean]
    near_sup = [(r, p) for r, p in near_sup if p is not None and -5 <= p <= 0]
    support_gap = [(r, _nearest_support_pct(r)) for r in clean]
    support_gap = [(r, p) for r, p in support_gap if p is None or p < -10]
    macro = [r for r in all_results if _is_macro(r.get('asset_type'))]
    limited = [r for r in all_results if _is_limited_asset(r.get('asset_type'))]
    warned_s = ', '.join(r['name'] for r in warned)
    high_near_s = ', '.join(
        f"{r['name']} {nearest_pct(r['curr'], r['high_52w']):+.1f}%"
        for r in high_near[:5]
    )
    near_res_s = ', '.join(f"{r['name']} +{p:.1f}%" for r, p in near_res[:5])
    near_sup_s = ', '.join(f"{r['name']} {p:.1f}%" for r, p in near_sup[:5])
    support_gap_s = ', '.join(
        f"{r['name']}({p:.1f}%)" if p is not None else f"{r['name']}(N/A)"
        for r, p in support_gap[:5]
    )
    uptrend = [r for r in clean if r.get('trend', {}).get('status') == '상승추세']
    box_upper = [
        r for r in clean
        if r.get('box', {}).get('status') in ('상단 근접', '박스 상단 돌파 관찰')
    ]
    prev_high_watch = [
        r for r in clean
        if r.get('previous_high', {}).get('status') in ('전고점 근접', '신고가 관찰')
    ]
    down_or_reversal = [
        r for r in clean
        if r.get('trend', {}).get('status') in ('하락추세', '반전 시도')
    ]
    volume_breakout = [
        r for r in clean
        if r.get('breakout', {}).get('long_candle') and r.get('breakout', {}).get('volume_spike')
    ]
    series_check = [r for r in clean if r.get('series_scale_check')]
    box_upper_s = ', '.join(
        f"{r['name']}({r.get('box', {}).get('status')})" for r in box_upper[:5]
    )
    prev_high_watch_s = ', '.join(
        f"{r['name']}({r.get('previous_high', {}).get('status')})" for r in prev_high_watch[:5]
    )
    down_or_reversal_s = ', '.join(
        f"{r['name']}({r.get('trend', {}).get('status')})" for r in down_or_reversal[:5]
    )
    volume_breakout_s = ', '.join(r['name'] for r in volume_breakout[:5])

    print("  [요약]")
    print(f"  - 데이터 경고: {warned_s + ' — 원천 가격 이상으로 계산 제외' if warned else '없음'}")
    print(f"  - 시계열 점검: {', '.join(r['name'] for r in series_check) or '없음'}")
    print(f"  - 52주 고점 근접 종목: {high_near_s or '없음'}")
    print(f"  - 근접 저항 5% 이내 종목: {near_res_s or '없음'}")
    print(f"  - 근접 지지 5% 이내 종목: {near_sup_s or '없음'}")
    print(f"  - 지지 공백: {support_gap_s or '없음'}")
    print(f"  - 매크로 관찰: {', '.join(r['ticker'] for r in macro) or '없음'}")
    print(f"  - 해석 제한: {', '.join(r['name'] for r in limited) or '없음'}")
    print(f"  - 상승추세 종목: {', '.join(r['name'] for r in uptrend[:5]) or '없음'}")
    print(f"  - 박스 상단 근접: {box_upper_s or '없음'}")
    print(f"  - 전고점/52주 고점 근접: {prev_high_watch_s or '없음'}")
    print(f"  - 하락추세/반전 시도: {down_or_reversal_s or '없음'}")
    print(f"  - 거래량 동반 돌파 관찰: {volume_breakout_s or '없음'}")
    print("  ※ 터치 수는 허용범위 내 과거 가격 접근 횟수, 강도는 터치 수와 가격 밀집도 기반 참고값입니다.")
    print("  ※ 매매 신호가 아니라 관찰 레벨입니다.\n")

    for r in all_results:
        curr = r['curr']
        asset_type = r['asset_type']
        print(f"  {r['name']}  현재가: {fmt_level(curr, asset_type)}")
        print(f"    데이터 출처: {_source_text(r)}")
        if r.get('series_scale_check'):
            print(f"    ⚠ {SCALE_CHECK_MESSAGE}")
        if r.get('data_warnings'):
            for w in r.get('data_warnings', []):
                print(f"    ⚠ {w}")
            print("    지지·저항: 신뢰 제한 — 원천 가격 데이터 이상으로 계산 제외\n")
            continue

        if _is_limited_asset(asset_type):
            print("    지지·저항: 해석 제한 — 현금성/금리형 상품은 일반 지지·저항 해석 부적합")
            print("    근접 상단 관찰선: N/A")
            print("    근접 하단 관찰선: N/A\n")
            continue

        if _is_macro(asset_type):
            fmt = _mk_fmt(asset_type)
            print("    매크로 관찰선 — 일반 지지·저항이 아니라 환율/금리/변동성 부담 레벨 참고")
            print("    근접 상단 관찰선:")
            print(_obs_lines(r.get('near_upper'), fmt))
            print("    근접 하단 관찰선:")
            print(_obs_lines(r.get('near_lower'), fmt))
            long_refs = (r.get('long_upper') or []) + (r.get('long_lower') or [])
            if long_refs:
                print("    장기 참고선:")
                print(_obs_lines(long_refs, fmt))
            print()
            continue

        print(f"  {'─'*50}")
        print(f"    [저항 레벨]")
        if r['resistances']:
            for lv in reversed(r['resistances']):
                pct = nearest_pct(curr, lv)
                print(f"    {fmt_level(lv, asset_type)}  → +{pct:.1f}%")
        else:
            print(f"    근접 저항 부족 — 52주 고점/심리 가격대를 상단 관찰선으로 참고")
        print(f"  {'─'*50}")
        print(f"    ▶ 현재가  {fmt_level(curr, asset_type)}")
        print(f"  {'─'*50}")
        print(f"    [지지 레벨]")
        if r['supports']:
            for lv in reversed(r['supports']):
                pct = nearest_pct(curr, lv)
                print(f"    {fmt_level(lv, asset_type)}  → {pct:.1f}%")
        else:
            print(f"    지지 공백 — 52주 저점/심리 가격대를 하단 관찰선으로 참고")

        fmt = _mk_fmt(asset_type)
        print(f"\n  근접 상단 관찰선: {_obs_text(r.get('near_upper'), fmt)}")
        print(f"  근접 하단 관찰선: {_obs_text(r.get('near_lower'), fmt)}")
        long_refs = (r.get('long_upper') or []) + (r.get('long_lower') or [])
        if long_refs:
            print(f"  장기 참고선: {_obs_text(long_refs, fmt)}")

        trend = r.get('trend', {})
        box = r.get('box', {})
        previous_high = r.get('previous_high', {})
        breakout = r.get('breakout', {})
        print("\n  [추세]")
        print(f"  - 상태: {trend.get('status', '판단 제한')}")
        print(f"  - 기준: {trend.get('basis', '50일선, 200일선, 최근 고점/저점 흐름')}")
        print(
            f"  - 현재가 vs MA50 / MA200: "
            f"MA50 {trend.get('ma50_side', 'N/A')} ({_fmt_optional(fmt, trend.get('ma50'))}) / "
            f"MA200 {trend.get('ma200_side', 'N/A')} ({_fmt_optional(fmt, trend.get('ma200'))})"
        )
        print(f"  - 중장기: {trend.get('long_term', '판단 제한')} / {trend.get('flow', '')}")
        if trend.get('kr_ma'):
            print(f"  - 이동평균: {trend.get('kr_ma')}")
        print(f"  박스: 상단 {_fmt_optional(fmt, box.get('box_high'))} / 하단 {_fmt_optional(fmt, box.get('box_low'))}")
        print(f"  박스 상태: {box.get('status', '판단 제한')}")
        print(f"  {previous_high.get('text', '전고점: N/A')}")
        print(f"  {breakout.get('text', '돌파 확인: N/A')}")

        h52 = r['high_52w']
        l52 = r['low_52w']
        high_pct = nearest_pct(curr, h52)
        low_pct  = nearest_pct(curr, l52)
        print(f"\n  52주 고점: {fmt_level(h52, asset_type)}  ({high_pct:+.1f}%)")
        print(f"  52주 저점: {fmt_level(l52, asset_type)}  ({low_pct:+.1f}%)")

        if (h52 != l52 and not np.isnan(h52) and not np.isnan(l52)
                and not np.isnan(curr)):
            pos_pct = (curr - l52) / (h52 - l52) * 100
            pos_pct = max(0.0, min(100.0, pos_pct))
            bar_len = 30
            filled  = int(pos_pct / 100 * bar_len)
            bar = '[' + '█' * filled + '░' * (bar_len - filled) + ']'
            print(f"  52주 위치: {bar} {pos_pct:.0f}%")
        print()

    # HTML 저장 및 브라우저 오픈
    html = generate_html(all_results, timestamp)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    os.makedirs(out_dir, exist_ok=True)
    latest_html = os.path.join(out_dir, 'support_resistance_latest.html')
    latest_txt = os.path.join(out_dir, 'support_resistance_latest_summary.txt')
    with open(latest_html, 'w', encoding='utf-8') as f:
        f.write(html)
    with open(latest_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(build_summary_lines(all_results)) + '\n')

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='support_resistance_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    print(f"  최신 요약 저장: {latest_txt}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")

if __name__ == '__main__':
    main()
