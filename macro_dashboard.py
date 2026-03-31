#!/usr/bin/env python3
"""거시경제 지표 대시보드 - Jason Market
금리, 달러, 환율, 유가 등 큰 그림을 보여줍니다."""

import yfinance as yf
from datetime import datetime

ALERT = '\033[38;5;203m'  # 연한 빨간색 (극단 경고에만)
RESET = '\033[0m'

EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

# (표시명, 티커, 단위, 설명)
MACRO_ITEMS = [
    # ── 금리 ──────────────────────────────
    ('미국 10년 금리', '^TNX',      '%',   '높을수록 성장주↓, 달러↑'),
    ('미국 2년 금리',  '^IRX',      '%',   '연준 기준금리 방향 선행'),
    # ── 달러/환율 ──────────────────────────
    ('달러인덱스 DXY', 'DX-Y.NYB',  'pt',  '높을수록 신흥국↓, 금↓, 원자재↓'),
    ('달러/원 환율',   'USDKRW=X',  '원',  '높을수록 수입물가↑'),
    # ── 변동성 ────────────────────────────
    ('공포지수 VIX',   '^VIX',      'pt',  '25↑주의, 30↑공포'),
    # ── 원자재 ────────────────────────────
    ('금 선물',        'GC=F',      'USD', '안전자산, 달러와 역상관'),
    ('브렌트유',       'BZ=F',      'USD', '글로벌 원유 기준가'),
    ('WTI 원유',       'CL=F',      'USD', '미국 원유 기준가, 인플레 지표'),
    ('구리 선물',      'HG=F',      'USD', '경기 선행 지표 (닥터 쿠퍼)'),
    # ── 미국 선물 지수 (24H) ──────────────
    ('다우선물 YM',    'YM=F',      'pt',  '미국 우량주 30종 선물'),
    ('S&P선물 ES',     'ES=F',      'pt',  'S&P500 선물 (24H 거래)'),
    ('나스닥선물 NQ',  'NQ=F',      'pt',  '기술주 나스닥100 선물'),
    ('러셀2000 RTY',   'RTY=F',     'pt',  '미국 중소형주 선물'),
    # ── 기타 지수 ─────────────────────────
    ('S&P500',         '^GSPC',     'pt',  '미국 대형주 벤치마크'),
    ('나스닥100',      '^NDX',      'pt',  '기술주 중심'),
    # ── 암호화폐 ──────────────────────────
    ('비트코인',       'BTC-USD',   'USD', '대표 암호화폐, 위험선호 지표'),
    ('코스피',       '^KS11',  'pt',  '한국 대표 지수 (선물 기초)'),
]

# 별도 표시용 (1년 변화)
YEARLY_COMPARE = ['GC=F', 'CL=F', '^GSPC', '^NDX', 'USDKRW=X']

def get_data(ticker):
    try:
        hist = yf.Ticker(ticker).history(period='5d')
        if hist.empty or len(hist) < 2:
            return None, None, None
        curr   = float(hist['Close'].iloc[-1])
        prev   = float(hist['Close'].iloc[-2])
        pct    = (curr - prev) / prev * 100
        return curr, prev, pct
    except Exception:
        return None, None, None

def get_yearly_change(ticker):
    try:
        hist = yf.Ticker(ticker).history(period='1y')
        if hist.empty or len(hist) < 5:
            return None
        start = float(hist['Close'].iloc[0])
        end   = float(hist['Close'].iloc[-1])
        return (end - start) / start * 100
    except Exception:
        return None

def fmt_val(val, unit):
    if val is None:
        return 'N/A'
    if unit == '%':
        return f"{val:.2f}%"
    if unit == '원':
        return f"₩{val:,.1f}"
    if val >= 1000:
        return f"{val:,.1f}"
    return f"{val:.3f}"

def fmt_pct(pct):
    if pct is None:
        return '     N/A'
    return f"{pct:>+7.2f}%"

def interpret(ticker, curr, pct):
    """간단한 신호 해석"""
    if ticker == '^VIX':
        if curr > 30:   return "극도 공포"
        if curr > 25:   return "공포"
        if curr > 20:   return "주의"
        return "안정"
    if ticker == '^TNX':
        if curr > 4.5:  return "고금리 주의"
        if curr > 4.0:  return "금리 부담"
        return "안정"
    if ticker == 'DX-Y.NYB':
        if curr > 105:  return "달러 강세"
        if curr > 100:  return "달러 보통"
        return "달러 약세"
    if ticker == 'USDKRW=X':
        if curr > 1400: return "원화 약세"
        if curr > 1300: return "주의"
        return "원화 강세"
    if ticker == 'HG=F':
        if pct and pct > 1:   return "경기 기대↑"
        if pct and pct < -1:  return "경기 우려↑"
        return "중립"
    if ticker == 'BTC-USD':
        if pct and pct > 3:   return "강한 상승"
        if pct and pct < -3:  return "강한 하락"
        return "보합"
    if ticker in ('BZ=F', 'CL=F'):
        if curr > 90:  return "고유가 경고"
        if curr > 75:  return "보통"
        return "저유가"
    if ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
        if pct and pct > 1:   return "선물 강세"
        if pct and pct < -1:  return "선물 약세"
        return "보합"
    if ticker == '^KS11':
        if pct and pct > 1:   return "코스피 강세"
        if pct and pct < -1:  return "코스피 약세"
        return "보합"
    return ''

def main():
    print(f"\n{'━'*66}")
    print(f"  Jason 거시경제 대시보드   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*66}")
    print("  데이터 수집 중 (약 15-20초)...\n")

    # ── 카테고리별 출력 ────────────────────────────────────

    categories = [
        ('금리',          ['^TNX', '^IRX']),
        ('달러/환율',     ['DX-Y.NYB', 'USDKRW=X']),
        ('변동성',        ['^VIX']),
        ('원자재',        ['GC=F', 'BZ=F', 'CL=F', 'HG=F']),
        ('미국 선물 (24H)', ['YM=F', 'ES=F', 'NQ=F', 'RTY=F']),
        ('주요 지수',     ['^GSPC', '^NDX', '^KS11']),
        ('암호화폐',      ['BTC-USD']),
    ]

    ticker_map = {item[1]: item for item in MACRO_ITEMS}

    for cat_name, tickers in categories:
        print(f"  {cat_name}")
        print(f"  {'─'*62}")
        print(f"  {'지표':<18} {'현재값':>10} {'일간':>9}  {'해석':<14} {'설명'}")
        print(f"  {'─'*62}")

        for ticker in tickers:
            item = ticker_map.get(ticker)
            if not item:
                continue
            name, _, unit, desc = item
            curr, prev, pct = get_data(ticker)
            if curr is None:
                print(f"  {name:<18} {'N/A':>10}")
                continue

            val_str  = fmt_val(curr, unit)
            pct_str  = fmt_pct(pct)
            intp     = interpret(ticker, curr, pct)

            print(f"  {name:<18} {val_str:>10} {pct_str}  {alert_line(intp):<14} {desc}")

        print()

    # ── 1년 변화 요약 ────────────────────────────────────
    print(f"  1년 수익률 비교")
    print(f"  {'─'*40}")
    yearly_tickers = {
        '금(GC=F)':     'GC=F',
        '브렌트유':     'BZ=F',
        'WTI유가':      'CL=F',
        'S&P선물(ES)':  'ES=F',
        '나스닥선물(NQ)':'NQ=F',
        'S&P500':       '^GSPC',
        '나스닥100':    '^NDX',
        '달러/원':      'USDKRW=X',
        '비트코인':     'BTC-USD',
        '코스피':    '^KS11',
    }
    for name, ticker in yearly_tickers.items():
        y = get_yearly_change(ticker)
        if y is not None:
            print(f"  {name:<12} {y:>+7.1f}%")

    print(f"\n  ※ 야후 파이낸스 기준 (15분 지연)\n")

if __name__ == '__main__':
    main()
