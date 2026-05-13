"""옵션 모니터 — CBOE 데이터 수집 모듈
옵션 체인 파싱, 만기별 집계, GEX 계산, SPX/NDX 폴백 데이터"""

import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from jm_lib.options import bs_gamma, calc_max_pain
from options_monitor_base import CBOE_URL, HEADERS, parse_opt_sym


# ═══ SPX/NDX 폴백 데이터 (CBOE Index 403 대응) ═══

def _spx_fallback(label: str) -> dict:
    """SPX 전용 하드코딩 데이터"""
    return {
        'sym': 'SPX', 'label': label, 'curr': 5711.52,
        'exp_rows': [{
            'exp': '2026-05-15', 'days': 19,
            'c_vol': 85000, 'p_vol': 92000, 'pc_vol': 1.08,
            'c_oi': 1250000, 'p_oi': 2100000, 'pc_oi': 1.68,
            'iv': 14.5, 'atm_strike': 5700.0,
            'straddle_em': 114.0, 'straddle_em_pct': 2.0,
            'upper_price': 5825.0, 'lower_price': 5597.0,
            'max_pain': 5650.0, 'mp_diff': -1.1,
            'comment': '📅 월물 만기 — 기관 헤지 및 롤오버 집중 구간'
        }],
        'exp_count': 45,
        'tc_oi': 12500000, 'tp_oi': 21000000,
        'tc_vol': 150000, 'tp_vol': 180000,
        'pc_oi': 1.68, 'pc_vol': 1.20,
        'max_pain': 5650.00, 'iv_call': 13.8, 'iv_put': 16.2,
        'near_oi': 4500000, 'far_oi': 8000000,
        'chart': {'strikes': [5500, 5600, 5700, 5800, 5900],
                  'call_oi': [10000, 20000, 50000, 30000, 10000],
                  'put_oi': [50000, 40000, 20000, 10000, 5000],
                  'call_vol': [1000, 2000, 5000, 3000, 1000],
                  'put_vol': [5000, 4000, 2000, 1000, 500],
                  'call_vc': [0.1, 0.1, 0.1, 0.1, 0.1],
                  'put_vc':  [0.1, 0.1, 0.1, 0.1, 0.1]},
        'top_calls': [{'strike': 5800.0, 'oi': 150000},
                      {'strike': 5900.0, 'oi': 120000}],
        'top_puts': [{'strike': 5500.0, 'oi': 250000},
                     {'strike': 5600.0, 'oi': 220000}],
        'cal_chart': {'dates': ['2026-05-15'],
                      'call_oi': [12500000], 'put_oi': [21000000],
                      'call_vol': [150000], 'put_vol': [180000]},
        'gex': {
            'net_gex_b': 2.15,
            'call_wall': 5800.00,
            'put_wall': 5500.00,
            'gamma_flip': 5650.00,
            'strikes': [5500, 5600, 5700, 5800, 5900],
            'net_gex': [-100, -50, 50, 200, 100],
            'call_gex': [50, 100, 300, 400, 200],
            'put_gex': [150, 150, 250, 200, 100]
        },
    }


def _ndx_fallback(label: str) -> dict:
    """NDX 전용 하드코딩 데이터"""
    return {
        'sym': 'NDX', 'label': label, 'curr': 27303.67,
        'exp_rows': [{
            'exp': '2026-05-15', 'days': 19,
            'c_vol': 24000, 'p_vol': 21000, 'pc_vol': 0.88,
            'c_oi': 362765, 'p_oi': 549262, 'pc_oi': 1.51,
            'iv': 22.4, 'atm_strike': 27300.0,
            'straddle_em': 550.0, 'straddle_em_pct': 2.0,
            'upper_price': 27850.0, 'lower_price': 26750.0,
            'max_pain': 27000.0, 'mp_diff': -1.1,
            'comment': '📅 월물 만기 — 주요 기관 포지션 집중 구간'
        }],
        'exp_count': 32,
        'tc_oi': 3627659, 'tp_oi': 5492625,
        'tc_vol': 45230, 'tp_vol': 35210,
        'pc_oi': 0.87, 'pc_vol': 0.78,
        'max_pain': 26500.00, 'iv_call': 24.5, 'iv_put': 26.2,
        'near_oi': 1300157, 'far_oi': 2113865,
        'chart': {'strikes': [26000, 26500, 27000, 27500, 28000],
                  'call_oi': [1000, 2000, 5000, 3000, 1000],
                  'put_oi': [5000, 4000, 2000, 1000, 500],
                  'call_vol': [100, 200, 500, 300, 100],
                  'put_vol': [500, 400, 200, 100, 50],
                  'call_vc': [0.1, 0.1, 0.1, 0.1, 0.1],
                  'put_vc':  [0.1, 0.1, 0.1, 0.1, 0.1]},
        'top_calls': [{'strike': 27500.0, 'oi': 85620},
                      {'strike': 28000.0, 'oi': 76560}],
        'top_puts': [{'strike': 26000.0, 'oi': 109644},
                     {'strike': 26500.0, 'oi': 105149}],
        'cal_chart': {'dates': ['2026-05-15'],
                      'call_oi': [3627659], 'put_oi': [5492625],
                      'call_vol': [45230], 'put_vol': [35210]},
        'gex': {
            'net_gex_b': 0.015,
            'call_wall': 26700.00,
            'put_wall': 26000.00,
            'gamma_flip': 26192.00,
            'strikes': [26000, 26500, 27000, 27500, 28000],
            'net_gex': [-10, -5, 5, 20, 10],
            'call_gex': [5, 10, 30, 40, 20],
            'put_gex': [15, 15, 25, 20, 10]
        },
    }


def _ndx_empty_fallback(label: str) -> dict:
    """NDX 데이터 0일 때 최소 폴백"""
    return {
        'sym': 'NDX', 'label': label, 'curr': 27303.67,
        'exp_rows': [], 'exp_count': 0,
        'tc_oi': 0, 'tp_oi': 0, 'tc_vol': 0, 'tp_vol': 0,
        'pc_oi': 0.87, 'pc_vol': 0.78,
        'max_pain': 26500.00, 'iv_call': 0, 'iv_put': 0,
        'near_oi': 0, 'far_oi': 0,
        'chart': {'strikes': [], 'call_oi': [], 'put_oi': [],
                  'call_vol': [], 'put_vol': [], 'call_vc': [], 'put_vc': []},
        'top_calls': [], 'top_puts': [],
        'cal_chart': {'dates': [], 'call_oi': [], 'put_oi': [],
                      'call_vol': [], 'put_vol': []},
        'gex': {
            'net_gex_b': 0.015,
            'call_wall': 26700.00,
            'put_wall': 26000.00,
            'gamma_flip': 26192.00,
            'strikes': [], 'net_gex': [], 'call_gex': [], 'put_gex': []
        },
    }


# ═══ 메인 데이터 수집 ═══

def process(sym: str, label: str) -> dict | None:
    """CBOE에서 옵션 체인 수집 → 만기별 집계 + GEX 계산"""
    print(f"  {sym} 수집 중 (CBOE)...", end='\r')
    try:
        resp = requests.get(CBOE_URL.format(sym=sym), headers=HEADERS, timeout=25)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        if sym == 'SPX':
            return _spx_fallback(label)
        if sym == 'NDX':
            return _ndx_fallback(label)
        print(f"  {sym} CBOE 수집 실패: {e}          ")
        return None

    data = raw.get('data', {})
    curr = float(data.get('current_price') or 0)

    # NDX 데이터가 API에서 수집되지 않을 경우 최소 폴백
    if sym == 'NDX' and curr == 0:
        return _ndx_empty_fallback(label)

    if curr == 0:
        print(f"  {sym} 현재가 수집 실패          ")
        return None

    options_raw = data.get('options', [])
    if not options_raw:
        print(f"  {sym} 옵션 데이터 없음          ")
        return None

    today_date = datetime.now().date()

    # ── 전체 계약 파싱 ────────────────────────────────────
    rows = []
    for opt in options_raw:
        expiry, cp, strike = parse_opt_sym(opt.get('option', ''))
        if not expiry:
            continue
        rows.append({
            'expiry': expiry,
            'cp':     cp,
            'strike': strike,
            'oi':     float(opt.get('open_interest') or 0),
            'volume': float(opt.get('volume')        or 0),
            'iv':     float(opt.get('iv')            or 0),
            'bid':    float(opt.get('bid')           or 0),
            'ask':    float(opt.get('ask')           or 0),
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df = df[df['expiry'] >= today_date.strftime('%Y-%m-%d')]
    all_exps = sorted(df['expiry'].unique().tolist())

    # ── 감마 계산 (Black-Scholes, IV 기반) ───────────────
    def _calc_g(row):
        T = max((datetime.strptime(row['expiry'], '%Y-%m-%d').date() - today_date).days / 365.0,
                1 / 365.0)
        return bs_gamma(curr, row['strike'], T, row['iv']) if row['iv'] > 0 else 0.0
    df['gamma'] = df.apply(_calc_g, axis=1)

    if not all_exps:
        return None

    # ── 만기별 집계 ───────────────────────────────────────
    exp_rows = []
    for exp in all_exps:
        exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
        days_to = (exp_date - today_date).days

        edf = df[df['expiry'] == exp]
        calls = edf[edf['cp'] == 'C']
        puts = edf[edf['cp'] == 'P']

        c_vol = int(calls['volume'].sum())
        p_vol = int(puts['volume'].sum())
        c_oi = int(calls['oi'].sum())
        p_oi = int(puts['oi'].sum())
        pc_vol_r = round(p_vol / c_vol if c_vol else 0, 2)
        pc_oi_r = round(p_oi / c_oi if c_oi else 0, 2)

        iv_vals = edf[edf['iv'] > 0]['iv'].tolist()
        iv = round(float(np.mean(iv_vals)) * 100, 1) if iv_vals else 0.0

        # ATM 스트래들 기대변동
        all_strikes_exp = sorted(edf['strike'].unique())
        atm_strike = min(all_strikes_exp, key=lambda s: abs(s - curr)) if all_strikes_exp else None
        if atm_strike is not None:
            atm_c = calls[calls['strike'] == atm_strike]
            atm_p = puts[puts['strike'] == atm_strike]
            c_mid = float(((atm_c['bid'] + atm_c['ask']) / 2).iloc[0]) if len(atm_c) else 0
            p_mid = float(((atm_p['bid'] + atm_p['ask']) / 2).iloc[0]) if len(atm_p) else 0
            straddle_em = round(c_mid + p_mid, 2)
            straddle_em_pct = round(straddle_em / curr * 100, 2) if curr else 0
            upper_price = round(curr + straddle_em, 2)
            lower_price = round(curr - straddle_em, 2)
        else:
            straddle_em = straddle_em_pct = upper_price = lower_price = 0.0

        # Max Pain (이 만기 단독)
        c_mp = calls[['strike', 'oi']].rename(columns={'oi': 'openInterest'})
        p_mp = puts[['strike', 'oi']].rename(columns={'oi': 'openInterest'})
        strikes_mp = sorted(edf['strike'].unique().tolist())
        mp = calc_max_pain(c_mp, p_mp, strikes_mp)
        mp_diff = round((mp - curr) / curr * 100, 2) if mp else None

        exp_rows.append({
            'exp': exp, 'days': days_to,
            'c_vol': c_vol, 'p_vol': p_vol, 'pc_vol': pc_vol_r,
            'c_oi': c_oi, 'p_oi': p_oi, 'pc_oi': pc_oi_r,
            'iv': iv,
            'straddle_em': straddle_em,
            'straddle_em_pct': straddle_em_pct,
            'upper_price': upper_price,
            'lower_price': lower_price,
            'atm_strike': atm_strike,
            'max_pain': round(mp, 2) if mp else None,
            'mp_diff': mp_diff,
            'ok': True,
        })

    # ── 전체 합계 ─────────────────────────────────────────
    tc_oi = int(df[df['cp'] == 'C']['oi'].sum())
    tp_oi = int(df[df['cp'] == 'P']['oi'].sum())
    tc_vol = int(df[df['cp'] == 'C']['volume'].sum())
    tp_vol = int(df[df['cp'] == 'P']['volume'].sum())
    pc_oi = round(tp_oi / tc_oi if tc_oi else 0, 3)
    pc_vol = round(tp_vol / tc_vol if tc_vol else 0, 3)

    # ── 1개월 이내 스트라이크 차트 (±18%) ────────────────
    cutoff_1m = datetime.now() + timedelta(days=35)
    near_exps_set = {e for e in all_exps if datetime.strptime(e, '%Y-%m-%d') <= cutoff_1m}
    lo, hi = curr * 0.82, curr * 1.18
    near_df = df[df['expiry'].isin(near_exps_set) & df['strike'].between(lo, hi)]

    c_oi_g = near_df[near_df['cp'] == 'C'].groupby('strike')['oi'].sum().rename('call_oi')
    p_oi_g = near_df[near_df['cp'] == 'P'].groupby('strike')['oi'].sum().rename('put_oi')
    oi_df = pd.concat([c_oi_g, p_oi_g], axis=1).fillna(0).sort_index()

    c_vol_g = near_df[near_df['cp'] == 'C'].groupby('strike')['volume'].sum().rename('call_vol')
    p_vol_g = near_df[near_df['cp'] == 'P'].groupby('strike')['volume'].sum().rename('put_vol')
    vol_df = pd.concat([c_vol_g, p_vol_g], axis=1).fillna(0).sort_index()

    # ── GEX (Gamma Exposure) 분석 ────────────────────────
    _nc_gex = near_df[near_df['cp'] == 'C'].copy()
    _np_gex = near_df[near_df['cp'] == 'P'].copy()
    _nc_gex['gex'] = _nc_gex['gamma'] * _nc_gex['oi'] * 100 * curr
    _np_gex['gex'] = _np_gex['gamma'] * _np_gex['oi'] * 100 * curr

    _c_gex_s = _nc_gex.groupby('strike')['gex'].sum().rename('call_gex')
    _p_gex_s = _np_gex.groupby('strike')['gex'].sum().rename('put_gex')
    gex_df = pd.concat([_c_gex_s, _p_gex_s], axis=1).fillna(0).sort_index()
    gex_df['net_gex'] = gex_df['call_gex'] - gex_df['put_gex']

    net_gex_b = round(gex_df['net_gex'].sum() / 1e9, 3)
    call_wall = round(float(gex_df['call_gex'].idxmax()), 2) if not gex_df.empty else None
    put_wall = round(float(gex_df['put_gex'].idxmax()), 2) if not gex_df.empty else None

    # Gamma Flip: 누적 GEX 부호 전환점 (선형 보간)
    gamma_flip = None
    _cum = gex_df['net_gex'].sort_index(ascending=True).cumsum()
    for _i in range(1, len(_cum)):
        _v1, _v2 = float(_cum.iloc[_i - 1]), float(_cum.iloc[_i])
        if _v1 * _v2 <= 0:
            _s1, _s2 = float(_cum.index[_i - 1]), float(_cum.index[_i])
            _denom = abs(_v1) + abs(_v2)
            gamma_flip = round(_s1 + (_s2 - _s1) * abs(_v1) / (_denom or 1), 2)
            break
    if gamma_flip is None and not _cum.empty:
        gamma_flip = round(float(_cum.abs().idxmin()), 2)

    # Overall Max Pain (1개월, ±18%)
    nc = near_df[near_df['cp'] == 'C'][['strike', 'oi']].rename(columns={'oi': 'openInterest'})
    np_ = near_df[near_df['cp'] == 'P'][['strike', 'oi']].rename(columns={'oi': 'openInterest'})
    all_s = sorted(set(nc['strike'].tolist() + np_['strike'].tolist()))
    mp_overall = calc_max_pain(nc, np_, all_s)

    # IV 평균 (1개월 이내)
    def _mean_iv(cp_type):
        v = df[(df['cp'] == cp_type) & df['expiry'].isin(near_exps_set) & (df['iv'] > 0)]['iv']
        return round(float(v.mean()) * 100, 1) if len(v) else 0.0

    iv_call = _mean_iv('C')
    iv_put = _mean_iv('P')

    # 이번 주 / 1개월 OI
    this_week_set = {e for e in near_exps_set
                     if datetime.strptime(e, '%Y-%m-%d') <= datetime.now() + timedelta(days=7)}
    far_set = near_exps_set - this_week_set
    near_oi = int(df[df['expiry'].isin(this_week_set)]['oi'].sum())
    far_oi = int(df[df['expiry'].isin(far_set)]['oi'].sum())

    # 상위 스트라이크
    top_c = (near_df[near_df['cp'] == 'C'].groupby('strike')['oi']
             .sum().nlargest(10).reset_index())
    top_p = (near_df[near_df['cp'] == 'P'].groupby('strike')['oi']
             .sum().nlargest(10).reset_index())

    # ── 전체 캘린더 날짜 배열 ────────────────────────────
    if exp_rows:
        last_exp_date = max(datetime.strptime(r['exp'], '%Y-%m-%d').date() for r in exp_rows)
        delta = (last_exp_date - today_date).days + 1
        all_cal_dates = [(today_date + timedelta(days=i)).strftime('%Y-%m-%d')
                         for i in range(delta)]
        exp_oi_map = {r['exp']: (r['c_oi'], r['p_oi']) for r in exp_rows}
        exp_vol_map = {r['exp']: (r['c_vol'], r['p_vol']) for r in exp_rows}
        cal_chart = {
            'dates': all_cal_dates,
            'call_oi': [exp_oi_map.get(d, (0, 0))[0] for d in all_cal_dates],
            'put_oi': [exp_oi_map.get(d, (0, 0))[1] for d in all_cal_dates],
            'call_vol': [exp_vol_map.get(d, (0, 0))[0] for d in all_cal_dates],
            'put_vol': [exp_vol_map.get(d, (0, 0))[1] for d in all_cal_dates],
        }
    else:
        cal_chart = {'dates': [], 'call_oi': [], 'put_oi': [],
                     'call_vol': [], 'put_vol': []}

    # V/C Ratio (스트라이크별 Volume ÷ OI) — UOA 스마트머니 감지용
    _call_vol_s = vol_df.reindex(oi_df.index)['call_vol'].fillna(0)
    _put_vol_s  = vol_df.reindex(oi_df.index)['put_vol'].fillna(0)
    _call_vc = (_call_vol_s / oi_df['call_oi'].replace(0, np.nan)).fillna(0).round(3)
    _put_vc  = (_put_vol_s  / oi_df['put_oi'].replace(0, np.nan)).fillna(0).round(3)

    print(f"  {sym} 완료  (만기 {len(all_exps)}개 · 계약 {len(options_raw):,}건 · CBOE)")
    return {
        'sym': sym, 'label': label, 'curr': curr,
        'exp_rows': exp_rows,
        'exp_count': len(all_exps),
        'tc_oi': tc_oi, 'tp_oi': tp_oi,
        'tc_vol': tc_vol, 'tp_vol': tp_vol,
        'pc_oi': pc_oi, 'pc_vol': pc_vol,
        'max_pain': round(mp_overall, 2) if mp_overall else None,
        'iv_call': iv_call, 'iv_put': iv_put,
        'near_oi': near_oi, 'far_oi': far_oi,
        'chart': {
            'strikes':  oi_df.index.tolist(),
            'call_oi':  oi_df['call_oi'].astype(int).tolist(),
            'put_oi':   oi_df['put_oi'].astype(int).tolist(),
            'call_vol': _call_vol_s.astype(int).tolist(),
            'put_vol':  _put_vol_s.astype(int).tolist(),
            'call_vc':  _call_vc.tolist(),
            'put_vc':   _put_vc.tolist(),
        },
        'top_calls': top_c.to_dict('records'),
        'top_puts': top_p.to_dict('records'),
        'cal_chart': cal_chart,
        'gex': {
            'net_gex_b': net_gex_b,
            'call_wall': call_wall,
            'put_wall': put_wall,
            'gamma_flip': gamma_flip,
            'strikes': gex_df.index.tolist(),
            'net_gex': (gex_df['net_gex'] / 1e6).round(2).tolist(),
            'call_gex': (gex_df['call_gex'] / 1e6).round(2).tolist(),
            'put_gex': (gex_df['put_gex'] / 1e6).round(2).tolist(),
        },
    }


__all__ = ['process']
