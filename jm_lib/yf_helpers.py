from __future__ import annotations
"""yfinance 가격 데이터 통합 헬퍼
Yahoo Finance v8 API — curl 직접 호출 (429 Rate-Limit 우회)

가격 로직:
- 미국/한국 주식·ETF·지수: regularMarketPrice vs 역사 일봉 종가[-1 or -2] 등락률
  (chartPreviousClose 메타값은 한국 자산에서 수주 전 값이 나오는 버그가 있어 사용 안 함)
- 선물(=F)/FX(=X)/크립토: regularMarketPrice vs 00:00 UTC 시가 등락률
"""

import subprocess
import json
import logging
import requests
from datetime import datetime, timezone, timedelta

logging.getLogger('yfinance').setLevel(logging.CRITICAL)

_UA  = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart'


# ═══ 티커 분류 ═══

def classify_ticker(ticker: str, custom_equity_set: set = None) -> dict:
    """티커를 자산 유형별로 분류"""
    is_kr      = ticker.endswith('.KS')
    is_futures = ticker.endswith('=F')
    is_fx      = ticker.endswith('=X')
    is_index   = ticker.startswith('^')
    is_crypto  = ticker in ('BTC-USD', 'ETH-USD', 'BTC-KRW')

    if custom_equity_set is not None:
        is_equity = ticker in custom_equity_set
    else:
        is_equity = not (is_kr or is_futures or is_fx or is_index or is_crypto)

    return {
        'is_kr':      is_kr,
        'is_equity':  is_equity,
        'is_futures': is_futures,
        'is_fx':      is_fx,
        'is_index':   is_index,
        'is_crypto':  is_crypto,
    }


# ═══ 내부 API 호출 ═══

def _chart(ticker: str, interval: str = '1d', range_: str = '5d') -> dict | None:
    """Yahoo Finance v8 chart API (curl) → result[0] 딕셔너리 반환"""
    try:
        url = f'{_BASE}/{ticker}?interval={interval}&range={range_}'
        r = subprocess.run(
            ['curl', '-s', '-A', _UA, url],
            capture_output=True, timeout=12
        )
        data = json.loads(r.stdout.decode('utf-8', errors='replace'))
        results = data.get('chart', {}).get('result', None)
        if results:
            return results[0]
    except Exception:
        pass
    return None


def _get_utc_open(ticker: str) -> float | None:
    """오늘 00:00 UTC 이후 첫 시가 조회 (글로벌 자산용)"""
    try:
        result = _chart(ticker, interval='1h', range_='2d')
        if not result:
            return None
        timestamps = result.get('timestamp', [])
        opens = result.get('indicators', {}).get('quote', [{}])[0].get('open', [])
        today_utc = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        for ts, op in zip(timestamps, opens):
            if ts >= today_utc and op is not None:
                return float(op)
    except Exception:
        pass
    return None


# ═══ KST 시간대 판별 ═══

def _kst_session() -> str:
    """현재 KST 시간 기준 미국 주식 거래 세션 반환
    Returns: 'regular' | 'pre' | 'post' | 'blue_ocean'
    """
    KST = timezone(timedelta(hours=9))
    h = datetime.now(KST).hour + datetime.now(KST).minute / 60
    if 22.5 <= h or h < 5:
        return 'regular'       # 정규장    22:30~05:00 KST
    elif 5 <= h < 9:
        return 'post'          # 애프터마켓 05:00~09:00 KST
    elif 17 <= h < 22.5:
        return 'pre'           # 프리마켓  17:00~22:30 KST
    else:
        return 'blue_ocean'    # 주간거래  09:00~17:00 KST (블루오션)


# ═══ Pyth Network — 블루오션/프리/애프터마켓 가격 ═══

# 세션별 피드 우선순위 키워드
_PYTH_SESSION_PREF = {
    'blue_ocean': ['OVERNIGHT'],
    'pre':        ['PRE MARKET', 'OVERNIGHT'],
    'post':       ['POST MARKET', 'OVERNIGHT'],
    'regular':    [],
}

def _pyth_curr(ticker: str, session: str, session_only: bool = True,
               max_age_min: int = 30) -> float | None:
    """Pyth Network에서 세션별 최적 피드 현재가 조회

    Args:
        session_only: True이면 세션 특화 피드(OVERNIGHT/PRE/POST)만 사용.
                      False이면 세션 피드 없을 때 일반 정규 피드 fallback.
        max_age_min:  publish_time이 이 분(분) 이상 지난 데이터는 stale로 판단해 None 반환.

    - blue_ocean: OVERNIGHT 피드 → 블루오션 근사 시세
    - pre/post: PRE MARKET / POST MARKET 피드
    - regular: Pyth 미사용
    """
    pref = _PYTH_SESSION_PREF.get(session, [])

    try:
        # 1. 피드 검색
        r = requests.get(
            f'https://hermes.pyth.network/v2/price_feeds?query={ticker}&asset_type=equity',
            timeout=8
        )
        feeds = r.json()
        my_feeds = [f for f in feeds
                    if f.get('attributes', {}).get('base', '').upper() == ticker.upper()]
        if not my_feeds:
            return None

        # 세션 우선순위 키워드로 피드 선택
        chosen_id = None
        for keyword in pref:
            for f in my_feeds:
                desc = f.get('attributes', {}).get('description', '').upper()
                if keyword in desc:
                    chosen_id = f.get('id')
                    break
            if chosen_id:
                break

        # 세션 특화 피드 없음
        if not chosen_id:
            if session_only:
                return None  # 선물 추정으로 fallback하도록 None 반환
            # session_only=False: 일반 정규 피드 사용
            for f in my_feeds:
                desc = f.get('attributes', {}).get('description', '').upper()
                if not any(k in desc for k in ['OVERNIGHT', 'PRE MARKET', 'POST MARKET']):
                    chosen_id = f.get('id')
                    break
            if not chosen_id:
                chosen_id = my_feeds[0].get('id')

        if not chosen_id:
            return None

        # 2. 가격 조회
        r2 = requests.get(
            f'https://hermes.pyth.network/v2/updates/price/latest?ids[]={chosen_id}',
            timeout=8
        )
        parsed = r2.json().get('parsed', [None])[0]
        if parsed:
            pd = parsed.get('price', {})
            price_raw = int(pd.get('price', 0))
            expo = int(pd.get('expo', 0))
            price = price_raw * (10 ** expo)
            if price <= 0:
                return None

            # ── 신선도 체크: publish_time이 max_age_min 분 이내인지 확인 ──
            publish_time = pd.get('publish_time', 0)
            if publish_time:
                age_min = (datetime.now(timezone.utc).timestamp() - publish_time) / 60
                if age_min > max_age_min:
                    return None  # stale 데이터 → 선물 추정으로 fallback

            return float(price)
    except Exception:
        pass
    return None


def _us_equity_price_data(ticker: str) -> dict | None:
    """미국 직투 종목 전용: range=2d 역사 종가로 정확한 전일 종가 계산

    - chartPreviousClose 메타값은 range에 따라 변하는 잘못된 값 → 사용 안 함
    - range=2d 일봉 closes[0]=어제, closes[1]=오늘 → _resolve_prev로 전일 종가 정확 추출

    세션별 curr/prev 로직:
    - 정규장 (22:30~05:00 KST): Yahoo regularMarketPrice 실시간 / prev = 전일 종가
    - 블루오션 (09:00~17:00 KST): 미국 장 완전 마감 상태 → Yahoo 마감가를 curr로 사용
                                   prev = 그 전날 종가 / 선물 추정 없음 (Yahoo Finance 일치)
    - 프리마켓 (17:00~22:30 KST): Pyth PRE MARKET → 선물 추정 → Yahoo / prev = 마지막 종가
    - 애프터마켓 (05:00~09:00 KST): Pyth POST MARKET → 선물 추정 → Yahoo / prev = 마지막 종가
    """
    # Yahoo에서 curr + closes 준비
    result = _chart(ticker, interval='1d', range_='2d')
    if not result:
        return None

    meta       = result.get('meta', {})
    yahoo_curr = meta.get('regularMarketPrice')
    if not yahoo_curr:
        return None
    yahoo_curr = float(yahoo_curr)

    closes = _daily_closes(result)
    if not closes:
        return None

    session = _kst_session()

    # ── 블루오션 전용 경로 ────────────────────────────────────────────
    # 미국 장 완전 마감(한국 낮 시간) → QQQM 거래 없음
    # Yahoo regularMarketPrice = 가장 최근 정규장 종가 → 그대로 curr로 사용
    # prev = _resolve_prev: curr ≈ closes[-1] → closes[-2] (하루 전 종가) 반환
    # 결과: Yahoo Finance 앱 표시와 동일한 종가·등락률
    if session == 'blue_ocean':
        prev = _resolve_prev(yahoo_curr, closes)
        if not prev:
            return None
        pct = (yahoo_curr - prev) / prev * 100
        return {'curr': yahoo_curr, 'prev': prev, 'pct': pct}

    # ── prev 결정 (정규장 / 프리·애프터) ─────────────────────────────
    # 정규장: _resolve_prev 로 "오늘 장 중 vs 어제 종가" 정확 판단
    # 프리·애프터마켓: closes[-1] = 가장 최근 정규장 종가 (= 비교 기준점)
    if session == 'regular':
        prev = _resolve_prev(yahoo_curr, closes)
    else:
        prev = closes[-1]   # 가장 최근 정규장 종가 = pre/post 비교 기준

    if not prev:
        return None

    # ── curr 결정 (프리·애프터마켓만) ────────────────────────────────
    # 실제 거래가 이뤄지는 세션에서만 Pyth/선물 추정으로 현재가 보정
    curr = yahoo_curr
    if session != 'regular':
        # 1순위: Pyth 세션 특화 피드 (신선도 30분 이내만 사용)
        pyth = _pyth_curr(ticker, session, session_only=True, max_age_min=30)
        if pyth:
            curr = pyth
        else:
            # 2순위: 연관 선물 등락률 기반 추정 (QQQM→NQ=F, SPY→ES=F 등)
            est = _futures_estimate(ticker, prev)
            if est:
                curr = est
            else:
                # 3순위: Pyth 일반 피드 (staleness 관계없이 최후 수단)
                pyth_reg = _pyth_curr(ticker, session, session_only=False, max_age_min=120)
                if pyth_reg:
                    curr = pyth_reg
                # 4순위: yahoo_curr (정규장 종가) 그대로

    pct = (curr - prev) / prev * 100
    return {'curr': curr, 'prev': prev, 'pct': pct}


# ETF → 추종 선물 매핑 (Pyth overnight 피드 없는 종목용)
_ETF_FUTURES_MAP = {
    'QQQM': 'NQ=F',   # 나스닥 100
    'QQQ':  'NQ=F',
    'TQQQ': 'NQ=F',
    'SPY':  'ES=F',   # S&P500 (Pyth가 없을 때 fallback)
    'IVV':  'ES=F',
    'VOO':  'ES=F',
    'DIA':  'YM=F',   # 다우존스
}

def _futures_estimate(etf_ticker: str, last_close: float) -> float | None:
    """연관 선물의 전일 종가 대비 등락률로 ETF 블루오션/야간 현재가 추정

    Args:
        last_close: ETF의 가장 최근 정규장 종가 (블루오션 추정의 기준점)

    핵심 공식:
        ETF_est = last_close × (futures_curr / futures_prev_close)

    UTC 00:00 시가 기준 방식은 주말 개장 후 첫 몇 시간 동안 누락된
    시세 변동을 포착하지 못하는 문제가 있어 폐기.
    """
    futures = _ETF_FUTURES_MAP.get(etf_ticker.upper())
    if not futures:
        return None
    try:
        # 선물 일봉 2d: closes[-1] ≈ fut_curr (장 중) 또는 전 세션 종가
        result = _chart(futures, interval='1d', range_='2d')
        if not result:
            return None
        fut_curr_raw = result.get('meta', {}).get('regularMarketPrice')
        if not fut_curr_raw:
            return None
        fut_curr = float(fut_curr_raw)

        # 선물 전일 종가: _resolve_prev 로 정확히 추출
        fut_closes = _daily_closes(result)
        fut_prev = _resolve_prev(fut_curr, fut_closes)
        if not fut_prev or fut_prev <= 0:
            return None

        # ETF_est = ETF_last_close × (fut_curr / fut_prev)
        return round(last_close * (fut_curr / fut_prev), 4)
    except Exception:
        return None


# ═══ 가격 조회 (하위 호환용 개별 함수) ═══

def get_current_price(ticker: str, is_equity: bool = None) -> float | None:
    """현재가 조회"""
    result = _chart(ticker)
    if not result:
        return None
    price = result.get('meta', {}).get('regularMarketPrice')
    return float(price) if price else None


def get_prev_close(ticker: str, curr: float = None) -> float | None:
    """전일 종가 조회"""
    result = _chart(ticker)
    if not result:
        return None
    closes = _daily_closes(result)
    curr_price = curr or result.get('meta', {}).get('regularMarketPrice')
    if curr_price and closes:
        return _resolve_prev(float(curr_price), closes)
    meta = result.get('meta', {})
    prev = meta.get('chartPreviousClose') or meta.get('previousClose')
    return float(prev) if prev else None


def _daily_closes(result: dict) -> list:
    """역사 일봉 result에서 None 제거한 종가 리스트 반환"""
    try:
        q = result.get('indicators', {}).get('quote', [{}])[0]
        return [float(c) for c in q.get('close', []) if c is not None]
    except Exception:
        return []


def _resolve_prev(curr: float, closes: list) -> float | None:
    """
    역사 일봉 종가 리스트로 전일 종가 계산 (CLAUDE.md 원본 로직 유지)

    - closes[-1] ≈ curr (0.1% 이내) → 장 마감 상태 → prev = closes[-2]
    - closes[-1] ≠ curr             → 장 중/프리마켓 → prev = closes[-1]
    """
    if not closes:
        return None
    last = closes[-1]
    if len(closes) >= 2 and abs(curr - last) / last < 0.001:
        return closes[-2]
    return last


def get_open_today_utc(ticker: str) -> float | None:
    """오늘 00:00 UTC 시가 조회"""
    return _get_utc_open(ticker)


# ═══ 통합 데이터 (메인 진입점) ═══

def get_price_data(ticker: str, is_equity: bool = None, is_global: bool = False) -> dict | None:
    """현재가 + 전일종가 + 등락률 통합 조회

    자산 유형별 로직:
    - 미국 직투 (US equity): v7 quote API로 KST 시간대별 pre/post/regular 가격 선택
    - 한국 주식·ETF·지수 (.KS, ^KS): 역사 일봉 종가 기반 (chartPreviousClose 버그 우회)
    - 글로벌 자산 (선물=F, FX=X, BTC, ^VIX 등): 00:00 UTC 시가 기준 등락률

    Returns:
        {'curr': float, 'prev': float, 'pct': float} 또는 None
    """
    is_kr      = ticker.endswith('.KS')
    is_futures = ticker.endswith('=F')
    is_fx      = ticker.endswith('=X')
    is_index   = ticker.startswith('^')
    is_crypto  = ticker in ('BTC-USD', 'ETH-USD', 'BTC-KRW')

    # is_equity 미지정 시 자동 감지 (US equity = KR/선물/FX/지수/크립토 아닌 것)
    if is_equity is None:
        is_equity = not (is_kr or is_futures or is_fx or is_index or is_crypto)

    # ── 미국 직투 종목: 시간대별 pre/post market 가격 ──────────────────
    if is_equity and not is_kr:
        return _us_equity_price_data(ticker)

    # ── 글로벌 자산 (선물/FX/크립토/일부 지수): 00:00 UTC 시가 기준 ──
    if is_global:
        result = _chart(ticker)
        if not result:
            return None
        meta = result.get('meta', {})
        curr = meta.get('regularMarketPrice')
        if not curr:
            return None
        curr = float(curr)
        open_utc = _get_utc_open(ticker)
        if open_utc and open_utc > 0:
            pct = (curr - open_utc) / open_utc * 100
            fb  = meta.get('chartPreviousClose') or meta.get('previousClose')
            return {'curr': curr, 'prev': float(fb) if fb else curr, 'pct': pct}
        # UTC open 실패 시 역사 종가 fallback
        closes = _daily_closes(result)
        prev = _resolve_prev(curr, closes)
        if not prev:
            return None
        return {'curr': curr, 'prev': prev, 'pct': (curr - prev) / prev * 100}

    # ── 한국 주식·ETF·지수: 역사 일봉 종가 기반 ──────────────────────
    result = _chart(ticker)
    if not result:
        return None

    meta  = result.get('meta', {})
    curr  = meta.get('regularMarketPrice')
    if not curr:
        return None
    curr = float(curr)

    closes = _daily_closes(result)
    prev   = _resolve_prev(curr, closes)

    # fallback: chartPreviousClose (스탈 가능성 있으나 최후 수단)
    if not prev:
        fb = meta.get('chartPreviousClose') or meta.get('previousClose')
        prev = float(fb) if fb else None

    if not prev:
        return None

    pct = (curr - prev) / prev * 100
    return {'curr': curr, 'prev': prev, 'pct': pct}


__all__ = [
    'classify_ticker',
    'get_current_price',
    'get_prev_close',
    'get_open_today_utc',
    'get_price_data',
]
