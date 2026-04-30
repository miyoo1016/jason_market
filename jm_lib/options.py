"""Black-Scholes 옵션 Greeks 및 Max Pain 계산 통합 라이브러리

CLAUDE.md 가격 데이터 로직 준수:
- Greeks(Vanna, Charm, Gamma) 계산용 공식 모듈
- 선물/인덱스 옵션 분석(GEX, Max Pain) 지원
"""

import numpy as np

try:
    from scipy.stats import norm
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# ═══ 무위험금리 및 상수 ═══
R_FREE = 0.045  # 미국 무위험금리 근사치


# ═══ Black-Scholes Greeks ═══

def bs_vanna(S, K, T_days, r, sigma):
    """Vanna = dDelta/dIV — IV 변화 시 딜러 헤징 방향

    Args:
        S: 현재가
        K: 스트라이크
        T_days: 잔존기간(일)
        r: 무위험금리
        sigma: 변동성(%)

    Returns:
        Vanna 값 (float)
    """
    if not SCIPY_AVAILABLE:
        return 0
    T = T_days / 365
    if T <= 0 or sigma <= 0 or K <= 0:
        return 0
    sigma_v = sigma / 100.0
    d1 = (np.log(S/K) + (r + 0.5*sigma_v**2)*T) / (sigma_v*np.sqrt(T))
    d2 = d1 - sigma_v*np.sqrt(T)
    return -norm.pdf(d1) * d2 / sigma_v


def bs_charm(S, K, T_days, r, sigma):
    """Charm = dDelta/dT — 시간 경과에 따른 딜러 델타 변화

    Args:
        S: 현재가
        K: 스트라이크
        T_days: 잔존기간(일)
        r: 무위험금리
        sigma: 변동성(%)

    Returns:
        Charm 값 (float)
    """
    if not SCIPY_AVAILABLE:
        return 0
    T = T_days / 365
    if T <= 0 or sigma <= 0 or K <= 0:
        return 0
    sigma_v = sigma / 100.0
    d1 = (np.log(S/K) + (r + 0.5*sigma_v**2)*T) / (sigma_v*np.sqrt(T))
    d2 = d1 - sigma_v*np.sqrt(T)
    return -norm.pdf(d1) * (2*r*T - d2*sigma_v*np.sqrt(T)) / (2*T*sigma_v*np.sqrt(T))


def bs_gamma(S, K, T, sigma, r=0.045):
    """Black-Scholes 감마 계산 (GEX 산출용)

    Args:
        S: 현재가
        K: 스트라이크
        T: 잔존기간(년)
        sigma: 변동성(소수, e.g., 0.20 for 20%)
        r: 무위험금리 (기본값: 0.045)

    Returns:
        감마 값 (float)
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        return float(np.exp(-0.5 * d1 ** 2) / (np.sqrt(2 * np.pi) * S * sigma * np.sqrt(T)))
    except Exception:
        return 0.0


# ═══ Options 통합 분석 ═══

def calc_max_pain(calls_df, puts_df, strikes):
    """Max Pain 계산 — 옵션 잔존 만기 시 최대 손실 스트라이크

    Args:
        calls_df: 콜옵션 DataFrame (필수 컬럼: strike, openInterest)
        puts_df: 풋옵션 DataFrame (필수 컬럼: strike, openInterest)
        strikes: 분석 대상 스트라이크 리스트

    Returns:
        Max Pain 스트라이크 (float) 또는 None
    """
    pain = {}
    for s in strikes:
        cp = ((s - calls_df.loc[calls_df['strike'] < s, 'strike'])
              * calls_df.loc[calls_df['strike'] < s, 'openInterest']).sum()
        pp = ((puts_df.loc[puts_df['strike'] > s, 'strike'] - s)
              * puts_df.loc[puts_df['strike'] > s, 'openInterest']).sum()
        pain[s] = cp + pp
    return min(pain, key=pain.get) if pain else None


def calc_vanna_charm(r):
    """Vanna & Charm 통합 계산 (CBOE 옵션 데이터용)

    Args:
        r: 옵션 데이터 딕셔너리 (필수 키:
            'sym', 'curr', 'iv_call', 'iv_put', 'exp_rows', 'chart',
            'tc_oi', 'tp_oi')

    Returns:
        {'vanna': float, 'charm': float} 또는 {'vanna': 0, 'charm': 0, 'err': str}
    """
    try:
        sym = r['sym']

        if not SCIPY_AVAILABLE:
            return {'vanna': 0, 'charm': 0, 'err': 'scipy 미설치: pip install scipy'}

        curr = r['curr']
        gex_data = r.get('gex', {})
        strikes = gex_data.get('strikes', [])

        if not strikes:
            return {'vanna': 0, 'charm': 0}

        net_vanna = 0
        net_charm = 0

        avg_iv = (r['iv_call'] + r['iv_put']) / 2
        if avg_iv <= 0:
            avg_iv = 20.0

        for row in r['exp_rows']:
            T = row['days']
            if T < 0:
                continue
            if T == 0:
                T = 0.01  # 0.01일 (약 15분) 로 근사하여 0 방지

            for i, strike in enumerate(r['chart']['strikes']):
                c_oi = r['chart']['call_oi'][i]
                p_oi = r['chart']['put_oi'][i]
                oi_total = c_oi + p_oi

                if oi_total <= 0:
                    continue

                v = bs_vanna(curr, strike, T, R_FREE, avg_iv)
                c = bs_charm(curr, strike, T, R_FREE, avg_iv)

                # 가중치 부여 (만기별 OI 비중에 따라)
                weight = ((row['c_oi'] + row['p_oi']) / (r['tc_oi'] + r['tp_oi'])
                         if (r['tc_oi'] + r['tp_oi']) > 0 else 1.0)

                net_vanna += v * oi_total * 100 * curr * weight
                net_charm += c * oi_total * 100 * curr * weight

        return {
            'vanna': round(net_vanna / 1e9, 3),
            'charm': round(net_charm / 1e9, 3)
        }
    except Exception as e:
        return {'vanna': 0, 'charm': 0, 'err': str(e)}


__all__ = [
    'bs_vanna',
    'bs_charm',
    'bs_gamma',
    'calc_max_pain',
    'calc_vanna_charm',
    'R_FREE',
    'SCIPY_AVAILABLE',
]
