from __future__ import annotations
"""옵션 모니터 — 분석 렌더링 모듈
IV Rank/Percentile, 0DTE 데이터 블록"""

from datetime import datetime
import numpy as np

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from options_monitor_validate import validate_iv_rank, validate_gex_regime


# ── MODULE 3: IV Rank / IV Percentile ────────────────────

def render_iv_rank(r: dict) -> dict:
    """현재 IV의 1년 내 위치(Rank, Percentile) — validate_iv_rank 사용."""
    try:
        if not YFINANCE_AVAILABLE:
            return {'rank': None, 'pct': None, 'status': 'yfinance 미설치',
                    'new_high': False, 'insufficient_history': True, 'low_confidence': True}

        mapper = {"SPX": "^SPX", "NDX": "^NDX",
                  "QQQ": "QQQ", "SPY": "SPY",
                  "GOOGL": "GOOGL", "GLD": "GLD"}
        y_sym = mapper.get(r['sym'], r['sym'])

        ticker = yf.Ticker(y_sym)
        hist   = ticker.history(period="1y")
        if hist.empty:
            return {'rank': None, 'pct': None,
                    'status': '데이터 수집 중 (초기 실행)',
                    'new_high': False, 'insufficient_history': True, 'low_confidence': True}

        returns  = np.log(hist['Close'] / hist['Close'].shift(1))
        vol_hist = returns.rolling(window=21).std() * np.sqrt(252) * 100
        vol_hist = vol_hist.dropna()

        curr_iv = (r['iv_call'] + r['iv_put']) / 2
        if curr_iv <= 0:
            curr_iv = float(vol_hist.iloc[-1]) if not vol_hist.empty else 20.0

        iv_list = vol_hist.tolist()
        v = validate_iv_rank(curr_iv, iv_list)

        # rank/pct가 None이면 화면 표시용 기본값 대신 None 유지 (100% 강제 금지)
        return {
            'rank': v['rank'],
            'pct':  v['percentile'],
            'status':              v['warning'] or 'OK',
            'new_high':            v.get('is_new_high', False),
            'insufficient_history': v['insufficient_history'],
            'low_confidence':       v['low_confidence'],
        }
    except Exception as e:
        return {'rank': None, 'pct': None,
                'status': f'오류: {str(e)}',
                'new_high': False, 'insufficient_history': True, 'low_confidence': True}


# ── MODULE 1: 0DTE 전용 렌더링 블록 ──────────────────────

def render_0dte_block(r: dict) -> dict | None:
    """오늘 만기(0DTE) 데이터 + GEX 레짐 분석 — validate_gex_regime 사용."""
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        zdte = next(
            (row for row in r['exp_rows']
             if row['days'] == 0 or row['exp'] == today_str),
            None
        )
        if not zdte:
            return None

        # [규칙 A-1] NET GEX 부호 + Gamma Flip 분리 검증
        gex   = r.get('gex', {})
        ngb   = gex.get('net_gex_b', 0) or 0
        gflip = gex.get('gamma_flip')
        curr  = r['curr']

        regime = validate_gex_regime(ngb * 1e9, curr, gflip)
        gex_dir     = regime['display_label']
        regime_color = regime['display_color']

        # 충돌/혼합 신호 주의문 추가
        if regime['final_regime'] == 'MIXED_SIGNAL':
            gex_dir += f' — {regime["caution_note"]}'
            bias = f'혼합 신호 ({regime["caution_note"][:40]}…)'
        elif regime['final_regime'] == 'LONG_GAMMA':
            bias = 'Pos Pinning (딜러 롱감마, 안정화)'
        else:
            bias = '숏감마 구간 (딜러 변동성 증폭 가능)'

        # Gamma Flip 위치 텍스트
        if gflip:
            if curr > gflip:
                flip_text = f"▼ 현재가 아래 — Gamma Flip {(gflip/curr-1)*100:.1f}%"
                if regime['final_regime'] == 'MIXED_SIGNAL':
                    flip_text += ' (혼합 신호, 단독 롱감마 판정 금지)'
                else:
                    flip_text += ' ✅'
            else:
                flip_text = f"▲ 현재가 위 ⚠ — Gamma Flip {(gflip/curr-1)*100:+.1f}%"
        else:
            flip_text = "Gamma Flip 데이터 없음"

        # [규칙 A-2] Call Wall 돌파 판단
        cw = r['gex']['call_wall']
        if r['curr'] > cw:
            call_wall_text = f"돌파 완료 구간 / 하방 지지 전환 ({(cw/r['curr']-1)*100:.1f}%)"
            call_wall_color = "#22c55e"
        else:
            call_wall_text = f"콜 감마 집중 저항 (+{(cw/r['curr']-1)*100:.1f}%)"
            call_wall_color = "#ef4444"

        # [규칙 A-3] Put Wall 텍스트 고정
        pw = r['gex']['put_wall']
        put_wall_text = f"풋 감마 집중 지지 ({(pw/r['curr']-1)*100:.1f}%)"
        put_wall_color = "#3b82f6"

        return {
            'exp': zdte['exp'], 'iv': zdte['iv'],
            'pc_vol': zdte['pc_vol'], 'pc_oi': zdte['pc_oi'],
            'em_pct': zdte['straddle_em_pct'], 'em_val': zdte['straddle_em'],
            'upper': zdte['upper_price'], 'lower': zdte['lower_price'],
            'mp': zdte['max_pain'], 'mp_diff': zdte['mp_diff'],
            'gex_dir': gex_dir, 'flip_text': flip_text,
            'bias': bias, 'regime_color': regime_color,
            'call_wall_text': call_wall_text, 'call_wall_color': call_wall_color,
            'put_wall_text': put_wall_text, 'put_wall_color': put_wall_color
        }
    except Exception as e:
        print(f"DEBUG: render_0dte_block error: {e}")
        return None


__all__ = ['render_iv_rank', 'render_0dte_block', 'YFINANCE_AVAILABLE']
