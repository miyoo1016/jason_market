"""옵션 모니터 — 기본 상수, 헬퍼, 헬프 함수
ALERT 색상, 자산 목록, CBOE URL, P/C 시그널, 요일·월물 판별"""

import re
from datetime import datetime

from jm_lib.colors import ALERT, RESET

# ═══ 알람 키워드 ═══

EXTREME = ['극도공포', '극도탐욕', '강력매도', '강력매수', '매우높음', '즉시청산']


def alert_line(text: str) -> str:
    """극단 키워드 포함 시 ALERT 색상으로 강조"""
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text


# ═══ 자산 목록 ═══

ASSETS = [
    ('SPX',   'S&P 500 Index'),
    ('NDX',   'Nasdaq 100 Index'),
    ('QQQ',   'Nasdaq 100 ETF'),
    ('SPY',   'S&P 500 ETF'),
    ('GOOGL', 'Alphabet Inc.'),
    ('GLD',   '금 ETF (SPDR Gold)'),
]

# ═══ CBOE API 설정 ═══

CBOE_URL = 'https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json'
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

# CBOE 옵션 심볼 파싱: 'QQQ260327C00450000' → ('2026-03-27', 'C', 450.0)
_OPT_RE = re.compile(r'^([A-Z]+)(\d{6})([CP])(\d{8})$')


def parse_opt_sym(sym: str) -> tuple:
    """CBOE 옵션 심볼 파싱 → (expiry, cp, strike)"""
    m = _OPT_RE.match(sym or '')
    if not m:
        return None, None, None
    _, ds, cp, ss = m.groups()
    expiry = f'20{ds[:2]}-{ds[2:4]}-{ds[4:6]}'
    strike = int(ss) / 1000.0
    return expiry, cp, strike


# ═══ P/C 시그널 ═══

def pc_signal(pc: float) -> tuple:
    """P/C 비율 → (라벨, 색상)"""
    if pc >= 1.5:
        return ('극도 풋 우세 (강한 헤지/약세)', '#ef5350')
    if pc >= 1.0:
        return ('풋 우세 (약세 배팅)', '#ff7043')
    if pc >= 0.7:
        return ('중립', '#888')
    if pc >= 0.5:
        return ('콜 우세 (강세 배팅)', '#26a69a')
    return ('극도 콜 우세 (강한 강세)', '#00bcd4')


def pc_color(pc: float) -> str:
    """P/C 비율 → 색상 코드"""
    if pc >= 1.5:
        return '#ef5350'
    if pc >= 1.0:
        return '#ff7043'
    if pc >= 0.7:
        return '#888'
    if pc >= 0.5:
        return '#26a69a'
    return '#00bcd4'


# ═══ 만기 날짜 헬퍼 ═══

_KO_DAYS = ['월', '화', '수', '목', '금', '토', '일']


def weekday_ko(exp_str: str) -> str:
    """YYYY-MM-DD → 한국어 요일"""
    try:
        return _KO_DAYS[datetime.strptime(exp_str, '%Y-%m-%d').weekday()]
    except Exception:
        return ''


def is_monthly(exp_str: str) -> bool:
    """3번째 금요일(월물)이면 True"""
    try:
        d = datetime.strptime(exp_str, '%Y-%m-%d')
        if d.weekday() != 4:
            return False
        return 15 <= d.day <= 21
    except Exception:
        return False


def days_badge(days: int) -> str:
    """만기일까지 남은 일수 → 색상 배지 HTML"""
    if days <= 0:
        return f'<span class="badge b-red">만기</span>'
    if days <= 7:
        return f'<span class="badge b-red">{days}일</span>'
    if days <= 30:
        return f'<span class="badge b-orange">{days}일</span>'
    if days <= 90:
        return f'<span class="badge b-gray">{days}일</span>'
    return f'<span class="badge b-light">{days}일</span>'


__all__ = [
    'EXTREME', 'alert_line',
    'ASSETS', 'CBOE_URL', 'HEADERS',
    'parse_opt_sym',
    'pc_signal', 'pc_color',
    'weekday_ko', 'is_monthly', 'days_badge',
]
