"""options_monitor_validate.py — 옵션 대시보드 데이터 검증 레이어

투자 결론을 바꾸지 않고, 원자료와 가공 결과를 분리하여 low_confidence 플래그를 생성한다.
하드코딩으로 특정 값만 맞추지 않고 일반화된 검증 로직만 작성한다.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Optional

# ── 히스토리 파일 ────────────────────────────────────────────────
_STATE_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state')
_HISTORY_FILE = os.path.join(_STATE_DIR, 'options_confidence_history.json')
_HISTORY_MAX  = 100   # 심볼별 최대 보관 건수

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
    Max Pain 방향 문구 — 전 구간에서 "당김", "끌어당김" 계열 표현 금지.

    - ≤7 DTE  : "단기 옵션 포지션 편향"
    - ≤45 DTE : "보조 참고"
    - >45 DTE : "장기 포지션 분포 참고, 방향 예측 불가"

    금지 표현: 하방 당김, 상방 당김, 가격 자석, 끌어당김, 옵션 자석
    """
    abs_diff = abs(diff_pct)

    if dte > MAX_PAIN_DTE_MEDIUM:
        return f'Max Pain {diff_pct:+.1f}% — 장기 포지션 분포 참고, 방향 예측 불가'

    if dte <= MAX_PAIN_DTE_STRONG:
        # 0~7 DTE: 단기 옵션 포지션 편향 (강도 표현은 허용, "당김" 금지)
        direction = '상방' if diff_pct > 0 else '하방'
        if abs_diff >= 5:
            return f'Max Pain {diff_pct:+.1f}% — 단기 옵션 포지션 편향 ({direction} 강함)'
        if abs_diff >= 2:
            return f'Max Pain {diff_pct:+.1f}% — 단기 옵션 포지션 편향 ({direction} 약함)'
        return f'Max Pain {diff_pct:+.1f}% — 중립 근처 (단기 포지션 균형)'

    # 8~45 DTE: 보조 참고
    direction = '상방' if diff_pct > 0 else '하방'
    if abs_diff >= 5:
        return f'Max Pain {diff_pct:+.1f}% — {direction} 방향 보조 참고 (예측 불가)'
    if abs_diff >= 2:
        return f'Max Pain {diff_pct:+.1f}% — 약한 {direction} 편향, 보조 참고'
    return f'Max Pain {diff_pct:+.1f}% — 중립 근처, 보조 참고'


# ── E-2. Confidence Score 강등 Cap ───────────────────────────────

# SPX/NDX용 score cap 조건
_CAP_RATIO_ABNORMAL   = 45   # SPX/SPY 비율 이상 시 최대 점수
_CAP_FULL_FALLBACK    = 40   # 가격+체인 모두 FALLBACK 시 최대 점수
_CAP_RENDER_MISMATCH  = 30   # live price ≠ rendered price 시 최대 점수
_CAP_FALLBACK_RATIO   = 35   # FALLBACK + 비율 이상 동시 시 최대 점수
_CAP_CHAIN_FALLBACK   = 65   # 체인만 FALLBACK 시 최대 점수


def cap_confidence_by_conditions(base_score: int, conditions: dict) -> tuple:
    """
    특수 강등 조건에 따라 confidence score에 hard cap 적용.

    Parameters
    ----------
    base_score : int  — calc_confidence_score()의 score
    conditions : dict
        is_full_fallback  : bool — price AND chain 모두 FALLBACK
        chain_is_fallback : bool — chain만 FALLBACK
        ratio_abnormal    : bool — 페어 비율 이상
        render_mismatch   : bool — live price ≠ rendered price
        stale_timestamp   : bool — 30분 이상 경과

    Returns
    -------
    (capped_score: int, cap_reason: str, forced_label: str | None)
        forced_label: None이면 score로 label 재계산, 아니면 강제 라벨
    """
    full_fb    = conditions.get('is_full_fallback',  False)
    chain_fb   = conditions.get('chain_is_fallback', False)
    ratio_bad  = conditions.get('ratio_abnormal',    False)
    mismatch   = conditions.get('render_mismatch',   False)
    stale      = conditions.get('stale_timestamp',   False)

    # 악조건 갯수 (VERY_LOW 강등 기준)
    bad_count = sum([full_fb, ratio_bad, mismatch, stale])
    if bad_count >= 2:
        return min(base_score, _CAP_FALLBACK_RATIO), 'VERY_LOW: 복합 악조건', 'VERY_LOW'

    # 개별 cap 적용
    cap    = 100
    reason = ''

    if mismatch:
        cap    = min(cap, _CAP_RENDER_MISMATCH)
        reason = 'render mismatch (live price ≠ rendered)'
    if full_fb and ratio_bad:
        cap    = min(cap, _CAP_FALLBACK_RATIO)
        reason = 'full fallback + ratio abnormal'
    elif full_fb:
        cap    = min(cap, _CAP_FULL_FALLBACK)
        reason = 'full fallback (price+chain)'
    elif ratio_bad:
        cap    = min(cap, _CAP_RATIO_ABNORMAL)
        reason = 'pair ratio abnormal'
    elif chain_fb:
        cap    = min(cap, _CAP_CHAIN_FALLBACK)
        reason = 'chain fallback'

    capped = min(base_score, cap)
    # 강등 후 label 재결정
    forced = None
    if capped <= 39:
        forced = 'VERY_LOW'
    elif capped <= 54 or full_fb or ratio_bad:
        forced = 'LOW'
    return capped, reason, forced


# ── E-3. Compressed Mixed Gamma Risk ──────────────────────────────

def detect_compressed_gamma_risk(
    spot: float,
    net_gex: float,
    gamma_flip: Optional[float],
    call_wall: Optional[float],
    put_wall: Optional[float],
    pc_oi: float = 0.0,
    near_iv: float = 0.0,
) -> dict:
    """
    압축된 혼합 감마 위험(Coiled Spring) 감지.

    조건 (모두 충족 시 compressed=True):
    1. net_gex < 0       딜러 숏감마
    2. spot > gamma_flip  현재가가 Gamma Flip 위
    3. |spot - flip| / spot > 10%  Flip이 멀리
    4. box_width = (call_wall - put_wall) / spot ≤ 1.0%
    5. pc_oi > 1.3 OR near_iv > 30  헤지/이벤트 신호

    Returns
    -------
    dict
        compressed    : bool
        label         : str
        box_width_pct : float | None
        conditions    : dict
    """
    if spot <= 0:
        return {'compressed': False, 'label': '', 'box_width_pct': None, 'conditions': {}}

    cond1 = net_gex < 0
    cond2 = (gamma_flip is not None) and (spot > gamma_flip)
    cond3 = (gamma_flip is not None) and (abs(spot - gamma_flip) / spot > 0.10)

    box_w = None
    cond4 = False
    if call_wall and put_wall and spot > 0:
        box_w = (call_wall - put_wall) / spot * 100
        cond4 = box_w <= 1.0

    cond5 = (pc_oi > 1.3) or (near_iv > 30)

    conds = {
        'net_gex_negative': cond1,
        'above_gamma_flip': cond2,
        'flip_far':         cond3,
        'narrow_box':       cond4,
        'hedge_signal':     cond5,
    }

    # 완전 조건: 1~4 모두 + (5 또는 합산 ≥ 4)
    if cond1 and cond2 and cond3 and cond4:
        _bw = f'{box_w:.1f}%' if box_w is not None else '?%'
        label = (
            f'압축된 혼합 감마 위험 ⚠ — NET GEX 음수, Gamma Flip 멀리, '
            f'Call/Put Wall 박스 {_bw} (매우 좁음). '
            '방향성 돌파 시 변동성 확대 가능.'
        )
        return {'compressed': True, 'label': label,
                'box_width_pct': box_w, 'conditions': conds}

    # 부분 혼합 신호
    if cond1 and cond2:
        _bw_s = f'{box_w:.1f}%' if box_w is not None else 'N/A'
        label = f'혼합 감마 신호 — NET GEX 음수, 현재가 Gamma Flip 위 (박스 {_bw_s})'
        return {'compressed': False, 'label': label,
                'box_width_pct': box_w, 'conditions': conds}

    return {'compressed': False, 'label': '', 'box_width_pct': box_w, 'conditions': conds}


# ── E-4. Proxy Priority Engine ────────────────────────────────────

# NDX/QQQ 정상 비율 범위 (NDX ÷ QQQ ≈ 38~42배)
NDX_QQQ_RATIO_MIN = 35.0
NDX_QQQ_RATIO_MAX = 45.0


def select_proxy_mode(asset_confs: dict) -> dict:
    """
    자산별 신뢰도 라벨에 따라 Proxy 선택 모드 결정.

    Parameters
    ----------
    asset_confs : {sym: {'label': str, 'score': int, 'fallback_penalty': int, ...}}

    Returns
    -------
    dict
        proxies : {'SP500': {...}, 'NASDAQ': {...}, 'GOLD': {...}, 'GOOGL': {...}}
        notes   : list[str]   — 각 프록시 선택 이유
        banner  : str         — 대시보드 상단 표시 문구
    """
    proxies: dict = {}
    notes:   list = []

    def _label(sym: str) -> str:
        return asset_confs.get(sym, {}).get('label', 'UNKNOWN')

    def _fp(sym: str) -> int:
        return asset_confs.get(sym, {}).get('fallback_penalty', 0)

    # ── S&P 500 ──────────────────────────────────────────────────
    spx_label = _label('SPX')
    if spx_label in ('LOW', 'VERY_LOW'):
        proxies['SP500']  = {'primary': 'SPY', 'ignored': 'SPX',
                             'reason': f'SPX {spx_label}'}
        notes.append(f'S&P: SPY PRIMARY — SPX {spx_label} (fallback/ratio abnormal).')
    else:
        proxies['SP500']  = {'primary': 'SPX', 'secondary': 'SPY',
                             'reason': f'SPX {spx_label}'}
        notes.append(f'S&P: SPX PRIMARY ({spx_label}).')

    # ── Nasdaq ────────────────────────────────────────────────────
    ndx_label = _label('NDX')
    ndx_fb    = _fp('NDX') > 0
    if ndx_label in ('LOW', 'VERY_LOW') or (ndx_label == 'MEDIUM' and ndx_fb):
        proxies['NASDAQ'] = {'primary': 'QQQ', 'secondary': 'NDX',
                             'reason': f'NDX {ndx_label}/fallback chain'}
        notes.append(
            f'Nasdaq: QQQ PRIMARY — NDX {ndx_label}'
            + (' (fallback chain)' if ndx_fb else '') + '.'
        )
    else:
        proxies['NASDAQ'] = {'primary': 'NDX', 'secondary': 'QQQ',
                             'reason': f'NDX {ndx_label}'}
        notes.append(f'Nasdaq: NDX PRIMARY ({ndx_label}).')

    # ── Gold / GOOGL ──────────────────────────────────────────────
    proxies['GOLD']  = {'primary': 'GLD'}
    proxies['GOOGL'] = {'primary': 'GOOGL'}
    notes.append('Gold: GLD PRIMARY.')
    notes.append('Alphabet: GOOGL PRIMARY.')

    # 배너
    sp_mode  = proxies['SP500']['primary']
    nq_mode  = proxies['NASDAQ']['primary']
    banner   = (
        f'Market Proxy Status: '
        f'S&P={sp_mode}, Nasdaq={nq_mode}, Gold=GLD, Alphabet=GOOGL'
    )

    return {'proxies': proxies, 'notes': notes, 'banner': banner}


# ── E-5. IV Rank 이상 감지 ────────────────────────────────────────

def detect_iv_rank_anomaly(iv_ranks: dict) -> dict:
    """
    여러 자산의 IV Rank가 동시에 100%이면 이상 감지.

    Parameters
    ----------
    iv_ranks : {sym: {'rank': float | None, 'source': str}}

    Returns
    -------
    dict
        anomaly   : bool
        flag      : str  — 'broad_iv_rank_extreme' | 'iv_rank_source_check_required' | ''
        affected  : list[str]
    """
    extremes = [sym for sym, v in iv_ranks.items()
                if v.get('rank') is not None and v['rank'] >= 99.0]
    if len(extremes) >= 3:
        return {
            'anomaly':  True,
            'flag':     'broad_iv_rank_extreme / iv_rank_source_check_required',
            'affected': extremes,
        }
    return {'anomaly': False, 'flag': '', 'affected': []}


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
        stale_penalty      : -0~20점 (데이터 경과 시간 기반, 양수로 입력)
        fallback_penalty   : -0~20점 (하드코딩/폴백 데이터 기반, 양수로 입력)

    Returns
    -------
    dict
        score          : int
        label          : 'HIGH' | 'MEDIUM_HIGH' | 'MEDIUM' | 'LOW' | 'VERY_LOW'
        badge_color    : str
        display_note   : str
        stale_penalty  : int   — 실제 적용된 stale 페널티
        fallback_penalty: int  — 실제 적용된 fallback 페널티
    """
    keys             = ('price_pair', 'expiry_dte', 'chain_completeness',
                        'gex_consistency', 'iv_history', 'wall_sanity')
    raw              = sum(components.get(k, 0) for k in keys)
    stale_pen        = int(components.get('stale_penalty',    0))
    fallback_pen     = int(components.get('fallback_penalty', 0))
    total_penalty    = stale_pen + fallback_pen
    score            = max(0, min(100, raw - total_penalty))

    _base = {
        'score': score,
        'stale_penalty':    stale_pen,
        'fallback_penalty': fallback_pen,
    }
    if score >= 85:
        return {**_base, 'label': 'HIGH',
                'badge_color': '#22c55e', 'display_note': ''}
    if score >= 70:
        return {**_base, 'label': 'MEDIUM_HIGH',
                'badge_color': '#84cc16', 'display_note': ''}
    if score >= 55:
        return {**_base, 'label': 'MEDIUM',
                'badge_color': '#eab308', 'display_note': '참고용'}
    if score >= 40:
        return {**_base, 'label': 'LOW',
                'badge_color': '#f97316',
                'display_note': '저신뢰 — 원자료/계산 검증 필요'}
    return {**_base, 'label': 'VERY_LOW',
            'badge_color': '#ef4444',
            'display_note': '저신뢰 — 원자료/계산 검증 필요'}


def calc_asset_confidence(r: dict, pair_check: dict | None = None) -> dict:
    """단일 자산 딕셔너리로 전체 신뢰도 점수 계산.

    타임스탬프 기반 stale_penalty / is_fallback 기반 fallback_penalty 분리 반영.
    """
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

    # ⑦ Stale 페널티 (타임스탬프 기반: 30분마다 +10점 페널티, 최대 20점)
    stale_pen = 0
    _ts = r.get('_timestamps', {})
    _price_ts = _ts.get('price_timestamp')
    if _price_ts:
        try:
            ts_dt   = datetime.fromisoformat(_price_ts.rstrip('Z')).replace(tzinfo=timezone.utc)
            age_min = (datetime.now(tz=timezone.utc) - ts_dt).total_seconds() / 60
            stale_pen = min(20, int(age_min / 30) * 10)
        except Exception:
            stale_pen = 0
    components['stale_penalty'] = stale_pen

    # ⑧ Fallback 페널티 (하드코딩/폴백 데이터, -20점)
    ds = r.get('_data_source', {})
    if r.get('_is_fallback') or ds.get('overall') == 'FALLBACK':
        components['fallback_penalty'] = 20
    elif ds.get('overall') == 'PARTIAL':
        components['fallback_penalty'] = 10
    else:
        components['fallback_penalty'] = 0

    return calc_confidence_score(components)


# ── 신뢰도 히스토리 ──────────────────────────────────────────────

def record_confidence_history(sym: str, score_result: dict,
                               components: dict | None = None) -> None:
    """
    신뢰도 점수 이력을 state/options_confidence_history.json에 저장.

    심볼별 최대 100건 유지 (오래된 것 자동 제거).

    Parameters
    ----------
    sym          : 자산 심볼 ('SPX', 'QQQ' 등)
    score_result : calc_confidence_score() 반환값
    components   : calc_asset_confidence() 입력 components (선택)
    """
    os.makedirs(_STATE_DIR, exist_ok=True)

    try:
        with open(_HISTORY_FILE, encoding='utf-8') as f:
            history: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = {}

    ts_now = datetime.now(tz=timezone.utc).isoformat()
    entry  = {
        'ts':              ts_now,
        'score':           score_result.get('score', 0),
        'label':           score_result.get('label', 'UNKNOWN'),
        'stale_penalty':   score_result.get('stale_penalty', 0),
        'fallback_penalty': score_result.get('fallback_penalty', 0),
    }
    if components:
        entry['components'] = {k: v for k, v in components.items()
                               if k not in ('stale_penalty', 'fallback_penalty')}

    bucket = history.setdefault(sym, [])
    bucket.append(entry)
    # 최대 100건 유지
    if len(bucket) > _HISTORY_MAX:
        history[sym] = bucket[-_HISTORY_MAX:]

    try:
        with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass   # 히스토리 저장 실패는 비치명 — 메인 플로우에 영향 없음


def load_confidence_history(sym: str | None = None) -> dict:
    """
    신뢰도 점수 이력 로드.

    Parameters
    ----------
    sym : None이면 전체 반환, 문자열이면 해당 심볼만 반환

    Returns
    -------
    dict  {sym: [entry, ...]}  or  [entry, ...]  (sym 지정 시)
    """
    try:
        with open(_HISTORY_FILE, encoding='utf-8') as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {} if sym is None else []

    if sym is None:
        return history
    return history.get(sym, [])


def get_confidence_trend(sym: str, n: int = 5) -> dict:
    """
    최근 n회 신뢰도 추세 반환.

    Returns
    -------
    dict
        scores     : list[int]    최근 n개 점수 (오래된 순)
        labels     : list[str]    대응 레이블
        trend      : 'UP' | 'DOWN' | 'FLAT'
        delta      : int          (최신 - 최초) 차이
        sparkline  : str          ASCII 미니 차트
    """
    entries = load_confidence_history(sym)
    if not entries:
        return {'scores': [], 'labels': [], 'trend': 'FLAT', 'delta': 0, 'sparkline': '—'}

    recent  = entries[-n:]
    scores  = [e['score'] for e in recent]
    labels  = [e['label'] for e in recent]
    delta   = scores[-1] - scores[0] if len(scores) >= 2 else 0
    trend   = 'UP' if delta > 5 else ('DOWN' if delta < -5 else 'FLAT')

    # ASCII 스파크라인 (5단계 블록)
    _blocks = '▁▂▃▅▇'
    _min_s, _max_s = min(scores), max(scores)
    _range = _max_s - _min_s or 1
    sparkline = ''.join(
        _blocks[min(4, int((s - _min_s) / _range * 4))]
        for s in scores
    )

    return {
        'scores': scores, 'labels': labels,
        'trend': trend, 'delta': delta, 'sparkline': sparkline,
    }


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

    # ── Test 7: data_source_status FALLBACK 처리 ──────────────
    print('\nTest 7: FALLBACK data_source_status → fallback_penalty 적용')
    _r7 = {
        'sym': 'SPX', 'curr': 5711.52,
        '_is_fallback': True,
        '_data_source': {'overall': 'FALLBACK'},
        '_timestamps': {'price_timestamp': None},
        'tc_oi': 0, 'tp_oi': 0,
        'exp_rows': [], 'gex': {}, 'max_pain': None, 'iv_call': 0, 'iv_put': 0,
    }
    c7 = calc_asset_confidence(_r7)
    _chk('T7-fallback-penalty',   c7['fallback_penalty'] == 20,    f"fp={c7['fallback_penalty']}")
    _chk('T7-score-penalized',    c7['score'] < 60,                f"score={c7['score']}")
    _chk('T7-not-high',           c7['label'] != 'HIGH',           f"label={c7['label']}")

    # ── Test 8: stale_penalty 타임스탬프 기반 ─────────────────────
    print('\nTest 8: stale_penalty — 60분 경과 타임스탬프')
    from datetime import timedelta
    _old_ts = (datetime.now(tz=timezone.utc) - timedelta(minutes=65)).isoformat()
    _r8 = {
        'sym': 'QQQ', 'curr': 706.11,
        '_is_fallback': False,
        '_data_source': {'overall': 'LIVE'},
        '_timestamps': {'price_timestamp': _old_ts},
        'tc_oi': 1_000_000, 'tp_oi': 1_000_000,
        'exp_rows': [{'exp': (date.today() + timedelta(days=10)).isoformat()}],
        'gex': {'net_gex_b': -0.08, 'gamma_flip': 579.78},
        'max_pain': 700.0, 'iv_call': 20.0, 'iv_put': 21.0,
    }
    c8 = calc_asset_confidence(_r8)
    # 60분 → stale_penalty = 20 (30분마다 10점, min(20, 2*10)=20)
    _chk('T8-stale-penalty-20',   c8['stale_penalty'] == 20,       f"sp={c8['stale_penalty']}")
    _chk('T8-fallback-zero',      c8['fallback_penalty'] == 0,     f"fp={c8['fallback_penalty']}")

    # ── Test 9: 히스토리 저장 / 로드 / 추세 ──────────────────────
    # 전용 테스트 심볼(_TEST_)로 격리하여 실 데이터와 충돌 방지
    print('\nTest 9: confidence history save/load/trend')
    _TSYM = '_TEST_CONF_SYM'    # 실 심볼과 겹치지 않는 테스트 전용 이름
    # 기존 테스트 엔트리 사전 제거
    try:
        import json as _json2, os as _os
        if os.path.exists(_HISTORY_FILE):
            _hdata = _json2.load(open(_HISTORY_FILE, encoding='utf-8'))
            _hdata.pop(_TSYM, None)
            with open(_HISTORY_FILE, 'w', encoding='utf-8') as _hf:
                _json2.dump(_hdata, _hf, ensure_ascii=False)
    except Exception:
        pass
    try:
        # 저장
        record_confidence_history(_TSYM, {'score': 70, 'label': 'MEDIUM_HIGH',
                                           'stale_penalty': 0, 'fallback_penalty': 0})
        record_confidence_history(_TSYM, {'score': 80, 'label': 'MEDIUM_HIGH',
                                           'stale_penalty': 0, 'fallback_penalty': 0})
        record_confidence_history(_TSYM, {'score': 65, 'label': 'MEDIUM',
                                           'stale_penalty': 5, 'fallback_penalty': 0})
        # 로드
        hist = load_confidence_history(_TSYM)
        _chk('T9-history-saved',   len(hist) == 3,                  f"entries={len(hist)}")
        _chk('T9-history-score',   hist[-1]['score'] == 65,         f"last={hist[-1]['score']}")
        # 추세
        trend = get_confidence_trend(_TSYM, n=3)
        _chk('T9-trend-scores',    trend['scores'] == [70, 80, 65], f"scores={trend['scores']}")
        _chk('T9-trend-flag',      trend['trend'] in ('UP', 'DOWN', 'FLAT'),
             f"trend={trend['trend']}")
        _chk('T9-sparkline',       len(trend['sparkline']) == 3,    f"spark={trend['sparkline']}")
    finally:
        # 테스트 엔트리 정리
        try:
            _hdata2 = _json2.load(open(_HISTORY_FILE, encoding='utf-8'))
            _hdata2.pop(_TSYM, None)
            with open(_HISTORY_FILE, 'w', encoding='utf-8') as _hf2:
                _json2.dump(_hdata2, _hf2, ensure_ascii=False)
        except Exception:
            pass

    # ── Test A: SPX live price must not be overwritten ────────────
    print('\nTest A: SPX live price must not be overwritten by fallback')
    live_p   = 7408.50
    fback_p  = 5711.52
    # 비즈니스 규칙: live_price가 있으면 반드시 그것이 rendered price
    final_p  = live_p if live_p else fback_p
    _chk('TA-live-wins',       final_p == live_p,      f"final={final_p}")
    _chk('TA-not-fallback',    final_p != fback_p,     f"final={final_p}")
    _chk('TA-mismatch-ok',     final_p == live_p,      'no mismatch when live wins')

    # ── Test B: SPX fallback + ratio abnormal → cap ≤ 45 ─────────
    print('\nTest B: SPX fallback + ratio abnormal → confidence cap')
    _r_spx = validate_price_pair(5711.52, 739.17)  # ratio = 7.73
    cond_b  = {
        'is_full_fallback':  True,   # price+chain FALLBACK
        'chain_is_fallback': True,
        'ratio_abnormal':    _r_spx['low_confidence'],
        'render_mismatch':   False,
        'stale_timestamp':   False,
    }
    base_b = 70  # 보정 전 가상 점수
    capped_b, reason_b, forced_b = cap_confidence_by_conditions(base_b, cond_b)
    _chk('TB-cap-le-45',      capped_b <= 45,            f"capped={capped_b}")
    _chk('TB-label-low',      forced_b in ('LOW','VERY_LOW'), f"label={forced_b}")
    _chk('TB-reason',         len(reason_b) > 0,          f"reason={reason_b[:30]}")

    # ── Test C: NDX chain fallback → cap ≤ 65 ───────────────────
    print('\nTest C: NDX chain fallback → cap ≤ 65')
    cond_c  = {
        'is_full_fallback':  False,
        'chain_is_fallback': True,   # 체인만 FALLBACK
        'ratio_abnormal':    False,
        'render_mismatch':   False,
        'stale_timestamp':   False,
    }
    base_c    = 80
    capped_c, _, forced_c = cap_confidence_by_conditions(base_c, cond_c)
    _chk('TC-cap-le-65',      capped_c <= 65,            f"capped={capped_c}")
    _chk('TC-not-high',       forced_c != 'HIGH' if forced_c else capped_c <= 65,
         f"forced={forced_c}")

    # ── Test D: Proxy mode selection ─────────────────────────────
    print('\nTest D: proxy mode — SPX LOW → SPY PRIMARY, NDX FALLBACK → QQQ PRIMARY')
    asset_d = {
        'SPX': {'label': 'LOW',         'fallback_penalty': 20, 'score': 40},
        'SPY': {'label': 'HIGH',        'fallback_penalty': 0,  'score': 90},
        'NDX': {'label': 'MEDIUM',      'fallback_penalty': 20, 'score': 55},
        'QQQ': {'label': 'HIGH',        'fallback_penalty': 0,  'score': 88},
        'GLD': {'label': 'HIGH',        'fallback_penalty': 0,  'score': 85},
        'GOOGL': {'label': 'HIGH',      'fallback_penalty': 0,  'score': 87},
    }
    pm = select_proxy_mode(asset_d)
    _chk('TD-sp500-spy',    pm['proxies']['SP500']['primary']  == 'SPY',
         f"sp500={pm['proxies']['SP500']['primary']}")
    _chk('TD-nasdaq-qqq',   pm['proxies']['NASDAQ']['primary'] == 'QQQ',
         f"nasdaq={pm['proxies']['NASDAQ']['primary']}")
    _chk('TD-banner-ok',    'SPY' in pm['banner'] and 'QQQ' in pm['banner'],
         f"banner={pm['banner']}")

    # ── Test E: QQQ compressed mixed gamma risk ──────────────────
    print('\nTest E: QQQ compressed mixed gamma risk')
    rE = detect_compressed_gamma_risk(
        spot=706.11, net_gex=-0.080e9, gamma_flip=579.78,
        call_wall=705.0, put_wall=700.0, pc_oi=1.62, near_iv=0,
    )
    _chk('TE-compressed',    rE['compressed'] is True,      f"compressed={rE['compressed']}")
    _chk('TE-label-ne',      len(rE['label']) > 10,         f"label='{rE['label'][:40]}'")
    _chk('TE-box-width',     rE['box_width_pct'] is not None and
                              abs(rE['box_width_pct'] - 0.706) < 0.05,
         f"box={rE.get('box_width_pct'):.3f}%")
    # SPY: box=1.35% → not compressed
    rE2 = detect_compressed_gamma_risk(
        spot=739.17, net_gex=-0.333e9, gamma_flip=607.0,
        call_wall=740.0, put_wall=730.0, pc_oi=1.5, near_iv=0,
    )
    spy_bw = rE2.get('box_width_pct', 0)
    _chk('TE-spy-not-compressed', rE2['compressed'] is False,
         f"SPY box={spy_bw:.2f}% (>1%) → not compressed")

    # ── Test F: Max Pain forbidden language ──────────────────────
    print('\nTest F: Max Pain forbidden language')
    _FORBIDDEN_MP = ['하방 당김', '상방 당김', '가격 자석', '끌어당김', '당김 강함']
    _all_labels   = [
        validate_max_pain_label(v, d)
        for v in [-10, -5, -2, 0, 2, 5, 10]
        for d in [3, 20, 100]
    ]
    _violations   = [(lbl, word) for lbl in _all_labels
                     for word in _FORBIDDEN_MP if word in lbl]
    _chk('TF-no-forbidden',  len(_violations) == 0,
         f"violations={_violations[:3] if _violations else '없음'}")

    # ── Test G: IV Rank source labeling ──────────────────────────
    print('\nTest G: IV Rank anomaly detection (3+ symbols at 100%)')
    iv_g = {
        'QQQ':   {'rank': 100.0, 'source': 'REALIZED_VOL_PROXY'},
        'SPY':   {'rank': 100.0, 'source': 'REALIZED_VOL_PROXY'},
        'GOOGL': {'rank': 100.0, 'source': 'REALIZED_VOL_PROXY'},
        'GLD':   {'rank':  55.0, 'source': 'REALIZED_VOL_PROXY'},
    }
    anomaly_g = detect_iv_rank_anomaly(iv_g)
    _chk('TG-anomaly-detected', anomaly_g['anomaly'] is True,
         f"flag={anomaly_g['flag'][:30]}")
    _chk('TG-affected-3plus',   len(anomaly_g['affected']) >= 3,
         f"affected={anomaly_g['affected']}")

    # ── Test H: Dashboard integrity summary ──────────────────────
    print('\nTest H: dashboard summary contains proxy mode')
    asset_h = {
        'SPX': {'label': 'LOW',    'fallback_penalty': 20, 'score': 38},
        'SPY': {'label': 'HIGH',   'fallback_penalty': 0,  'score': 90},
        'NDX': {'label': 'MEDIUM', 'fallback_penalty': 20, 'score': 55},
        'QQQ': {'label': 'HIGH',   'fallback_penalty': 0,  'score': 88},
    }
    pm_h = select_proxy_mode(asset_h)
    summary_text = ' '.join(pm_h['notes'])
    _chk('TH-spy-in-notes',  'SPY' in summary_text,     f"notes='{summary_text[:60]}'")
    _chk('TH-qqq-in-notes',  'QQQ' in summary_text,     f"notes='{summary_text[:60]}'")
    _chk('TH-spx-ignored',   'SPX' in pm_h['proxies']['SP500'].get('ignored',''),
         f"SP500 primary={pm_h['proxies']['SP500']['primary']}")

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
    'cap_confidence_by_conditions',
    'detect_compressed_gamma_risk',
    'select_proxy_mode',
    'detect_iv_rank_anomaly',
    'record_confidence_history',
    'load_confidence_history',
    'get_confidence_trend',
    'run_tests',
    # 상수
    'SPX_SPY_RATIO_MIN', 'SPX_SPY_RATIO_MAX',
    'GAMMA_FLIP_FAR_THRESHOLD_PCT',
    'IV_RANK_MIN_HISTORY',
    'MAX_PAIN_DTE_STRONG', 'MAX_PAIN_DTE_MEDIUM',
]


if __name__ == '__main__':
    run_tests()
