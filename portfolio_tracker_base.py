"""포트폴리오 트래커 — 기본 설정 및 포맷 유틸리티"""

import os
import json

from jm_lib.colors import ALERT, RESET

# ═══ 알람 키워드 ═══

EXTREME = ['극도공포', '극도탐욕', '강력매도', '강력매수', '매우높음', '즉시청산']


def alert_line(text: str) -> str:
    """극단 키워드가 있으면 ALERT 색상으로 강조"""
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text


# ═══ 포맷 헬퍼 ═══

def fmt_krw(val) -> str:
    """원화 포맷 (₩123,456)"""
    return f"₩{val:>15,.0f}"


def fmt_usd(val) -> str:
    """달러 포맷 ($123 또는 $0.12)"""
    return f"${val:>12,.0f}" if abs(val) >= 1000 else f"${val:>12,.2f}"


def fmt_pct(val) -> str:
    """퍼센트 포맷 (+1.23%)"""
    return f"{val:>+7.2f}%"


def _fmt_signed_krw_compact(val) -> str:
    """손익 금액 인라인 표시 (+₩123 / ₩-123)."""
    if val > 0:
        return f"+₩{val:,.0f}"
    return f"₩{val:,.0f}"


def calc_daily_return_pct(current_value, daily_pnl):
    """1일 수익률 = 1일손익 / 전일평가금액."""
    try:
        prev_value = current_value - daily_pnl
        if prev_value <= 0:
            return None
        return daily_pnl / prev_value * 100
    except Exception:
        return None


def format_daily_pnl_with_pct(daily_pnl, current_value, precalc_pct=None) -> str:
    """1일손익과 1일 수익률을 한 칸에 표시."""
    if daily_pnl is None:
        return '-'
    if precalc_pct is not None:
        pct = precalc_pct
    else:
        pct = calc_daily_return_pct(current_value, daily_pnl)
    pct_s = f"{pct:+.2f}%" if pct is not None else '-'
    return f"{_fmt_signed_krw_compact(daily_pnl)} ({pct_s})"


def format_total_pnl_with_pct(total_pnl, total_return_pct) -> str:
    """총손익과 기존 총 수익률을 한 칸에 표시."""
    if total_pnl is None or total_return_pct is None:
        return '-'
    return f"{_fmt_signed_krw_compact(total_pnl)} ({total_return_pct:+.2f}%)"


# ═══ 현금 추적 (일일·총손익 기준값 저장) ═══

_CASH_TRACKER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'state', 'cash_tracker.json'
)


def load_cash_tracker() -> dict:
    """cash_tracker.json 로드. 없으면 빈 dict 반환."""
    try:
        with open(_CASH_TRACKER_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_cash_tracker(tracker: dict):
    """cash_tracker.json 저장"""
    try:
        with open(_CASH_TRACKER_PATH, 'w', encoding='utf-8') as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


__all__ = [
    'EXTREME', 'alert_line',
    'fmt_krw', 'fmt_usd', 'fmt_pct',
    'calc_daily_return_pct', 'format_daily_pnl_with_pct',
    'format_total_pnl_with_pct',
    'load_cash_tracker', 'save_cash_tracker',
]
