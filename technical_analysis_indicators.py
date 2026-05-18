"""기술분석 지표 계산 라이브러리
RSI · MACD · 볼린저밴드 · 이동평균 · 스토캐스틱 · ATR · ADX · OBV · 피봇포인트 · 매물대"""

import numpy as np
import pandas as pd


# ═══ 기본 지표 ═══

def _ma(close, p):
    """p기간 단순이동평균"""
    return close.rolling(p).mean()


def calc_rsi(close, p=14):
    """RSI (Relative Strength Index, 14기간)"""
    d = close.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    ag = g.ewm(com=p-1, min_periods=p).mean()
    al = l.ewm(com=p-1, min_periods=p).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - 100/(1+rs)
    return float(rsi.iloc[-1]) if not rsi.empty else None


def calc_macd(close, fast=12, slow=26, sig=9):
    """MACD (Moving Average Convergence Divergence)

    Returns:
        (macd_line, signal_line, histogram)
    """
    ml = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sl = ml.ewm(span=sig, adjust=False).mean()
    return float(ml.iloc[-1]), float(sl.iloc[-1]), float((ml-sl).iloc[-1])


def calc_bollinger(close, p=20, std=2):
    """볼린저 밴드 (20기간, 2σ)

    Returns:
        (upper_band, mid_band, lower_band, percent_b)
    """
    ma = close.rolling(p).mean()
    sd = close.rolling(p).std()
    u, l = ma+std*sd, ma-std*sd
    c = float(close.iloc[-1])
    pct_b = (c - float(l.iloc[-1])) / (float(u.iloc[-1]) - float(l.iloc[-1])) * 100
    return float(u.iloc[-1]), float(ma.iloc[-1]), float(l.iloc[-1]), pct_b


def calc_stochastic(hist, k=14, d=3):
    """Stochastic Oscillator (K, D)

    Args:
        hist: OHLC 데이터 (High, Low, Close 필수)
        k: K기간
        d: D평활기간

    Returns:
        (K값, D값)
    """
    lo = hist['Low'].rolling(k).min()
    hi = hist['High'].rolling(k).max()
    denom = (hi - lo).replace(0, np.nan)
    K = (hist['Close'] - lo) / denom * 100
    D = K.rolling(d).mean()
    kv = K.dropna()
    dv = D.dropna()
    return (float(kv.iloc[-1]) if not kv.empty else None,
            float(dv.iloc[-1]) if not dv.empty else None)


def calc_atr(hist, p=14):
    """Average True Range (14기간)

    Args:
        hist: OHLC 데이터

    Returns:
        (atr_value, atr_percentage)
    """
    h, l, pc = hist['High'], hist['Low'], hist['Close'].shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=p, adjust=False).mean()
    v = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else None
    curr = float(hist['Close'].iloc[-1])
    return v, (v/curr*100 if v and curr else None)


def calc_adx(hist, p=14):
    """ADX + DI (Average Directional Index, Wilder's smoothing)

    Args:
        hist: OHLC 데이터

    Returns:
        (adx_value, plus_di, minus_di)
    """
    h = hist['High'].values
    l = hist['Low'].values
    c = hist['Close'].values
    n = len(c)
    if n < p + 1:
        return None, None, None

    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)

    for i in range(1, n):
        up = h[i] - h[i-1]
        down = l[i-1] - l[i]
        plus_dm[i] = up if up > down and up > 0 else 0
        minus_dm[i] = down if down > up and down > 0 else 0
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))

    # Wilder smoothing via ewm
    s = pd.Series
    atr_s = s(tr).ewm(span=p, adjust=False).mean()
    pdm_s = s(plus_dm).ewm(span=p, adjust=False).mean()
    mdm_s = s(minus_dm).ewm(span=p, adjust=False).mean()
    pdi = (pdm_s / atr_s.replace(0, np.nan) * 100).fillna(0)
    mdi = (mdm_s / atr_s.replace(0, np.nan) * 100).fillna(0)
    dx = ((pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan) * 100).fillna(0)
    adx = dx.ewm(span=p, adjust=False).mean()

    adx_val = float(adx.iloc[-1]) if not adx.empty else None
    plus_di = float(pdi.iloc[-1]) if not pdi.empty else None
    minus_di = float(mdi.iloc[-1]) if not mdi.empty else None
    return adx_val, plus_di, minus_di


def calc_obv(hist):
    """OBV (On-Balance Volume) 추세 + 다이버전스 탐지

    Returns:
        (trend_str, divergence_str or None)
    """
    c = hist['Close'].values
    vol = hist['Volume'].values if 'Volume' in hist.columns else np.ones(len(c))
    obv = np.zeros(len(c))

    for i in range(1, len(c)):
        if c[i] > c[i-1]:
            obv[i] = obv[i-1] + vol[i]
        elif c[i] < c[i-1]:
            obv[i] = obv[i-1] - vol[i]
        else:
            obv[i] = obv[i-1]

    trend = 'flat'
    if len(obv) >= 20:
        r, m = obv[-5:].mean(), obv[-20:-5].mean()
        if r > m*1.01:
            trend = 'up'
        elif r < m*0.99:
            trend = 'down'

    # 다이버전스 탐지 (최근 5일 vs 이전 15일)
    divergence = None
    if len(c) >= 20:
        price_recent = c[-5:].mean()
        price_prev = c[-20:-5].mean()
        obv_recent = obv[-5:].mean()
        obv_prev = obv[-20:-5].mean()
        price_up = price_recent > price_prev * 1.005
        price_dn = price_recent < price_prev * 0.995
        obv_up = obv_recent > obv_prev * 1.001
        obv_dn = obv_recent < obv_prev * 0.999

        if price_up and obv_dn:
            divergence = '⚠ 하락다이버전스 (가격↑·OBV↓)'
        elif price_dn and obv_up:
            divergence = '✅ 상승다이버전스 (가격↓·OBV↑)'

    return trend, divergence


def calc_pivot_weekly(hist):
    """주간 피봇 포인트 (지난 주 5거래일 데이터 사용)

    Returns:
        {'P': float, 'R1': float, 'R2': float, 'S1': float, 'S2': float} or None
    """
    if len(hist) < 10:
        return None
    week = hist.tail(10).head(5)
    H = float(week['High'].max())
    L = float(week['Low'].min())
    C = float(week['Close'].iloc[-1])
    P = (H + L + C) / 3
    return {'P': P, 'R1': 2*P-L, 'R2': P+(H-L), 'S1': 2*P-H, 'S2': P-(H-L)}


def calc_volume_profile(hist, bins=12):
    """매물대 분석 (최근 데이터 기반)

    Args:
        hist: OHLC 데이터
        bins: 가격 구간 개수

    Returns:
        (profile_list, poc_price)
    """
    c = hist['Close'].values
    v = hist['Volume'].values if 'Volume' in hist.columns else np.ones(len(c))
    v = np.where(v > 0, v, 1)
    mn, mx = c.min(), c.max()

    if mx == mn:
        return [], None

    edges = np.linspace(mn, mx, bins+1)
    profile = []

    for i in range(bins):
        lo, hi = edges[i], edges[i+1]
        mask = (c >= lo) & (c <= hi)
        vol = float(v[mask].sum())
        profile.append({'price': round((lo+hi)/2, 4), 'volume': vol})

    mx_v = max(p['volume'] for p in profile) or 1
    for p in profile:
        p['pct'] = round(p['volume']/mx_v*100, 1)

    poc_price = max(profile, key=lambda x: x['volume'])['price'] if profile else None
    return profile, poc_price


def calc_composite_score(r):
    """종합 기술상태 점수 (-7 ~ +7)

    Args:
        r: 지표 결과 딕셔너리

    Returns:
        {'trend_score': int, 'momentum_score': int, 'volume_score': int,
         'total': int, 'label': str, 'color': str, 'bar_pct': int}
    """
    # 추세 점수
    trend_score = 0
    if r.get('ma20'):
        trend_score += 1 if r['curr'] > r['ma20'] else -1
    if r.get('ma60'):
        trend_score += 1 if r['curr'] > r['ma60'] else -1
    if r.get('ma200'):
        trend_score += 1 if r['curr'] > r['ma200'] else -1

    # 모멘텀 점수
    mom = 0
    rsi = r.get('rsi')
    if rsi is not None:
        if rsi < 30:
            mom += 2
        elif rsi < 45:
            mom += 1
        elif rsi > 70:
            mom -= 2
        elif rsi > 55:
            mom -= 1

    if r.get('macd') is not None and r.get('macd_sig') is not None:
        mom += 1 if r['macd'] > r['macd_sig'] else -1

    mom = max(-3, min(3, mom))

    # 거래량 점수
    obv_trend = r.get('obv_trend', 'flat')
    vol_score = 1 if obv_trend == 'up' else (-1 if obv_trend == 'down' else 0)

    total = trend_score + mom + vol_score

    # 레이블 및 색상: 기술상태 표현만 사용
    if total >= 5:
        label, color = '강한 상승우위', '#00838f'
    elif total >= 3:
        label, color = '상승우위', '#26a69a'
    elif total >= 1:
        label, color = '약한 상승우위', '#80cbc4'
    elif total >= -1:
        label, color = '중립', '#90a4ae'
    elif total >= -3:
        label, color = '약한 하락우위', '#ff8a65'
    elif total >= -5:
        label, color = '하락우위', '#e65100'
    else:
        label, color = '강한 하락우위', '#c62828'

    bar_pct = int((total + 7) / 14 * 100)

    return {
        'trend_score': trend_score,
        'momentum_score': mom,
        'volume_score': vol_score,
        'total': total,
        'label': label,
        'color': color,
        'bar_pct': bar_pct,
    }


def safe_float(s):
    """NaN 체크하여 float 변환"""
    return round(float(s), 6) if not pd.isna(s) else None


def ma_series(close, p, n=60):
    """p기간 이동평균의 최근 n개 값"""
    s = close.rolling(p).mean().tail(n)
    return [safe_float(v) for v in s]


def classify_asset(name, ticker):
    """기술지표 해석용 최소 자산 분류."""
    n = (name or '').upper()
    t = (ticker or '').upper()
    if 'CD금리' in (name or '') or t == '357870.KS' or 'CASH' in t:
        return 'cash_like'
    if t in ('USDKRW=X', 'KRW=X') or t.endswith('=X'):
        return 'macro_fx'
    if t in ('^TNX', '^FVX', '^IRX') or '10년' in (name or '') or '금리' in (name or ''):
        return 'macro_rate'
    if t == '^VIX' or 'VIX' in n:
        return 'volatility_index'
    if t in ('BTC-USD', 'ETH-USD') or '-USD' in t and 'BTC' in t:
        return 'crypto'
    if t in ('GC=F', 'CL=F', 'BZ=F', 'SI=F', 'HG=F') or 'COMMODITY' in n:
        return 'commodity'
    if t.startswith('^') or t in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
        return 'index_or_futures'
    return 'equity_or_etf'


def has_reliable_volume(hist, asset_type):
    """OBV 해석이 가능한 거래량인지 판정."""
    if asset_type in ('macro_fx', 'macro_rate', 'volatility_index', 'index_or_futures'):
        return False
    if hist is None or 'Volume' not in hist.columns:
        return False
    vol = hist['Volume'].tail(90)
    if vol.empty:
        return False
    zero_ratio = float((vol.fillna(0) <= 0).mean())
    return zero_ratio < 0.30 and float(vol.fillna(0).sum()) > 0


def bb_label(pct_b):
    """볼린저밴드 %B 구간 라벨."""
    if pct_b is None:
        return 'N/A'
    if pct_b >= 100:
        return '상단 돌파'
    if pct_b >= 85:
        return '상단권'
    if pct_b >= 65:
        return '중립 상단'
    if pct_b >= 35:
        return '중립'
    if pct_b >= 15:
        return '중립 하단'
    if pct_b >= 0:
        return '하단권'
    return '하단 이탈'


def momentum_label(macd, macd_sig, hist=None):
    """MACD 상태 라벨."""
    if macd is None or macd_sig is None:
        return '중립'
    if hist is not None and abs(hist) < 1e-12:
        return '중립'
    return '상방 모멘텀' if macd > macd_sig else '하방 모멘텀' if macd < macd_sig else '중립'


def rsi_label(value, asset_type):
    if value is None:
        return 'N/A'
    high = '상단권' if asset_type in ('macro_fx', 'macro_rate', 'volatility_index') else '과열권'
    low = '하단권' if asset_type in ('macro_fx', 'macro_rate', 'volatility_index') else '침체권'
    return high if value >= 70 else low if value <= 30 else '중립'


def stoch_label(value, asset_type):
    if value is None:
        return 'N/A'
    high = '상단권' if asset_type in ('macro_fx', 'macro_rate', 'volatility_index') else '과열권'
    low = '하단권' if asset_type in ('macro_fx', 'macro_rate', 'volatility_index') else '침체권'
    return high if value >= 80 else low if value <= 20 else '중립'


def obv_label(trend, reliable=True):
    if not reliable:
        return 'N/A — 거래량 신뢰도 낮음'
    if trend == 'up':
        return '상승 — 거래량 동반 가능'
    if trend == 'down':
        return '하락 — 거래량 약화 가능'
    return '중립'


def pivot_position_label(pivot, curr):
    if not pivot or curr is None:
        return 'N/A'
    try:
        s1, p, r1, r2 = pivot['S1'], pivot['P'], pivot['R1'], pivot['R2']
        if curr > r2:
            return '현재가 R2 위 — 단기 상단 돌파 구간'
        if curr >= r1:
            return '현재가 R1~R2 — 상단권'
        if curr >= p:
            return '현재가 P~R1 — 중립 상단'
        if curr >= s1:
            return '현재가 S1~P — 중립 하단'
        return '현재가 S1 아래 — 약세 구간'
    except Exception:
        return 'N/A'


__all__ = [
    'calc_rsi', 'calc_macd', 'calc_bollinger', 'calc_stochastic',
    'calc_atr', 'calc_adx', 'calc_obv', 'calc_pivot_weekly',
    'calc_volume_profile', 'calc_composite_score',
    'safe_float', 'ma_series', '_ma',
    'classify_asset', 'has_reliable_volume', 'bb_label', 'momentum_label',
    'rsi_label', 'stoch_label', 'obv_label', 'pivot_position_label',
]
