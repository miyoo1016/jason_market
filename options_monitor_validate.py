"""options_monitor_validate.py — 옵션 대시보드 데이터 검증 레이어

투자 결론을 바꾸지 않고, 원자료와 가공 결과를 분리하여 low_confidence 플래그를 생성한다.
하드코딩으로 특정 값만 맞추지 않고 일반화된 검증 로직만 작성한다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

# ── 상수 ──────────────────────────────────────────────────────────

# SPX/SPY 역사적 비율 정상 범위 (10배 전후, ±1.5배 허용)
SPX_SPY_RATIO_MIN = 8.5
SPX_SPY_RATIO_MAX = 11.5

# Gamma Flip이 현재가 대비 10% 초과 이탈 시 "참고용" 강등
GAMMA_FLIP_FAR_THRESHOLD_PCT = 10.0

# IV Rank 최소 이력 관측치
IV_RANK_MIN_HISTORY = 30

# Max Pain 강한 해석 허용 DTE 상한
MAX_PAIN_DTE_STRONG  =  7    # ≤7 DTE  : 단기 참고 가능 (강한 표현 허용)
MAX_PAIN_DTE_MEDIUM  = 45    # ≤45 DTE : 보조 참고 (완화된 표현)
                              # >45 DTE : 방향 예측 문구 금지


# ── A. SPX/SPY 가격 페어 검증 ────────────────────────────────────

def validate_price_pair(
    index_price: float,
    etf_price: float,
    index_sym: str = 'SPX',
    etf_sym: str = 'SPY',
) -> dict:
    """
    인덱스/ETF 가격 비율 검증.

    SPX/SPY 정상 범위: 8.5 ~ 11.5x (역사적 ~10x).
    비율 이탈 시 downstream GEX/Wall/MaxPain 해석을 low_confidence로 처리.

    Returns
    -------
    dict
        ratio         : float | None
        is_normal     : bool
        confidence    : 'HIGH' | 'MEDIUM' | 'LOW'
        low_confidence: bool
        warning       : str
        score         : int   0~25 (confidence 기여분)
    """
    if etf_price <= 0:
        return {
            'ratio': None, 'is_normal': False,
            'confidence': 'LOW', 'low_confidence': True,
            'warning': f'{etf_sym} 가격 없음 — 비율 계산 불가',
            'score': 0,
        }

    ratio = index_price / etf_price

    if SPX_SPY_RATIO_MIN <= ratio <= SPX_SPY_RATIO_MAX:
        return {
            'ratio': round(ratio, 2), 'is_normal': True,
            'confidence': 'HIGH', 'low_confidence': False,
            'warning': '',
            'score': 25,
        }

    # 정상 범위 이탈 = LOW. 범위 내 경계 근접이면 MEDIUM (별도 경로에서 처리)
    confidence = 'LOW'
    score      = 5

    warning = (
        f'{index_sym}/{etf_sym} ratio abnormal: {ratio:.2f}x '
        f'(정상 범위 {SPX_SPY_RATIO_MIN}~{SPX_SPY_RATIO_MAX}x) '
        '— price source mismatch / stale data / split-adjusted value 확인 필요. '
        f'downstream {index_sym} GEX·Call/Put Wall·Max Pain 해석 저신뢰 처리.'
    )
    return {
        'ratio': round(ratio, 2), 'is_normal': False,
        'confidence': confidence, 'low_confidence': True,
        'warning': warning,
        'score': score,
    }


# ── B. 만기일 / DTE 검증 ─────────────────────────────────────────

def validate_expiry_dates(
    expiry_date_str: str,
    valuation_date: Optional[date] = None,
) -> dict:
    """
    만기일과 기준일(valuation_date)을 비교하여 DTE 및 expired 상태를 계산.

    DTE = max(expiry - valuation, 0).
    expired contract는 1개월 집계·GEX·OI·Max Pain·기대변동에서 제외 권장.

    Returns
    -------
    dict
        dte           : int
        expired       : bool
        valuation_date: str
        expiry_date   : str
        include_in_1m : bool  expired면 False
        score         : int   0~20
        warning       : str
    """
    val_date = valuation_date or datetime.now().date()

    try:
        exp_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
    except ValueError:
        return {
            'dte': 0, 'expired': True,
            'valuation_date': val_date.isoformat(),
            'expiry_date': expiry_date_str,
            'include_in_1m': False,
            'score': 0,
            'warning': f'만기일 파싱 오류: {expiry_date_str}',
        }

    delta    = (exp_date - val_date).days
    dte      = max(delta, 0)
    expired  = delta < 0

    warning = ''
    score   = 20

    if expired:
        warning = (
            f'만기 경과: {expiry_date_str} — 기준일 {val_date} 기준 {abs(delta)}일 전 만기. '
            '1개월 집계·GEX·OI·Max Pain·기대변동에서 제외 필요.'
        )
        score = 0
    elif dte == 0:
        warning = f'오늘 만기 (0DTE): {expiry_date_str}'
        score   = 18

    return {
        'dte': dte, 'expired': expired,
        'valuation_date': val_date.isoformat(),
        'expiry_date': expiry_date_str,
        'include_in_1m': not expired,
        'score': score,
        'warning': warning,
    }


# ── C/D. GEX 레짐 + Gamma Flip 거리 검증 ────────────────────────

def validate_gex_regime(
    net_gex: float,
    spot: float,
    gamma_flip: Optional[float],
) -> dict:
    """
    NET GEX 부호와 Gamma Flip 위치를 분리하여 레짐 판단.

    두 신호가 충돌하면 MIXED_SIGNAL — "롱감마 안정" 단독 표기 금지.
    Gamma Flip이 현재가 대비 10% 초과 이탈 시 gamma_flip_far = True.

    Returns
    -------
    dict
        net_gex_sign_regime        : 'LONG_GAMMA' | 'SHORT_GAMMA' | 'NEUTRAL'
        price_vs_gamma_flip_regime : 'ABOVE_FLIP'  | 'BELOW_FLIP'  | 'UNKNOWN'
        final_regime               : 'LONG_GAMMA' | 'SHORT_GAMMA' | 'MIXED_SIGNAL' | 'UNKNOWN'
        gamma_flip_far             : bool
        distance_pct               : float | None
        display_label              : str   화면 표시용 문구
        display_color              : str
        caution_note               : str   충돌 시 주의 문구
        flip_far_note              : str   Gamma Flip 이탈 주의 문구
        score                      : int   0~15
    """
    # ① NET GEX 부호 레짐
    if net_gex > 0:
        gex_sign_regime = 'LONG_GAMMA'
    elif net_gex < 0:
        gex_sign_regime = 'SHORT_GAMMA'
    else:
        gex_sign_regime = 'NEUTRAL'

    # ② Price vs Gamma Flip 레짐
    if gamma_flip is None or gamma_flip <= 0:
        flip_regime    = 'UNKNOWN'
        distance_pct   = None
        gamma_flip_far = False
    else:
        flip_regime    = 'ABOVE_FLIP' if spot > gamma_flip else 'BELOW_FLIP'
        distance_pct   = round(abs(spot - gamma_flip) / spot * 100, 2)
        gamma_flip_far = distance_pct >= GAMMA_FLIP_FAR_THRESHOLD_PCT

    # ③ 최종 레짐 결정
    if flip_regime == 'UNKNOWN':
        final_regime = 'UNKNOWN'
    elif gex_sign_regime == 'NEUTRAL':
        final_regime = flip_regime
    elif gex_sign_regime == 'LONG_GAMMA'  and flip_regime == 'ABOVE_FLIP':
        final_regime = 'LONG_GAMMA'
    elif gex_sign_regime == 'SHORT_GAMMA' and flip_regime == 'BELOW_FLIP':
        final_regime = 'SHORT_GAMMA'
    else:
        final_regime = 'MIXED_SIGNAL'   # 두 신호 충돌

    # ④ 화면 문구 결정
    caution_note = ''
    if final_regime == 'LONG_GAMMA':
        display_label = '딜러 롱감마 ✅ — 안정화 작동 가능성'
        display_color = '#22c55e'
    elif final_regime == 'SHORT_GAMMA':
        display_label = '딜러 숏감마 ⚠ — 변동성 증폭 위험'
        display_color = '#f97316'
    elif final_regime == 'MIXED_SIGNAL':
        display_label = '혼합 신호 / 검증 필요 ⚠'
        display_color = '#eab308'
        if gex_sign_regime == 'SHORT_GAMMA' and flip_regime == 'ABOVE_FLIP':
            caution_note = (
                f'NET GEX 음수({net_gex/1e9:+.3f}B)이나 현재가가 Gamma Flip 위. '
                '딜러 감마 해석 혼합 — 단독 롱감마 판정 금지.'
            )
        elif gex_sign_regime == 'LONG_GAMMA' and flip_regime == 'BELOW_FLIP':
            caution_note = (
                f'NET GEX 양수({net_gex/1e9:+.3f}B)이나 현재가가 Gamma Flip 아래. '
                '딜러 감마 해석 혼합 — 단독 숏감마 판정 금지.'
            )
    else:
        display_label = '레짐 판단 불가 (데이터 부족)'
        display_color = '#94a3b8'

    # ⑤ Gamma Flip 거리 주의 문구
    flip_far_note = ''
    if gamma_flip_far and distance_pct is not None:
        flip_far_note = (
            f'Gamma Flip은 현재가보다 {distance_pct:.1f}% 멀리 있어 '
            '단기 지지/저항보다는 구조 참고용.'
        )

    score = 15 if final_regime in ('LONG_GAMMA', 'SHORT_GAMMA') else (
            7  if final_regime == 'MIXED_SIGNAL' else 5)

    return {
        'net_gex_sign_regime':        gex_sign_regime,
        'price_vs_gamma_flip_regime': flip_regime,
        'final_regime':               final_regime,
        'gamma_flip_far':             gamma_flip_far,
        'distance_pct':               distance_pct,
        'display_label':              display_label,
        'display_color':              display_color,
        'caution_note':               caution_note,
        'flip_far_note':              flip_far_note,
        'score':                      score,
    }


# ── E. Max Pain DTE 제한 ─────────────────────────────────────────

def validate_max_pain_label(diff_pct: float, dte: int) -> str:
    """
    Max Pain 방향 문구를 DTE에 따라 제한.

    - ≤7 DTE  : 단기 참고 가능 (강한 표현 허용)
    - ≤45 DTE : 보조 참고 (완화된 표현)
    - >45 DTE : 방향 예측 금지 → "장기 포지션 분포 참고"만 허용

    Parameters
    ----------
    diff_pct : (max_pain - curr) / curr * 100
    dte      : Days to Expiry

    Returns
    -------
    str : 화면에 안전하게 표시할 Max Pain 문구
    """
    if dte > MAX_PAIN_DTE_MEDIUM:
        return f'Max Pain {diff_pct:+.1f}% — 장기 포지션 분포 참고 (방향 예측 불가)'

    abs_diff = abs(diff_pct)

    if dte <= MAX_PAIN_DTE_STRONG:
        if diff_pct >= 5:
            return f'Max Pain +{diff_pct:.1f}% → 상방 당김 강함'
        if diff_pct >= 2:
            return f'Max Pain +{diff_pct:.1f}% → 약한 상방 인력'
        if diff_pct <= -5:
            return f'Max Pain {diff_pct:.1f}% → 하방 당김 강함'
        if diff_pct <= -2:
            return f'Max Pain {diff_pct:.1f}% → 약한 하방 인력'
        return f'Max Pain {diff_pct:+.1f}% (중립 근처)'

    # 8~45 DTE: 완화된 표현
    if abs_diff >= 5:
        direction = '상방' if diff_pct > 0 else '하방'
        return f'Max Pain {diff_pct:+.1f}% — {direction} 방향 참고 (보조 지표)'
    if abs_diff >= 2:
        direction = '상방' if diff_pct > 0 else '하방'
        return f'Max Pain {diff_pct:+.1f}% — 약한 {direction} 편향 (보조 참고)'
    return f'Max Pain {diff_pct:+.1f}% (중립 근처, 보조 참고)'


# ── F. IV Rank 검증 ──────────────────────────────────────────────

def validate_iv_rank(
    current_iv: float,
    iv_history: list,
    min_required: int = IV_RANK_MIN_HISTORY,
) -> dict:
    """
    IV Rank / IV Percentile 계산 및 충분성 검증.

    산식:
    - IV Rank    = (current_iv - iv_min) / (iv_max - iv_min)
    - IV Pct     = lookback 중 current_iv 이하 비율

    특이 케이스:
    - len < min_required : insufficient_history = True, rank = None
    - iv_max == iv_min   : rank = None (분모 0 방지, 100% 강제 금지)

    Returns
    -------
    dict
        rank               : float | None
        percentile         : float | None
        insufficient_history: bool
        low_confidence     : bool
        is_new_high        : bool
        warning            : str
        score              : int   0~10
    """
    n = len(iv_history)
    if n < min_required:
        return {
            'rank': None, 'percentile': None,
            'insufficient_history': True,
            'low_confidence': True,
            'is_new_high': False,
            'warning': f'IV 이력 부족: {n}개 (최소 {min_required}개 필요)',
            'score': 0,
        }

    iv_min = min(iv_history)
    iv_max = max(iv_history)

    if iv_max == iv_min:
        return {
            'rank': None, 'percentile': None,
            'insufficient_history': False,
            'low_confidence': True,
            'is_new_high': False,
            'warning': (f'IV 범위 없음: min={iv_min:.1f}% == max={iv_max:.1f}% '
                        '— rank 계산 불가 (100% 강제 적용 금지)'),
            'score': 3,
        }

    rank_raw    = (current_iv - iv_min) / (iv_max - iv_min) * 100
    rank        = round(min(100.0, max(0.0, rank_raw)), 1)
    is_new_high = current_iv > iv_max
    pct         = round(sum(1 for v in iv_history if v < current_iv) / n * 100, 1)

    warning = ''
    score   = 10
    if is_new_high:
        warning = f'1년 신고 IV: {current_iv:.1f}% (역사적 최대 {iv_max:.1f}%)'
        score   = 8

    return {
        'rank': rank, 'percentile': pct,
        'insufficient_history': False,
        'low_confidence': False,
        'is_new_high': is_new_high,
        'warning': warning,
        'score': score,
    }


# ── G. Expected Move 검증 ────────────────────────────────────────

def validate_expected_move(
    dte: int,
    straddle_em: float,
    method: str = 'ATM Straddle',
) -> dict:
    """
    Expected Move 유효성 및 계산 방법 레이블 검증.

    DTE ≤ 0 이거나 straddle_em = 0 이면 계산 금지.

    Returns
    -------
    dict
        valid        : bool
        method_label : str
        warning      : str
    """
    if dte <= 0:
        return {
            'valid': False,
            'method_label': method,
            'warning': 'DTE=0 또는 만기 경과 — Expected Move 계산 금지',
        }
    if straddle_em <= 0:
        return {
            'valid': False,
            'method_label': method,
            'warning': 'ATM Straddle 가격 0 — Expected Move 계산 불가',
        }
    label = 'ATM Straddle 기반' if 'Straddle' in method else 'IV 기반 추정'
    return {'valid': True, 'method_label': label, 'warning': ''}


# ── 종합 신뢰도 점수 ─────────────────────────────────────────────

def calc_confidence_score(components: dict) -> dict:
    """
    각 검증 결과를 합산하여 0~100점 신뢰도 점수 산출.

    권장 가중치:
        price_pair         : 25점
        expiry_dte         : 20점
        chain_completeness : 15점
        gex_consistency    : 15점
        iv_history         : 10점
        wall_sanity        : 10점
        stale_penalty      : -0~30점 (페널티, 양수로 입력)

    Returns
    -------
    dict
        score        : int
        label        : 'HIGH' | 'MEDIUM_HIGH' | 'MEDIUM' | 'LOW' | 'VERY_LOW'
        badge_color  : str
        display_note : str
    """
    keys   = ('price_pair', 'expiry_dte', 'chain_completeness',
               'gex_consistency', 'iv_history', 'wall_sanity')
    raw    = sum(components.get(k, 0) for k in keys)
    penalty = components.get('stale_penalty', 0)
    score   = max(0, min(100, raw - penalty))

    if score >= 85:
        return {'score': score, 'label': 'HIGH',
                'badge_color': '#22c55e', 'display_note': ''}
    if score >= 70:
        return {'score': score, 'label': 'MEDIUM_HIGH',
                'badge_color': '#84cc16', 'display_note': ''}
    if score >= 55:
        return {'score': score, 'label': 'MEDIUM',
                'badge_color': '#eab308', 'display_note': '참고용'}
    if score >= 40:
        return {'score': score, 'label': 'LOW',
                'badge_color': '#f97316',
                'display_note': '저신뢰 — 원자료/계산 검증 필요'}
    return {'score': score, 'label': 'VERY_LOW',
            'badge_color': '#ef4444',
            'display_note': '저신뢰 — 원자료/계산 검증 필요'}


def calc_asset_confidence(r: dict, pair_check: dict | None = None) -> dict:
    """단일 자산 딕셔너리로 전체 신뢰도 점수 계산."""
    today      = datetime.now().date()
    components = {}

    # ① 가격 페어
    components['price_pair'] = pair_check.get('score', 25) if pair_check else 25

    # ② 만기/DTE
    exp_rows = r.get('exp_rows', [])
    if exp_rows:
        valid_n = sum(1 for row in exp_rows
                      if validate_expiry_dates(row['exp'], today)['include_in_1m'])
        components['expiry_dte'] = round(20 * valid_n / len(exp_rows))
    else:
        components['expiry_dte'] = 0

    # ③ 체인 완성도
    total_oi = r.get('tc_oi', 0) + r.get('tp_oi', 0)
    components['chain_completeness'] = 15 if total_oi > 10000 else (8 if total_oi > 0 else 0)

    # ④ GEX 일관성
    gex   = r.get('gex', {})
    ngb   = gex.get('net_gex_b')
    gflip = gex.get('gamma_flip')
    curr  = r.get('curr', 0)
    if ngb is not None and gflip and curr > 0:
        gex_v = validate_gex_regime(ngb * 1e9, curr, gflip)
        components['gex_consistency'] = gex_v['score']
    else:
        components['gex_consistency'] = 5

    # ⑤ IV 이력
    components['iv_history'] = 10 if (r.get('iv_call', 0) + r.get('iv_put', 0)) > 0 else 0

    # ⑥ Wall/MaxPain 타당성
    mp = r.get('max_pain')
    if mp and curr > 0 and abs(mp - curr) / curr < 0.20:
        components['wall_sanity'] = 10
    else:
        components['wall_sanity'] = 5

    # ⑦ 스테일 페널티
    components['stale_penalty'] = 15 if r.get('_is_fallback', False) else 0

    return calc_confidence_score(components)


# ── 테스트 스위트 ────────────────────────────────────────────────

def run_tests() -> list:
    """
    6개 테스트 케이스 실행.

    Returns
    -------
    list[(name: str, passed: bool, detail: str)]
    """
    results = []

    def _chk(name: str, cond: bool, detail: str = '') -> bool:
        results.append((name, cond, detail))
        status = '✅ PASS' if cond else '❌ FAIL'
        msg    = f'  {status}: {name}'
        if detail:
            msg += f' — {detail}'
        print(msg)
        return cond

    print('\n' + '═' * 55)
    print('  OPTIONS MONITOR VALIDATION TEST SUITE')
    print('═' * 55)

    # ── Test 1: SPX/SPY ratio sanity ──────────────────────────
    print('\nTest 1: SPX/SPY ratio sanity')
    r1 = validate_price_pair(5711.52, 739.17, 'SPX', 'SPY')
    _chk('T1-ratio',         abs(r1['ratio'] - 7.73) < 0.01,     f"ratio={r1['ratio']}")
    _chk('T1-confidence-low', r1['confidence'] == 'LOW',          f"conf={r1['confidence']}")
    _chk('T1-low-confidence', r1['low_confidence'] is True)
    _chk('T1-warning-ratio',  'ratio abnormal' in r1['warning'],  f"warn='{r1['warning'][:50]}'")

    # ── Test 2: Expired expiry ──────────────────────────────────
    print('\nTest 2: expired expiry date')
    r2 = validate_expiry_dates('2026-05-15', date(2026, 5, 17))
    _chk('T2-dte-zero',       r2['dte'] == 0,                     f"dte={r2['dte']}")
    _chk('T2-expired',        r2['expired'] is True)
    _chk('T2-exclude-1m',     r2['include_in_1m'] is False)
    _chk('T2-warning',        '만기 경과' in r2['warning'],        f"warn='{r2['warning'][:40]}'")

    # ── Test 3: Negative GEX but above Gamma Flip ──────────────
    print('\nTest 3: negative GEX but above Gamma Flip')
    r3 = validate_gex_regime(-0.080e9, 706.11, 579.78)
    _chk('T3-net-gex-short',  r3['net_gex_sign_regime'] == 'SHORT_GAMMA')
    _chk('T3-above-flip',     r3['price_vs_gamma_flip_regime'] == 'ABOVE_FLIP')
    _chk('T3-mixed-signal',   r3['final_regime'] == 'MIXED_SIGNAL')
    _chk('T3-no-long-only',   '롱감마 안정' not in r3['display_label'],
         f"label='{r3['display_label']}'")
    _chk('T3-caution-note',   len(r3['caution_note']) > 0,
         f"note='{r3['caution_note'][:40]}'")

    # ── Test 4: Far gamma flip ──────────────────────────────────
    print('\nTest 4: far gamma flip')
    r4 = validate_gex_regime(-0.080e9, 706.11, 579.78)
    dist_expected = abs(706.11 - 579.78) / 706.11 * 100
    _chk('T4-distance',       abs((r4['distance_pct'] or 0) - dist_expected) < 0.1,
         f"dist={r4['distance_pct']:.2f}% (expected≈{dist_expected:.2f}%)")
    _chk('T4-gamma-flip-far', r4['gamma_flip_far'] is True)
    _chk('T4-far-note',       '구조 참고용' in r4['flip_far_note'],
         f"note='{r4['flip_far_note'][:40]}'")

    # ── Test 5: IV rank insufficient history ────────────────────
    print('\nTest 5: IV rank insufficient history')
    r5 = validate_iv_rank(25.0, [20.0, 22.0], min_required=30)
    _chk('T5-insuff-history', r5['insufficient_history'] is True)
    _chk('T5-rank-null',      r5['rank'] is None)
    _chk('T5-low-confidence', r5['low_confidence'] is True)

    # ── Test 6: Long-dated Max Pain ─────────────────────────────
    print('\nTest 6: long-dated Max Pain (DTE=215)')
    r6 = validate_max_pain_label(-10.0, 215)
    _chk('T6-no-strong-down', '하방 당김 강함' not in r6,         f"label='{r6}'")
    _chk('T6-long-term-ref',  '장기 포지션 분포 참고' in r6,      f"label='{r6}'")

    # ── 결과 요약 ────────────────────────────────────────────────
    total  = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f'\n{"═"*55}')
    print(f'  결과: {passed}/{total} PASSED'
          + (' ✅ ALL PASS' if passed == total else ' ❌ FAILURES'))
    print('═' * 55 + '\n')
    return results


__all__ = [
    'validate_price_pair',
    'validate_expiry_dates',
    'validate_gex_regime',
    'validate_max_pain_label',
    'validate_iv_rank',
    'validate_expected_move',
    'calc_confidence_score',
    'calc_asset_confidence',
    'run_tests',
    # 상수
    'SPX_SPY_RATIO_MIN', 'SPX_SPY_RATIO_MAX',
    'GAMMA_FLIP_FAR_THRESHOLD_PCT',
    'IV_RANK_MIN_HISTORY',
    'MAX_PAIN_DTE_STRONG', 'MAX_PAIN_DTE_MEDIUM',
]


if __name__ == '__main__':
    run_tests()
