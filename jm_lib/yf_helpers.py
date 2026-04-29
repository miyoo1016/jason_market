"""yfinance 가격 데이터 통합 헬퍼

CLAUDE.md 가격 데이터 로직 준수:
- 한국 ETF: fast_info.last_price (정규장)
- 미국 주식/ETF: history(1d, 1m, prepost=True) (프리·애프터 포함)
- 선물(=F)/FX(=X)/지수(^)/크립토: fast_info.last_price (24H 실시간)

설계 원칙:
- 각 함수는 단일 책임 (Single Responsibility)
- 빌딩 블록으로 사용 (calling 코드가 조합)
- 모듈별 커스터마이징 가능 (override 인자)
"""

import yfinance as yf
from datetime import datetime, timezone


# ═══ 티커 분류 ═══

def classify_ticker(ticker: str, custom_equity_set: set = None) -> dict:
    """티커를 자산 유형별로 분류

    Args:
        ticker: yfinance 티커 (예: 'SPY', 'GC=F', 'USDKRW=X', '^VIX', 'BTC-USD', '379810.KS')
        custom_equity_set: 모듈별로 명시적으로 equity로 취급할 티커 집합 (선택)

    Returns:
        {'is_kr', 'is_equity', 'is_futures', 'is_fx', 'is_index', 'is_crypto'}
    """
    is_kr = ticker.endswith('.KS')
    is_futures = ticker.endswith('=F')
    is_fx = ticker.endswith('=X')
    is_index = ticker.startswith('^')
    is_crypto = ticker in ('BTC-USD', 'ETH-USD', 'BTC-KRW')

    # custom_equity_set이 주어지면 그 기준으로, 아니면 자동 판정
    if custom_equity_set is not None:
        is_equity = ticker in custom_equity_set
    else:
        is_equity = not (is_kr or is_futures or is_fx or is_index or is_crypto)

    return {
        'is_kr': is_kr,
        'is_equity': is_equity,
        'is_futures': is_futures,
        'is_fx': is_fx,
        'is_index': is_index,
        'is_crypto': is_crypto,
    }


# ═══ 가격 조회 ═══

def get_current_price(ticker: str, is_equity: bool = None) -> float:
    """현재가 조회 (CLAUDE.md 로직 준수)

    Args:
        ticker: yfinance 티커
        is_equity: True면 미국 주식/ETF 로직 (prepost 포함), None이면 자동 판정

    Returns:
        현재가 (float) 또는 None (실패 시)

    Logic:
        - 한국 ETF (.KS) 또는 미국 주식/ETF: 1분봉 prepost 우선
        - 선물/FX/지수/크립토: fast_info.last_price (24H)
    """
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info

        # 자동 판정
        if is_equity is None:
            cls = classify_ticker(ticker)
            # 한국 ETF는 정규장만이지만 fast_info가 더 정확
            # 미국 주식/ETF는 프리·애프터 포함을 위해 history 사용
            is_equity = cls['is_equity']

        # 미국 주식/ETF: 프리·애프터 포함 (1분봉)
        if is_equity:
            try:
                h1m = t.history(period='1d', interval='1m', prepost=True)
                if not h1m.empty:
                    return float(h1m['Close'].iloc[-1])
            except Exception:
                pass

        # Fallback: fast_info.last_price (한국 정규장, 선물/FX/지수/크립토 24H)
        return float(getattr(fi, 'last_price', None) or 0) or None
    except Exception:
        return None


def get_prev_close(ticker: str, curr: float = None) -> float:
    """전일 종가 조회 (선물/FX/지수 특수 로직 포함)

    Args:
        ticker: yfinance 티커
        curr: 현재가 (있으면 마감 vs 거래 중 판단에 사용)

    Returns:
        전일 종가 (float) 또는 None (실패 시)

    Logic:
        - 한국/미국 주식·ETF: fast_info.previous_close
        - 선물/FX/지수/크립토: history(5d) 분석
            * 현재가 ≈ 마지막 종가 → 마감 상태 → close[-2] 사용
            * 현재가 ≠ 마지막 종가 → 거래 중 → close[-1] 사용
    """
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        cls = classify_ticker(ticker)

        # 한국/미국 주식·ETF
        if cls['is_kr'] or cls['is_equity']:
            prev = getattr(fi, 'previous_close', None)
            if prev:
                return float(prev)

        # 선물/FX/지수/크립토 또는 fallback
        hist = t.history(period='5d')
        if hist.empty:
            return None

        daily_last = float(hist['Close'].iloc[-1])

        # curr이 주어졌고 마지막 일봉 종가와 거의 같으면 마감 상태
        if curr is not None and daily_last > 0:
            if abs(curr - daily_last) / daily_last < 0.001:
                # 마감 상태 → 전일 종가는 [-2]
                if len(hist) >= 2:
                    return float(hist['Close'].iloc[-2])

        return daily_last  # 거래 중 또는 curr 미주어짐
    except Exception:
        return None


def get_open_today_utc(ticker: str) -> float:
    """오늘 00:00 UTC 시가 조회 (글로벌 자산용)

    글로벌 자산(선물/FX/크립토)의 등락률 계산 시 GMT 00:00 시가 기준 사용.
    Fallback 우선순위:
        1. history(2d, 1h)에서 00:00 UTC 이후 첫 시가
        2. fast_info.open (오늘 시가)
        3. None

    Args:
        ticker: yfinance 티커

    Returns:
        오늘 시가 (float) 또는 None
    """
    try:
        t = yf.Ticker(ticker)

        # 1차: 1시간봉에서 00:00 UTC 시가 추출
        try:
            h_int = t.history(period='2d', interval='1h')
            if not h_int.empty:
                h_int.index = h_int.index.tz_convert('UTC')
                today_utc = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                today_data = h_int.loc[h_int.index >= today_utc]
                if not today_data.empty:
                    return float(today_data['Open'].iloc[0])
        except Exception:
            pass

        # 2차: fast_info.open (fallback - 일부 인덱스/티커는 1h 데이터 없음)
        try:
            fi = t.fast_info
            open_val = getattr(fi, 'open', None)
            if open_val:
                return float(open_val)
        except Exception:
            pass

        return None
    except Exception:
        return None


# ═══ 통합 데이터 ═══

def get_price_data(ticker: str, is_equity: bool = None, is_global: bool = False) -> dict:
    """현재가 + 전일종가 + 시가 통합 조회

    Args:
        ticker: yfinance 티커
        is_equity: 미국 주식/ETF 여부 (prepost 처리)
        is_global: 글로벌 자산 여부 (00:00 UTC 시가 사용)

    Returns:
        {'curr': float, 'prev': float, 'open_utc': float (선택), 'pct': float (선택)}
        실패 시 None
    """
    curr = get_current_price(ticker, is_equity=is_equity)
    if curr is None:
        return None

    prev = get_prev_close(ticker, curr=curr)
    if prev is None:
        return None

    result = {'curr': curr, 'prev': prev}

    # 글로벌 자산: 00:00 UTC 시가 추가
    if is_global:
        open_utc = get_open_today_utc(ticker)
        if open_utc:
            result['open_utc'] = open_utc
            result['pct'] = (curr - open_utc) / open_utc * 100

    if 'pct' not in result:
        result['pct'] = (curr - prev) / prev * 100

    return result


__all__ = [
    'classify_ticker',
    'get_current_price',
    'get_prev_close',
    'get_open_today_utc',
    'get_price_data',
]
