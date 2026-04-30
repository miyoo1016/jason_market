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
    'load_cash_tracker', 'save_cash_tracker',
]
