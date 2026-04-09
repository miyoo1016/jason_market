#!/usr/bin/env python3
"""옵션 모니터 - Jason Market
QQQ / GLD 전체 만기 옵션 배팅 현황
데이터 소스:
  · 날짜/OI/Volume/IV : CBOE Delayed Quotes API (= optioncharts.io 동일 소스)
  · 기대변동폭 : ATM 스트래들 미드가격 (= barchart.com/expected-move 동일 방식)
만기별 상세표 · 스트라이크 OI 차트 · Max Pain · P/C 비율 · 상한/하한 범위"""

import os, json, re, webbrowser, warnings
warnings.filterwarnings('ignore')

# .env 파일에서 API 키 로드
from dotenv import load_dotenv
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env, override=True)

import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

ALERT = '\033[38;5;203m'
RESET = '\033[0m'
EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

ASSETS = [
    ('QQQ',   'Nasdaq 100 ETF'),
    ('SPY',   'S&P 500 ETF'),
    ('GOOGL', 'Alphabet Inc.'),
    ('GLD',   '금 ETF (SPDR Gold)'),
]

# CBOE 공개 delayed quotes API (optioncharts.io 와 동일 데이터 소스)
CBOE_URL = 'https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json'
HEADERS  = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'}

# ── 데이터 수집 ───────────────────────────────────────────

def _bs_gamma(S, K, T, sigma, r=0.045):
    """Black-Scholes 감마 계산 (GEX 산출용)
    S=현재가, K=스트라이크, T=잔존기간(년), sigma=IV(소수), r=무위험금리"""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        return float(np.exp(-0.5 * d1 ** 2) / (np.sqrt(2 * np.pi) * S * sigma * np.sqrt(T)))
    except Exception:
        return 0.0


def calc_max_pain(calls_df, puts_df, strikes):
    pain = {}
    for s in strikes:
        cp = ((s - calls_df.loc[calls_df['strike'] < s, 'strike'])
              * calls_df.loc[calls_df['strike'] < s, 'openInterest']).sum()
        pp = ((puts_df.loc[puts_df['strike'] > s, 'strike'] - s)
              * puts_df.loc[puts_df['strike'] > s, 'openInterest']).sum()
        pain[s] = cp + pp
    return min(pain, key=pain.get) if pain else None

# CBOE 옵션 심볼 파싱: 'QQQ260327C00450000' → ('2026-03-27', 'C', 450.0)
_OPT_RE = re.compile(r'^([A-Z]+)(\d{6})([CP])(\d{8})$')

def _parse_opt_sym(sym):
    m = _OPT_RE.match(sym or '')
    if not m:
        return None, None, None
    _, ds, cp, ss = m.groups()
    expiry = f'20{ds[:2]}-{ds[2:4]}-{ds[4:6]}'
    strike = int(ss) / 1000.0
    return expiry, cp, strike

def process(sym, label):
    print(f"  {sym} 수집 중 (CBOE)...", end='\r')
    try:
        resp = requests.get(CBOE_URL.format(sym=sym), headers=HEADERS, timeout=25)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        print(f"  {sym} CBOE 수집 실패: {e}          ")
        return None

    data = raw.get('data', {})
    curr = float(data.get('current_price') or 0)
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
        expiry, cp, strike = _parse_opt_sym(opt.get('option', ''))
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
    # 과거 만기일 제외 (오늘 이전)
    df = df[df['expiry'] >= today_date.strftime('%Y-%m-%d')]
    all_exps = sorted(df['expiry'].unique().tolist())

    # ── 감마 계산 (Black-Scholes, IV 기반) ───────────────
    def _calc_g(row):
        T = max((datetime.strptime(row['expiry'], '%Y-%m-%d').date() - today_date).days / 365.0,
                1 / 365.0)
        return _bs_gamma(curr, row['strike'], T, row['iv']) if row['iv'] > 0 else 0.0
    df['gamma'] = df.apply(_calc_g, axis=1)

    if not all_exps:
        return None

    # ── 만기별 집계 ───────────────────────────────────────
    exp_rows = []
    for exp in all_exps:
        exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
        days_to  = (exp_date - today_date).days

        edf   = df[df['expiry'] == exp]
        calls = edf[edf['cp'] == 'C']
        puts  = edf[edf['cp'] == 'P']

        c_vol = int(calls['volume'].sum())
        p_vol = int(puts['volume'].sum())
        c_oi  = int(calls['oi'].sum())
        p_oi  = int(puts['oi'].sum())
        pc_vol_r = round(p_vol / c_vol if c_vol else 0, 2)
        pc_oi_r  = round(p_oi  / c_oi  if c_oi  else 0, 2)

        # IV: 0 제외 평균
        iv_vals = edf[edf['iv'] > 0]['iv'].tolist()
        iv = round(float(np.mean(iv_vals)) * 100, 1) if iv_vals else 0.0

        # ── ATM 스트래들 기대변동 (barchart.com 동일 방식) ──────
        # 현재가에 가장 가까운 스트라이크의 콜mid + 풋mid
        all_strikes_exp = sorted(edf['strike'].unique())
        atm_strike = min(all_strikes_exp, key=lambda s: abs(s - curr)) if all_strikes_exp else None
        if atm_strike is not None:
            atm_c = calls[calls['strike'] == atm_strike]
            atm_p = puts[puts['strike']  == atm_strike]
            c_mid = float(((atm_c['bid'] + atm_c['ask']) / 2).iloc[0]) if len(atm_c) else 0
            p_mid = float(((atm_p['bid'] + atm_p['ask']) / 2).iloc[0]) if len(atm_p) else 0
            straddle_em     = round(c_mid + p_mid, 2)
            straddle_em_pct = round(straddle_em / curr * 100, 2) if curr else 0
            upper_price     = round(curr + straddle_em, 2)
            lower_price     = round(curr - straddle_em, 2)
        else:
            straddle_em = straddle_em_pct = upper_price = lower_price = 0.0

        # Max Pain (이 만기 단독)
        c_mp = calls[['strike', 'oi']].rename(columns={'oi': 'openInterest'})
        p_mp = puts[['strike',  'oi']].rename(columns={'oi': 'openInterest'})
        strikes_mp = sorted(edf['strike'].unique().tolist())
        mp     = calc_max_pain(c_mp, p_mp, strikes_mp)
        mp_diff = round((mp - curr) / curr * 100, 2) if mp else None

        exp_rows.append({
            'exp':  exp, 'days': days_to,
            'c_vol': c_vol, 'p_vol': p_vol, 'pc_vol': pc_vol_r,
            'c_oi':  c_oi,  'p_oi':  p_oi,  'pc_oi':  pc_oi_r,
            'iv': iv,
            'straddle_em':     straddle_em,
            'straddle_em_pct': straddle_em_pct,
            'upper_price':     upper_price,
            'lower_price':     lower_price,
            'atm_strike':      atm_strike,
            'max_pain': round(mp, 2) if mp else None,
            'mp_diff':  mp_diff,
            'ok': True,
        })

    # ── 전체 합계 ─────────────────────────────────────────
    tc_oi  = int(df[df['cp'] == 'C']['oi'].sum())
    tp_oi  = int(df[df['cp'] == 'P']['oi'].sum())
    tc_vol = int(df[df['cp'] == 'C']['volume'].sum())
    tp_vol = int(df[df['cp'] == 'P']['volume'].sum())
    pc_oi  = round(tp_oi  / tc_oi  if tc_oi  else 0, 3)
    pc_vol = round(tp_vol / tc_vol if tc_vol else 0, 3)

    # ── 1개월 이내 스트라이크 차트 (±18%) ────────────────
    cutoff_1m     = datetime.now() + timedelta(days=35)
    near_exps_set = {e for e in all_exps if datetime.strptime(e, '%Y-%m-%d') <= cutoff_1m}
    lo, hi   = curr * 0.82, curr * 1.18
    near_df  = df[df['expiry'].isin(near_exps_set) & df['strike'].between(lo, hi)]

    c_oi_g  = near_df[near_df['cp'] == 'C'].groupby('strike')['oi'].sum().rename('call_oi')
    p_oi_g  = near_df[near_df['cp'] == 'P'].groupby('strike')['oi'].sum().rename('put_oi')
    oi_df   = pd.concat([c_oi_g, p_oi_g], axis=1).fillna(0).sort_index()

    c_vol_g = near_df[near_df['cp'] == 'C'].groupby('strike')['volume'].sum().rename('call_vol')
    p_vol_g = near_df[near_df['cp'] == 'P'].groupby('strike')['volume'].sum().rename('put_vol')
    vol_df  = pd.concat([c_vol_g, p_vol_g], axis=1).fillna(0).sort_index()

    # ── GEX (Gamma Exposure) 분석 ────────────────────────
    # GEX = gamma × OI × 100 × 현재가  (콜: +, 풋: -)
    # 양수: 딜러 롱감마 → 시장 안정화 / 음수: 딜러 숏감마 → 변동성 증폭
    _nc_gex = near_df[near_df['cp'] == 'C'].copy()
    _np_gex = near_df[near_df['cp'] == 'P'].copy()
    _nc_gex['gex'] = _nc_gex['gamma'] * _nc_gex['oi'] * 100 * curr
    _np_gex['gex'] = _np_gex['gamma'] * _np_gex['oi'] * 100 * curr

    _c_gex_s = _nc_gex.groupby('strike')['gex'].sum().rename('call_gex')
    _p_gex_s = _np_gex.groupby('strike')['gex'].sum().rename('put_gex')
    gex_df   = pd.concat([_c_gex_s, _p_gex_s], axis=1).fillna(0).sort_index()
    gex_df['net_gex'] = gex_df['call_gex'] - gex_df['put_gex']

    net_gex_b  = round(gex_df['net_gex'].sum() / 1e9, 3)   # $ billions
    call_wall  = round(float(gex_df['call_gex'].idxmax()), 2) if not gex_df.empty else None
    put_wall   = round(float(gex_df['put_gex'].idxmax()),  2) if not gex_df.empty else None

    # Gamma Flip: 누적 GEX 부호 전환점 (선형 보간)
    gamma_flip = None
    _cum = gex_df['net_gex'].sort_index(ascending=True).cumsum()
    for _i in range(1, len(_cum)):
        _v1, _v2 = float(_cum.iloc[_i - 1]), float(_cum.iloc[_i])
        if _v1 * _v2 <= 0:
            _s1, _s2 = float(_cum.index[_i - 1]), float(_cum.index[_i])
            _denom   = abs(_v1) + abs(_v2)
            gamma_flip = round(_s1 + (_s2 - _s1) * abs(_v1) / (_denom or 1), 2)
            break
    if gamma_flip is None and not _cum.empty:
        gamma_flip = round(float(_cum.abs().idxmin()), 2)

    # Overall Max Pain (1개월, ±18%)
    nc      = near_df[near_df['cp'] == 'C'][['strike', 'oi']].rename(columns={'oi': 'openInterest'})
    np_     = near_df[near_df['cp'] == 'P'][['strike', 'oi']].rename(columns={'oi': 'openInterest'})
    all_s   = sorted(set(nc['strike'].tolist() + np_['strike'].tolist()))
    mp_overall = calc_max_pain(nc, np_, all_s)

    # IV 평균 (1개월 이내)
    def _mean_iv(cp_type):
        v = df[(df['cp'] == cp_type) & df['expiry'].isin(near_exps_set) & (df['iv'] > 0)]['iv']
        return round(float(v.mean()) * 100, 1) if len(v) else 0.0

    iv_call = _mean_iv('C')
    iv_put  = _mean_iv('P')

    # 이번 주 / 1개월 OI
    this_week_set = {e for e in near_exps_set
                     if datetime.strptime(e, '%Y-%m-%d') <= datetime.now() + timedelta(days=7)}
    far_set  = near_exps_set - this_week_set
    near_oi  = int(df[df['expiry'].isin(this_week_set)]['oi'].sum())
    far_oi   = int(df[df['expiry'].isin(far_set)]['oi'].sum())

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
        exp_oi_map  = {r['exp']: (r['c_oi'],  r['p_oi'])  for r in exp_rows}
        exp_vol_map = {r['exp']: (r['c_vol'], r['p_vol']) for r in exp_rows}
        cal_chart = {
            'dates':    all_cal_dates,
            'call_oi':  [exp_oi_map.get(d,  (0, 0))[0] for d in all_cal_dates],
            'put_oi':   [exp_oi_map.get(d,  (0, 0))[1] for d in all_cal_dates],
            'call_vol': [exp_vol_map.get(d, (0, 0))[0] for d in all_cal_dates],
            'put_vol':  [exp_vol_map.get(d, (0, 0))[1] for d in all_cal_dates],
        }
    else:
        cal_chart = {'dates': [], 'call_oi': [], 'put_oi': [], 'call_vol': [], 'put_vol': []}

    print(f"  {sym} 완료  (만기 {len(all_exps)}개 · 계약 {len(options_raw):,}건 · CBOE)")
    return {
        'sym': sym, 'label': label, 'curr': curr,
        'exp_rows':  exp_rows,
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
            'call_vol': vol_df.reindex(oi_df.index)['call_vol'].fillna(0).astype(int).tolist(),
            'put_vol':  vol_df.reindex(oi_df.index)['put_vol'].fillna(0).astype(int).tolist(),
        },
        'top_calls': top_c.to_dict('records'),
        'top_puts':  top_p.to_dict('records'),
        'cal_chart': cal_chart,
        'gex': {
            'net_gex_b':  net_gex_b,
            'call_wall':  call_wall,
            'put_wall':   put_wall,
            'gamma_flip': gamma_flip,
            'strikes':    gex_df.index.tolist(),
            'net_gex':    (gex_df['net_gex']  / 1e6).round(2).tolist(),
            'call_gex':   (gex_df['call_gex'] / 1e6).round(2).tolist(),
            'put_gex':    (gex_df['put_gex']  / 1e6).round(2).tolist(),
        },
    }

# ── HTML 생성 ─────────────────────────────────────────────

def pc_signal(pc):
    if pc >= 1.5: return ('극도 풋 우세 (강한 헤지/약세)', '#ef5350')
    if pc >= 1.0: return ('풋 우세 (약세 배팅)',           '#ff7043')
    if pc >= 0.7: return ('중립',                         '#888')
    if pc >= 0.5: return ('콜 우세 (강세 배팅)',           '#26a69a')
    return             ('극도 콜 우세 (강한 강세)',         '#00bcd4')

def _pc_color(pc):
    if pc >= 1.5: return '#ef5350'
    if pc >= 1.0: return '#ff7043'
    if pc >= 0.7: return '#888'
    if pc >= 0.5: return '#26a69a'
    return '#00bcd4'

_KO_DAYS = ['월', '화', '수', '목', '금', '토', '일']

def _weekday_ko(exp_str):
    try:
        return _KO_DAYS[datetime.strptime(exp_str, '%Y-%m-%d').weekday()]
    except Exception:
        return ''

def _is_monthly(exp_str):
    """3번째 금요일(월물)이면 True"""
    try:
        d = datetime.strptime(exp_str, '%Y-%m-%d')
        if d.weekday() != 4:
            return False
        return 15 <= d.day <= 21
    except Exception:
        return False

def _exp_comment(row, curr):
    days  = row['days']
    pc_oi = row['pc_oi']
    iv    = row['iv']
    mp    = row['max_pain']
    c_oi  = row['c_oi']
    p_oi  = row['p_oi']
    ok    = row.get('ok', True)

    if not ok:
        return '⚠ 데이터 수집 실패'

    parts = []
    is_mo = _is_monthly(row['exp'])

    if days <= 0:
        parts.append('📌 오늘 만기 — 감마 위험 극대, 핀 리스크 주의')
    elif days <= 3:
        parts.append('⚡ 초단기 — 델타·감마 변동 매우 심함')
    elif days <= 7:
        parts.append('🔥 단기 주물 — 빠른 시간가치 소멸')
    elif days <= 30:
        if is_mo:
            parts.append('📅 월물 만기 — 대형 포지션 정리·롤오버 집중')
        else:
            parts.append('📆 단기 주물')
    elif days <= 90:
        if is_mo:
            parts.append('📅 월물 (중기) — 기관 헤지 주요 만기')
        else:
            parts.append('📆 중기 주물')
    else:
        parts.append('🏦 장기 LEAPS — 기관·대형 방향성 배팅')

    if (c_oi + p_oi) > 0:
        if pc_oi >= 2.0:
            parts.append('🐻 극강 풋 우세 (강한 하락 헤지)')
        elif pc_oi >= 1.3:
            parts.append('🐻 풋 우세 (약세 배팅)')
        elif pc_oi <= 0.5:
            parts.append('🐂 극강 콜 우세 (강한 상승 배팅)')
        elif pc_oi <= 0.8:
            parts.append('🐂 콜 우세 (강세 배팅)')
        else:
            parts.append('⚖ 콜·풋 균형')

    if iv >= 50:
        parts.append(f'🌋 IV {iv:.0f}% 매우 높음 (이벤트/공포)')
    elif iv >= 35:
        parts.append(f'⚠ IV {iv:.0f}% 높음')
    elif iv > 0:
        parts.append(f'IV {iv:.0f}%')

    if mp:
        diff = (mp - curr) / curr * 100
        if diff >= 5:
            parts.append(f'Max Pain +{diff:.1f}% → 상방 당김 강함')
        elif diff >= 2:
            parts.append(f'Max Pain +{diff:.1f}% → 약한 상방 인력')
        elif diff <= -5:
            parts.append(f'Max Pain {diff:.1f}% → 하방 당김 강함')
        elif diff <= -2:
            parts.append(f'Max Pain {diff:.1f}% → 약한 하방 인력')

    tot_oi = c_oi + p_oi
    if tot_oi >= 1_000_000:
        parts.append('💎 초대형 OI')
    elif tot_oi >= 500_000:
        parts.append('🔵 대형 OI')
    elif tot_oi >= 100_000:
        parts.append('중규모 OI')

    return ' · '.join(parts) if parts else '–'

def _days_badge(days):
    if days <= 0:  return f'<span class="badge b-red">만기</span>'
    if days <= 7:  return f'<span class="badge b-red">{days}일</span>'
    if days <= 30: return f'<span class="badge b-orange">{days}일</span>'
    if days <= 90: return f'<span class="badge b-gray">{days}일</span>'
    return f'<span class="badge b-light">{days}일</span>'

def generate_html(results, timestamp):
    data_js = json.dumps(results, ensure_ascii=False)

    cards = ''
    for r in results:
        if not r:
            continue
        sym    = r['sym']
        curr   = r['curr']
        mp     = r['max_pain']
        pc_oi  = r['pc_oi']
        sig, sig_color = pc_signal(pc_oi)
        mp_diff = round((mp - curr) / curr * 100, 2) if mp else None
        mp_str  = f"${mp:,.2f} ({mp_diff:+.1f}%)" if mp and mp_diff is not None else 'N/A'

        # Max Pain 긴급 지표 (7일 이내 만기)
        mp_urgency = ''
        if mp and mp_diff is not None:
            near_exp = next((row for row in r['exp_rows']
                             if row.get('max_pain') and row['days'] <= 7), None)
            if near_exp and near_exp['max_pain']:
                mp_near = near_exp['max_pain']
                mp_near_diff = (mp_near - curr) / curr * 100
                if abs(mp_near_diff) >= 2:
                    direction = '하방' if mp_near_diff < 0 else '상방'
                    mp_urgency = (f"⚡ 주의: 이번주 만기 Max Pain {mp_near_diff:+.1f}% "
                                  f"({direction} 당김)")

        # ── 만기별 상세 테이블 ──────────────────────────────
        exp_rows_html = ''
        for row in r['exp_rows']:
            days    = row['days']
            c_vol   = row['c_vol']
            p_vol   = row['p_vol']
            tot_vol = c_vol + p_vol
            pc_vol  = row['pc_vol']
            c_oi    = row['c_oi']
            p_oi    = row['p_oi']
            tot_oi  = c_oi + p_oi
            pc_oi_r = row['pc_oi']
            iv          = row['iv']
            st_em       = row['straddle_em']
            st_em_pct   = row['straddle_em_pct']
            upper_p     = row['upper_price']
            lower_p     = row['lower_price']
            atm_s       = row['atm_strike']
            mp_r        = row['max_pain']
            mpd         = row['mp_diff']

            pc_vol_c  = _pc_color(pc_vol)
            pc_oi_c   = _pc_color(pc_oi_r)
            iv_cls    = 'iv-hi' if iv >= 40 else ('iv-mid' if iv >= 25 else 'iv-lo')
            mp_cell   = f'${mp_r:,.2f}' if mp_r else '–'
            mpd_cell  = f'{mpd:+.1f}%'  if mpd is not None else '–'
            mpd_color = '#26a69a' if (mpd or 0) >= 0 else '#ef5350'

            # 기대변동 셀 — ±% (굵게) + ±$ (서브) + 범위
            if st_em > 0:
                em_cell = (f'<span class="em-val">±{st_em_pct:.1f}%</span>'
                           f'<br><span class="em-sub">±${st_em:,.2f}</span>'
                           f'<br><span class="em-range">'
                           f'<span class="em-up">▲{upper_p:,.2f}</span>'
                           f'<br><span class="em-dn">▼{lower_p:,.2f}</span>'
                           f'</span>')
            else:
                em_cell = '–'

            # Max Pain 합성 셀
            if mp_r:
                mp_combined = (f'<span class="mp-price">${mp_r:,.2f}</span>'
                               f'<br><span class="mp-diff" style="color:{mpd_color}">{mpd_cell}</span>')
            else:
                mp_combined = '–'

            # P/C 합성 셀 (Vol P/C + OI P/C + OI 미니바)
            # 원본 숫자는 hover tooltip으로 복원
            pc_tooltip = (f'콜Vol:{c_vol:,} / 풋Vol:{p_vol:,}&#10;'
                          f'콜OI:{c_oi:,} / 풋OI:{p_oi:,}')
            if tot_oi > 0:
                call_w = round(c_oi / tot_oi * 100, 1)
                put_w  = 100 - call_w
                pc_bar = (f'<div class="pc-bar-wrap" title="{pc_tooltip}">'
                          f'<div class="pc-bar-c" style="width:{call_w}%"></div>'
                          f'<div class="pc-bar-p" style="width:{put_w}%"></div>'
                          f'</div>')
            else:
                pc_bar = ''

            pc_cell = (f'<div class="pc-line"><span class="pc-lbl">Vol</span>'
                       f'<span style="color:{pc_vol_c};font-weight:700">{pc_vol:.2f}</span></div>'
                       f'<div class="pc-line"><span class="pc-lbl">OI&nbsp;</span>'
                       f'<span style="color:{pc_oi_c};font-weight:700">{pc_oi_r:.2f}</span></div>'
                       f'{pc_bar}')

            row_cls       = ' class="row-near"' if days <= 7 else (
                            ' class="row-mid"'  if days <= 30 else '')
            wd            = _weekday_ko(row['exp'])
            comment       = _exp_comment(row, curr)
            ok            = row.get('ok', True)
            row_cls_extra = '' if ok else ' style="opacity:0.5"'

            exp_rows_html += f"""
<tr{row_cls}{row_cls_extra}>
  <td class="exp-date">{row['exp']}<span class="wd">({wd})</span></td>
  <td style="text-align:center">{_days_badge(days)}</td>
  <td class="pc-cell" title="{pc_tooltip}">{pc_cell}</td>
  <td class="num {iv_cls}">{iv:.1f}%</td>
  <td class="em-cell2">{em_cell}</td>
  <td class="mp-cell">{mp_combined}</td>
  <td class="comment-cell">{comment}</td>
</tr>"""

        # 합계행
        tot_c_vol  = sum(x['c_vol'] for x in r['exp_rows'])
        tot_p_vol  = sum(x['p_vol'] for x in r['exp_rows'])
        tot_c_oi   = sum(x['c_oi']  for x in r['exp_rows'])
        tot_p_oi   = sum(x['p_oi']  for x in r['exp_rows'])
        tot_pc_vol = round(tot_p_vol / tot_c_vol if tot_c_vol else 0, 2)
        tot_pc_oi  = round(tot_p_oi  / tot_c_oi  if tot_c_oi  else 0, 2)
        exp_rows_html += f"""
<tr class="row-total">
  <td colspan="2"><strong>합계</strong></td>
  <td class="pc-cell">
    <div class="pc-line"><span class="pc-lbl">Vol</span><span style="color:{_pc_color(tot_pc_vol)};font-weight:700">{tot_pc_vol:.2f}</span></div>
    <div class="pc-line"><span class="pc-lbl">OI&nbsp;</span><span style="color:{_pc_color(tot_pc_oi)};font-weight:700">{tot_pc_oi:.2f}</span></div>
  </td>
  <td></td><td></td><td></td><td></td>
</tr>"""

        # 상위 스트라이크 표
        top_c_rows = ''.join(
            f"<tr><td>${x['strike']:,.2f}</td><td>{int(x['oi']):,}</td></tr>"
            for x in r['top_calls']
        )
        top_p_rows = ''.join(
            f"<tr><td>${x['strike']:,.2f}</td><td>{int(x['oi']):,}</td></tr>"
            for x in r['top_puts']
        )

        # ── GEX HTML 준비 ──────────────────────────────────
        gex      = r.get('gex', {})
        ngb      = gex.get('net_gex_b', 0) or 0
        cwall    = gex.get('call_wall')
        pwall    = gex.get('put_wall')
        gflip    = gex.get('gamma_flip')
        ngb_cls  = 'gex-pos' if ngb >= 0 else 'gex-neg'
        ngb_str  = f'{"+" if ngb >= 0 else ""}${ngb:.3f}B'
        if ngb >= 0.5:
            gex_regime = '딜러 롱감마 ✅ — 딜러가 하락시 매수·상승시 매도 → 시장 안정화 (변동성 억제)'
        elif ngb >= 0:
            gex_regime = '딜러 약한 롱감마 — 시장 소폭 안정화'
        elif ngb >= -0.3:
            gex_regime = '딜러 약한 숏감마 ⚠ — 변동성 증폭 가능성'
        else:
            gex_regime = '딜러 숏감마 🔴 — 딜러가 하락시 매도·상승시 매수 → 변동성 폭발 위험'
        cwall_str = f'${cwall:,.2f}' if cwall else 'N/A'
        pwall_str = f'${pwall:,.2f}' if pwall else 'N/A'
        cwall_diff = f'(+{(cwall-curr)/curr*100:.1f}%)' if cwall else ''
        pwall_diff = f'({(pwall-curr)/curr*100:.1f}%)' if pwall else ''
        gflip_str  = f'${gflip:,.2f}' if gflip else 'N/A'
        gflip_rel  = ('▲ 현재가 위 ✅ — 딜러 롱감마 구간, 안정화 작동 중' if gflip and gflip > curr
                      else '▼ 현재가 아래 ⚠ — 딜러 숏감마 구간, 변동 증폭 위험' if gflip and gflip < curr
                      else '≈ 현재가 근접 — 감마 플립 전환 경계')
        gflip_cls  = 'gex-pos' if gflip and gflip > curr else 'gex-neg'

        # Expected Move 위치 표시
        near_em_row = next((row for row in r['exp_rows']
                            if row['straddle_em'] > 0 and row['days'] > 0), None)
        if near_em_row:
            em_upper = near_em_row['upper_price']
            em_lower = near_em_row['lower_price']
            em_pct   = near_em_row['straddle_em_pct']
            em_days  = near_em_row['days']
            em_range = em_upper - em_lower
            if em_range > 0:
                em_pos = max(0, min(100, (curr - em_lower) / em_range * 100))
            else:
                em_pos = 50
            em_hint = '✅ 기대범위 안' if 20 < em_pos < 80 else '⚠ 기대범위 경계 근처'
            em_html = f"""
    <div class="em-section">
      <div class="em-title">📐 기대변동 위치 — {em_days}일 후 만기 기준 (±{em_pct:.1f}%)</div>
      <div class="em-track-wrap">
        <span class="em-bound">▼${em_lower:,.0f}</span>
        <div class="em-track">
          <div class="em-zone"></div>
          <div class="em-cursor" style="left:{em_pos:.1f}%"></div>
        </div>
        <span class="em-bound">▲${em_upper:,.0f}</span>
      </div>
      <div class="em-hint">{em_hint}</div>
    </div>"""
        else:
            em_html = ''

        cards += f"""
<div class="card">

  <!-- 헤더 -->
  <div class="card-header">
    <div class="title-row">
      <span class="sym">{sym}</span>
      <span class="lbl">{r['label']}</span>
      <span class="price">${curr:,.2f}</span>
    </div>
    <div class="meta-sub">전체 {r['exp_count']}개 만기일 &nbsp;|&nbsp; 날짜·OI·IV: CBOE = optioncharts.io &nbsp;|&nbsp; 기대변동: ATM 콜+풋 스트래들 미드가 = barchart expected-move 동일 방식</div>
  </div>

  <!-- 요약 통계 -->
  <div class="stats-grid">
    <div class="sbox">
      <div class="slbl">전체 P/C OI</div>
      <div class="sval" style="color:{sig_color}">{pc_oi:.2f}</div>
      <div class="ssub" style="color:{sig_color}">{sig}</div>
      <div class="pc-note">※ P/C &gt; 1.3은 기관 헤지일 수 있어 단순 약세 신호가 아닐 수 있음</div>
    </div>
    <div class="sbox">
      <div class="slbl">전체 P/C Volume</div>
      <div class="sval">{r['pc_vol']:.2f}</div>
      <div class="ssub">{pc_signal(r['pc_vol'])[0]}</div>
    </div>
    <div class="sbox">
      <div class="slbl">1개월 Max Pain</div>
      <div class="sval">{mp_str}</div>
      <div class="ssub">옵션 매도자 유리 가격{f' &nbsp;<span style="color:#e65100;font-size:9px">{mp_urgency}</span>' if mp_urgency else ''}</div>
    </div>
    <div class="sbox">
      <div class="slbl">콜 OI / 풋 OI</div>
      <div class="sval"><span class="up">{r['tc_oi']:,}</span> / <span class="dn">{r['tp_oi']:,}</span></div>
      <div class="ssub">전체 Open Interest</div>
    </div>
    <div class="sbox">
      <div class="slbl">이번주 만기 OI</div>
      <div class="sval">{r['near_oi']:,}</div>
      <div class="ssub">7일 이내</div>
    </div>
    <div class="sbox">
      <div class="slbl">1개월 이내 만기 OI</div>
      <div class="sval">{r['far_oi']:,}</div>
      <div class="ssub">8~35일</div>
    </div>
    <div class="sbox">
      <div class="slbl">IV 콜 평균</div>
      <div class="sval">{r['iv_call']:.1f}%</div>
      <div class="ssub">1개월 이내 만기</div>
    </div>
    <div class="sbox">
      <div class="slbl">IV 풋 평균</div>
      <div class="sval">{r['iv_put']:.1f}%</div>
      <div class="ssub">1개월 이내 만기</div>
    </div>
  </div>

  {em_html}

  <!-- GEX (Gamma Exposure) 요약 — GexScreener 동일 지표 -->
  <div class="gex-grid">
    <div class="gex-box">
      <div class="gex-lbl">⚡ Net GEX (1개월이내)</div>
      <div class="gex-val {ngb_cls}">{ngb_str}</div>
      <div class="gex-sub">{gex_regime}</div>
    </div>
    <div class="gex-box">
      <div class="gex-lbl">🔄 Gamma Flip</div>
      <div class="gex-val {gflip_cls}">{gflip_str}</div>
      <div class="gex-sub">{gflip_rel}</div>
    </div>
    <div class="gex-box">
      <div class="gex-lbl">🟢 Call Wall</div>
      <div class="gex-val gex-pos">{cwall_str}</div>
      <div class="gex-sub">콜 감마 집중 저항 {cwall_diff}</div>
    </div>
    <div class="gex-box">
      <div class="gex-lbl">🔴 Put Wall</div>
      <div class="gex-val gex-neg">{pwall_str}</div>
      <div class="gex-sub">풋 감마 집중 지지 {pwall_diff}</div>
    </div>
  </div>
  <div class="gex-note">
    <span>GEX 해석:</span> &nbsp;
    Gamma Flip 위 = 딜러가 가격 오를 때 팔고, 내릴 때 사줌 (안정) &nbsp;|&nbsp;
    Gamma Flip 아래 = 딜러가 하락을 따라 팜 (증폭) &nbsp;|&nbsp;
    Call Wall = 강한 저항선 &nbsp;|&nbsp; Put Wall = 강한 지지선 &nbsp;|&nbsp;
    Black-Scholes 감마 × OI × 100 × 현재가 (CBOE IV 사용, = GexScreener 동일 방식)
  </div>

  <!-- GEX by Strike 차트 -->
  <div class="section">
    <div class="section-title">⚡ GEX (Gamma Exposure) by Strike — 현재가±18% · 1개월이내 &nbsp;
      <span style="font-weight:400;font-size:10px;color:#aaa">🟢양수=안정 / 🔴음수=변동성증폭 &nbsp;|&nbsp; 단위: $M</span>
    </div>
    <div style="position:relative;height:220px;">
      <canvas id="chart-{sym}-gex"></canvas>
    </div>
  </div>

  <!-- 만기별 상세 표 -->
  <div class="section">
    <div class="section-title">📋 만기일별 옵션 배팅 상세</div>
    <div class="table-wrap" id="tw-{sym}">
      <table class="exp-table">
        <colgroup>
          <col class="c-date"><col class="c-days"><col class="c-pc">
          <col class="c-iv"><col class="c-em"><col class="c-mp"><col class="c-cmt">
        </colgroup>
        <thead>
          <tr>
            <th>만기일</th>
            <th>잔존</th>
            <th title="마우스 올리면 원본 수량 표시">P/C<br><span style="font-weight:400;font-size:9px;color:#aaa">Vol / OI</span></th>
            <th>IV</th>
            <th>기대변동<br><span style="font-weight:400;font-size:9px;color:#aaa">±% · ±$ · 범위</span></th>
            <th>Max Pain<br><span style="font-weight:400;font-size:9px;color:#aaa">현재가대비</span></th>
            <th>해설</th>
          </tr>
        </thead>
        <tbody>{exp_rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- 전체 캘린더 차트 -->
  <div class="charts-row">
    <div class="chart-box chart-box-full">
      <div class="section-title">📅 전체 캘린더 — 만기일 OI (모든 날짜 · 만기일만 바 표시 · ★표시)</div>
      <div class="tab-row">
        <button class="tbtn active" onclick="switchCalTab('{sym}','oi',this)">OI</button>
        <button class="tbtn" onclick="switchCalTab('{sym}','vol',this)">Volume</button>
      </div>
      <div class="cal-scroll-wrap">
        <div class="cal-inner" id="cal-inner-{sym}-oi">
          <canvas id="chart-{sym}-cal-oi" height="220"></canvas>
        </div>
        <div class="cal-inner" id="cal-inner-{sym}-vol" style="display:none">
          <canvas id="chart-{sym}-cal-vol" height="220"></canvas>
        </div>
      </div>
    </div>
  </div>

  <!-- 스트라이크 차트 -->
  <div class="charts-row">
    <div class="chart-box" style="grid-column:1/-1;">
      <div class="section-title">📊 스트라이크별 OI — 현재가±18% (1개월 이내)</div>
      <div class="tab-row">
        <button class="tbtn active" onclick="switchTab('{sym}','oi',this)">OI</button>
        <button class="tbtn" onclick="switchTab('{sym}','vol',this)">Volume</button>
      </div>
      <div style="position:relative;height:240px;">
        <canvas id="chart-{sym}-oi"></canvas>
        <canvas id="chart-{sym}-vol" style="display:none"></canvas>
      </div>
    </div>
  </div>

  <!-- 상위 스트라이크 -->
  <div class="tables-row">
    <div class="tbl-box">
      <div class="tbl-title up">🟢 상위 콜 OI (강세 배팅) — 1개월 이내</div>
      <table><thead><tr><th>스트라이크</th><th>OI</th></tr></thead>
      <tbody>{top_c_rows}</tbody></table>
    </div>
    <div class="tbl-box">
      <div class="tbl-title dn">🔴 상위 풋 OI (약세 배팅) — 1개월 이내</div>
      <table><thead><tr><th>스트라이크</th><th>OI</th></tr></thead>
      <tbody>{top_p_rows}</tbody></table>
    </div>
  </div>

</div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason Market — 옵션 모니터 (QQQ/SPY/GOOGL)</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#f0f2f5;color:#222;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;}}
a{{color:inherit;}}

.top-header{{background:#1a237e;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;}}
.top-header h1{{font-size:16px;font-weight:700;}}
.top-header .meta{{font-size:11px;color:#aaa;}}


.page{{max-width:1500px;margin:0 auto;padding:16px;display:flex;flex-direction:column;gap:20px;}}

.card{{background:#fff;border:1px solid #ddd;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);}}
.card-header{{padding:14px 20px;background:#fafafa;border-bottom:1px solid #eee;}}
.title-row{{display:flex;align-items:baseline;gap:10px;}}
.sym{{font-size:24px;font-weight:800;color:#1a1a2e;}}
.lbl{{font-size:12px;color:#999;flex:1;}}
.price{{font-size:22px;font-weight:700;color:#1a5fa8;}}
.meta-sub{{font-size:11px;color:#bbb;margin-top:5px;}}

.stats-grid{{display:grid;grid-template-columns:repeat(8,1fr);gap:1px;background:#e8e8e8;}}
.sbox{{padding:10px 14px;background:#fff;}}
.slbl{{font-size:9px;color:#aaa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.sval{{font-size:15px;font-weight:700;color:#222;}}
.ssub{{font-size:9px;color:#aaa;margin-top:2px;}}
.pc-note{{font-size:9px;color:#bbb;margin-top:2px;line-height:1.4}}
.em-section{{padding:10px 20px;background:#f8f9ff;border-top:1px solid #eee;border-bottom:1px solid #eee;}}
.em-title{{font-size:11px;font-weight:700;color:#555;margin-bottom:6px}}
.em-track-wrap{{display:flex;align-items:center;gap:8px}}
.em-bound{{font-size:11px;font-family:monospace;color:#888;width:80px}}
.em-bound:last-child{{text-align:left}}
.em-track{{flex:1;height:14px;background:#e8eaf0;border-radius:7px;position:relative}}
.em-zone{{position:absolute;left:20%;width:60%;height:100%;background:#e8f5e9;border-radius:7px}}
.em-cursor{{position:absolute;top:-4px;width:6px;height:22px;background:#1565c0;border-radius:3px;transform:translateX(-50%);box-shadow:0 1px 4px rgba(0,0,0,.2)}}
.em-hint{{font-size:11px;color:#888;margin-top:4px;text-align:center}}
.up{{color:#1a8a7a;}}.dn{{color:#d32f2f;}}

.section{{padding:14px 20px;border-top:1px solid #f0f0f0;}}
.section-title{{font-size:12px;font-weight:700;color:#555;margin-bottom:10px;}}

/* ─── 만기별 상세 표 ─── */
/* table-wrap은 그냥 컨테이너 역할만, 좌우 스크롤 없음 */
.table-wrap{{overflow:visible;}}
/* 테이블 전체 너비 = 열 합산 고정값(auto) — 화면 가득 채우지 않음 */
.exp-table{{width:auto;min-width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed;}}
/* 열 너비 — 합계 약 670px, 해설은 딱 200px */
.exp-table col.c-date{{width:105px;}}
.exp-table col.c-days{{width:52px;}}
.exp-table col.c-pc  {{width:88px;}}
.exp-table col.c-iv  {{width:50px;}}
.exp-table col.c-em  {{width:100px;}}
.exp-table col.c-mp  {{width:86px;}}
.exp-table col.c-cmt {{width:200px;}}  /* 고정 200px — 2~3줄 줄바꿈 */

.exp-table thead th{{background:#1a1a2e;color:#fff;padding:6px 8px;font-size:10px;
                     text-align:center;position:sticky;top:0;z-index:2;
                     border-right:1px solid #2d2d44;}}
.exp-table thead th:first-child{{text-align:left;}}
.exp-table thead th:last-child{{text-align:right;border-right:none;}}
.exp-table tbody td{{padding:5px 7px;border-bottom:1px solid #f0f0f0;
                     vertical-align:top;border-right:1px solid #f5f5f5;}}
.exp-table tbody td:last-child{{border-right:none;}}
.exp-table tbody td.exp-date{{font-weight:600;color:#333;font-family:monospace;font-size:11px;}}
.exp-table tbody td.exp-date .wd{{display:block;font-family:sans-serif;font-size:9px;
                                   color:#1a5fa8;font-weight:600;margin-top:1px;}}
.exp-table tbody td.num{{text-align:right;font-variant-numeric:tabular-nums;}}
.exp-table tbody tr:hover td{{background:#f5f8ff;}}
.exp-table tbody tr.row-near{{background:#fff5f5;}}
.exp-table tbody tr.row-near:hover td{{background:#ffe8e8;}}
.exp-table tbody tr.row-mid{{background:#fffff5;}}
.exp-table tbody tr.row-total{{background:#f0f4ff;font-size:11px;}}
.exp-table tbody tr.row-total td{{padding:6px 7px;border-top:2px solid #dde;}}

.iv-hi{{color:#ef5350;font-weight:700;}}
.iv-mid{{color:#ff9800;font-weight:600;}}
.iv-lo{{color:#26a69a;}}

/* P/C 합성 셀 — Vol·OI P/C + OI 미니바; 원본 숫자는 hover tooltip */
.pc-cell{{cursor:help;}}
.pc-line{{display:flex;align-items:center;justify-content:space-between;
          font-size:10.5px;line-height:1.6;}}
.pc-lbl{{color:#aaa;font-size:9px;}}

/* 기대변동 셀 — ±% 굵게, ±$ 서브, 범위 */
.em-cell2{{text-align:right;}}
.em-val{{font-size:11.5px;font-weight:700;color:#1a1a2e;}}
.em-sub{{font-size:9.5px;color:#888;}}
.em-range{{font-size:9.5px;}}
.em-up{{color:#1a8a7a;font-weight:600;}}
.em-dn{{color:#d32f2f;font-weight:600;}}

/* Max Pain 합성 셀 */
.mp-cell{{text-align:right;}}
.mp-price{{font-size:11.5px;font-weight:700;color:#333;}}
.mp-diff{{font-size:10px;font-weight:600;}}

/* 해설 — 2~3줄 줄바꿈, 우측 정렬 (끝부분이 항상 오른쪽에 맞춰짐) */
.comment-cell{{font-size:10px;color:#444;line-height:1.7;
               text-align:right;white-space:normal;
               word-break:keep-all;overflow-wrap:break-word;}}

.badge{{display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;}}
.b-red{{background:#fdecea;color:#c62828;}}
.b-orange{{background:#fff3e0;color:#e65100;}}
.b-gray{{background:#f5f5f5;color:#555;}}
.b-light{{background:#fafafa;color:#aaa;}}

.pc-bar-wrap{{width:80px;height:8px;border-radius:4px;overflow:hidden;display:flex;}}
.pc-bar-c{{background:#26a69a;height:100%;}}
.pc-bar-p{{background:#ef5350;height:100%;}}

.charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#eee;border-top:1px solid #eee;}}
.chart-box{{padding:14px 18px;background:#fff;}}
.chart-box-full{{grid-column:1/-1;}}
.tab-row{{display:flex;gap:5px;margin-bottom:8px;}}
.tbtn{{padding:3px 11px;border:1px solid #ccc;background:#f0f0f0;color:#666;border-radius:3px;cursor:pointer;font-size:11px;}}
.tbtn.active{{background:#1a5fa8;border-color:#1a5fa8;color:#fff;}}

.cal-scroll-wrap{{overflow-x:auto;overflow-y:hidden;border:1px solid #eee;border-radius:4px;}}
.cal-inner{{height:260px;min-width:100%;}}

.tables-row{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#eee;border-top:1px solid #eee;}}
.tbl-box{{padding:12px 18px;background:#fff;}}

/* GEX 섹션 */
.gex-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#2a1a0e;border-top:2px solid #ff9800;}}
.gex-box{{padding:10px 14px;background:#1a1208;}}
.gex-lbl{{font-size:9px;color:#cc8800;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.gex-val{{font-size:15px;font-weight:700;}}
.gex-sub{{font-size:9px;color:#888;margin-top:2px;}}
.gex-pos{{color:#26c6a0;}}
.gex-neg{{color:#ef5350;}}
.gex-neu{{color:#ffa726;}}
.gex-note{{padding:7px 14px;background:#120e04;font-size:10px;color:#888;border-top:1px solid #2a1a0e;}}
.gex-note span{{color:#ffa726;}}
.tbl-title{{font-size:11px;font-weight:700;margin-bottom:8px;}}
table{{width:100%;border-collapse:collapse;font-size:12px;}}
th{{color:#999;font-weight:500;padding:4px 8px;border-bottom:1px solid #eee;text-align:right;}}
th:first-child{{text-align:left;}}
td{{padding:4px 8px;border-bottom:1px solid #f5f5f5;text-align:right;}}
td:first-child{{text-align:left;color:#333;}}
</style>
</head>
<body>
<div class="top-header">
  <h1>Jason Market — 옵션 모니터 (QQQ / SPY / GOOGL)</h1>
  <div class="meta">업데이트: {timestamp} &nbsp;|&nbsp; 날짜·OI: CBOE = optioncharts.io &nbsp;|&nbsp; 기대변동: ATM스트래들 = barchart 방식</div>
</div>
<div class="page">{cards}</div>

<script>
const ALL = {data_js};

function switchTab(sym, mode, el) {{
  el.closest('.chart-box').querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('chart-'+sym+'-oi').style.display  = mode==='oi'  ? '' : 'none';
  document.getElementById('chart-'+sym+'-vol').style.display = mode==='vol' ? '' : 'none';
}}

function switchCalTab(sym, mode, el) {{
  el.closest('.chart-box').querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('cal-inner-'+sym+'-oi').style.display  = mode==='oi'  ? '' : 'none';
  document.getElementById('cal-inner-'+sym+'-vol').style.display = mode==='vol' ? '' : 'none';
}}

function makeCalChart(canvasId, wrapperId, cal, mode) {{
  const ctx     = document.getElementById(canvasId);
  const wrapper = document.getElementById(wrapperId);
  if (!ctx || !wrapper) return;

  const dates   = cal.dates;
  const callOI  = cal.call_oi;
  const putOI   = cal.put_oi;
  const callVol = cal.call_vol;
  const putVol  = cal.put_vol;

  const callData = mode === 'oi' ? callOI  : callVol;
  const putData  = mode === 'oi' ? putOI   : putVol;
  const isExp    = dates.map((_,i) => callOI[i] > 0 || putOI[i] > 0);
  const totals   = callData.map((v,i) => v + putData[i]);
  const maxTot   = Math.max(...totals, 1);

  const W = Math.max(dates.length * 10, 900);
  wrapper.style.width = W + 'px';
  ctx.style.width = W + 'px';
  ctx.width = W;

  const wds = ['일','월','화','수','목','금','토'];
  const labels = dates.map((d,i) => {{
    if (!isExp[i]) return '';
    const dt = new Date(d);
    return d.slice(5) + '(' + wds[dt.getUTCDay()] + ')★';
  }});

  const cColors = callData.map((v,i) =>
    isExp[i] ? `rgba(38,166,154,${{0.3 + 0.65*(totals[i]/maxTot)}})` : 'rgba(0,0,0,0)');
  const pColors = putData.map((v,i) =>
    isExp[i] ? `rgba(239,83,80,${{0.3 + 0.65*(totals[i]/maxTot)}})` : 'rgba(0,0,0,0)');

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{label:'콜', data:callData, backgroundColor:cColors, borderWidth:0, borderRadius:2, barPercentage:0.6}},
        {{label:'풋', data:putData,  backgroundColor:pColors, borderWidth:0, borderRadius:2, barPercentage:0.6}},
      ]
    }},
    options: {{
      responsive: false,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{labels:{{color:'#555',font:{{size:11}}}}}},
        tooltip: {{
          filter: item => totals[item.dataIndex] > 0,
          callbacks: {{
            title: items => {{
              const i  = items[0].dataIndex;
              const d  = dates[i];
              const dt = new Date(d);
              const diff = Math.round((dt - new Date()) / 86400000);
              return d + ' (' + wds[dt.getUTCDay()] + ')' +
                (isExp[i] ? '  ★만기  D' + (diff >= 0 ? '-'+diff : '+'+Math.abs(diff)) : '');
            }},
            label: c => c.dataset.label + ': ' + c.raw.toLocaleString()
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{
            color: '#1a5fa8',
            font:  {{size:8, weight:'bold'}},
            maxRotation: 90,
            autoSkip: false,
          }},
          grid: {{color:'#f0f0f0'}}
        }},
        y: {{
          ticks: {{
            color: '#888', font: {{size:10}},
            callback: v => v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v
          }},
          grid: {{color:'#f0f0f0'}}
        }}
      }}
    }}
  }});
}}

function makeStrikeChart(canvasId, d, curr, maxPain) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  const isVol    = canvasId.endsWith('-vol');
  const callData = isVol ? d.call_vol : d.call_oi;
  const putData  = isVol ? d.put_vol  : d.put_oi;

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: d.strikes.map(l=>'$'+l.toFixed(0)),
      datasets: [
        {{label:'콜', data:callData,           backgroundColor:'rgba(38,166,154,0.75)',borderWidth:0}},
        {{label:'풋', data:putData.map(v=>-v), backgroundColor:'rgba(239,83,80,0.75)', borderWidth:0}},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{labels:{{color:'#555',font:{{size:11}}}}}},
        tooltip: {{
          callbacks: {{
            label: ctx => ctx.dataset.label+': '+Math.abs(ctx.raw).toLocaleString()
          }}
        }}
      }},
      scales: {{
        x: {{ticks:{{color:'#888',font:{{size:9}},maxRotation:45}},grid:{{color:'#f5f5f5'}}}},
        y: {{ticks:{{color:'#888',font:{{size:10}},
               callback:v=>Math.abs(v)>=1e3?(Math.abs(v)/1e3).toFixed(0)+'K':Math.abs(v)}},
             grid:{{color:'#f0f0f0'}}}}
      }}
    }}
  }});
}}

function makeGexChart(canvasId, gex, curr) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx || !gex || !gex.strikes || !gex.strikes.length) return;

  const labels   = gex.strikes.map(s => '$' + s.toFixed(0));
  const netData  = gex.net_gex;
  const callData = gex.call_gex;
  const putData  = gex.put_gex.map(v => -v);  // 아래로 표시

  // 스트라이크별 색상: 양수=녹색, 음수=빨강, Gamma Flip/Wall 강조
  const flip  = gex.gamma_flip;
  const cwall = gex.call_wall;
  const pwall = gex.put_wall;
  const barColors = netData.map((v, i) => {{
    const s = gex.strikes[i];
    if (Math.abs(s - flip)  < 0.5) return 'rgba(255,165,0,0.95)';   // Gamma Flip: 주황
    if (Math.abs(s - cwall) < 0.5) return 'rgba(0,230,180,1.0)';    // Call Wall: 밝은 녹색
    if (Math.abs(s - pwall) < 0.5) return 'rgba(255,80,80,1.0)';    // Put Wall: 밝은 빨강
    return v >= 0 ? 'rgba(38,166,154,0.75)' : 'rgba(239,83,80,0.75)';
  }});

  // 현재가에 가장 가까운 스트라이크 인덱스
  const currIdx = gex.strikes.reduce((bi, s, i) =>
    Math.abs(s - curr) < Math.abs(gex.strikes[bi] - curr) ? i : bi, 0);

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{
          label: 'Net GEX ($M)',
          data: netData,
          backgroundColor: barColors,
          borderWidth: 0,
          borderRadius: 2,
        }},
        {{
          label: '콜 GEX ($M)',
          data: callData,
          backgroundColor: 'rgba(38,166,154,0.25)',
          borderWidth: 0,
          borderRadius: 1,
          hidden: true,
        }},
        {{
          label: '풋 GEX ($M)',
          data: putData,
          backgroundColor: 'rgba(239,83,80,0.25)',
          borderWidth: 0,
          borderRadius: 1,
          hidden: true,
        }},
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{
          labels: {{color:'#ccc', font:{{size:11}}}},
        }},
        tooltip: {{
          callbacks: {{
            title: items => {{
              const s = gex.strikes[items[0].dataIndex];
              const tag = Math.abs(s - flip)  < 0.5 ? ' 🔄 Gamma Flip' :
                          Math.abs(s - cwall) < 0.5 ? ' 🟢 Call Wall'  :
                          Math.abs(s - pwall) < 0.5 ? ' 🔴 Put Wall'   : '';
              return '$' + s.toFixed(2) + tag;
            }},
            label: c => c.dataset.label + ': $' + Math.abs(c.raw).toFixed(1) + 'M'
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{
            color: ctx2 => {{
              const s = gex.strikes[ctx2.index];
              return Math.abs(s - curr) < 0.5 ? '#ff9800' : '#888';
            }},
            font: {{size:9}},
            maxRotation: 45,
          }},
          grid: {{color:'#2a2a2a'}}
        }},
        y: {{
          ticks: {{
            color: '#888',
            font: {{size:10}},
            callback: v => (v >= 0 ? '+' : '') + v.toFixed(0) + 'M'
          }},
          grid: {{color:'#2a2a2a'}},
          border: {{color:'#555'}}
        }}
      }}
    }}
  }});
}}

ALL.forEach(r => {{
  if (!r) return;
  makeCalChart('chart-'+r.sym+'-cal-oi',  'cal-inner-'+r.sym+'-oi',  r.cal_chart, 'oi');
  makeCalChart('chart-'+r.sym+'-cal-vol', 'cal-inner-'+r.sym+'-vol', r.cal_chart, 'vol');
  makeStrikeChart('chart-'+r.sym+'-oi',  r.chart, r.curr, r.max_pain);
  makeStrikeChart('chart-'+r.sym+'-vol', r.chart, r.curr, r.max_pain);
  makeGexChart('chart-'+r.sym+'-gex', r.gex, r.curr);
}});

</script>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""

# ── 메인 ─────────────────────────────────────────────────

def main():
    print(f"\n{'━'*55}")
    print(f"  Jason 옵션 모니터  (QQQ / SPY / GOOGL)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*55}")
    print("  CBOE delayed quotes 수집 중 (약 10-20초)...\n")

    results = []
    for sym, label in ASSETS:
        r = process(sym, label)
        results.append(r)
        if r:
            sig, _ = pc_signal(r['pc_oi'])
            print(f"  {sym}  현재가 ${r['curr']:,.2f}  |  P/C OI {r['pc_oi']:.2f}  ({sig})")
            print(f"       Max Pain ${r['max_pain']:,.2f}" if r['max_pain'] else "       Max Pain N/A")
            print(f"       만기 {r['exp_count']}개\n")
        else:
            print(f"  {sym}  데이터 수집 실패\n")

    timestamp    = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_content = generate_html(results, timestamp)

    DIR       = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(DIR, 'options_dashboard.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"  브라우저에서 오픈 중...")
    webbrowser.open(f'file://{html_path}')
    print(f"  완료!\n")
    print("  보는 법:")
    print("  - P/C 비율 > 1.0 : 풋 많음 (헤지/약세)  < 0.7 : 콜 많음 (강세)")
    print("  - Max Pain : 옵션 매도자 입장에서 가장 유리한 만기 가격")
    print("  - 기대변동폭 : ATM 스트래들 미드가 (= barchart expected-move)")
    print("  - GEX 양수 : 딜러 롱감마 → 가격 안정 / GEX 음수 : 딜러 숏감마 → 변동성 증폭")
    print("  - Gamma Flip : 이 가격 아래로 내려가면 딜러가 하락을 오히려 증폭시킴")
    print("  - Call Wall : 강한 저항 / Put Wall : 강한 지지\n")

if __name__ == '__main__':
    main()
