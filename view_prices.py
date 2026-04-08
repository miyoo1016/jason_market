#!/usr/bin/env python3
"""실시간 시세 조회 - Jason Market"""

import subprocess, json
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

ASSETS = [
    # ── 미국 ETF / 개별 종목 ────────
    ('Nasdaq QQQM ', 'QQQM'),
    ('S&P500 SPY  ', 'SPY'),
    ('Google      ', 'GOOGL'),
    # ── 포트폴리오 국내 ETF ──────────
    ('KODEX NQ100 ', '379810.KS'),
    ('KODEX S&P500', '379800.KS'),
    ('KODEX 반도체 ', '390390.KS'),
    ('TIGER CD금리 ', '357870.KS'),
    ('KRX 금현물   ', 'GOLD_KRX'),
    # ── 한국 ────────────────────────
    ('코스피       ', '^KS11'),
    ('삼성전자     ', '005930.KS'),
    # ── 암호화폐 ────────────────────
    ('Bitcoin     ', 'BTC-USD'),
    # ── 환율/금리 ───────────────────
    ('달러/원      ', 'USDKRW=X'),
    ('금           ', 'GC=F'),
    ('미국10년물   ', '^TNX'),
    # ── 원자재 ──────────────────────
    ('브렌트유     ', 'BZ=F'),
    ('WTI원유     ', 'CL=F'),
    # ── 선물 지수 (24H) ─────────────
    ('다우선물     ', 'YM=F'),
    ('S&P선물     ', 'ES=F'),
    ('나스닥선물   ', 'NQ=F'),
    ('러셀2000    ', 'RTY=F'),
    # ── 변동성 ──────────────────────
    ('VIX         ', '^VIX'),
]

def get_gold_krx():
    """KRX 금현물 — 네이버 증권 API (M04020000, 한국거래소 공식)"""
    try:
        r = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0',
             'https://api.stock.naver.com/marketindex/metals/M04020000'],
            capture_output=True, timeout=10
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        price_str = d.get('closePrice') or d.get('currentPrice') or ''
        price = float(price_str.replace(',', ''))
        ratio = float(d.get('fluctuationsRatio', 0))
        ftype = d.get('fluctuationsType', '')
        if ftype == 'FALL':
            ratio = -abs(ratio)
        elif ftype == 'RISE':
            ratio = abs(ratio)
        if price > 0:
            return price, ratio
    except Exception:
        pass
    return None

def get_data(ticker):
    if ticker == 'GOLD_KRX':
        return get_gold_krx()
    try:
        t  = yf.Ticker(ticker)
        fi = t.fast_info

        is_kr     = ticker.endswith('.KS') or ticker in ('^KS11',)
        is_equity = (not is_kr
                     and not ticker.endswith('=F')
                     and not ticker.endswith('=X')
                     and not ticker.startswith('^')
                     and ticker not in ('BTC-USD',))

        # ── 현재가 ───────────────────────────────────────────
        if is_kr:
            # 한국 정규장: fast_info
            curr = fi.get('last_price') or fi.get('lastPrice')
        elif is_equity:
            # 미국 주식/ETF: 1분봉 prepost → 프리·애프터마켓 실시간
            try:
                h1m  = t.history(period='1d', interval='1m', prepost=True)
                curr = float(h1m['Close'].iloc[-1]) if not h1m.empty else None
            except Exception:
                curr = None
            if not curr:
                curr = fi.get('last_price') or fi.get('lastPrice')
        else:
            # 선물/FX/지수/크립토: fast_info 24H 실시간
            curr = fi.get('last_price') or fi.get('lastPrice')

        curr = float(curr) if curr else None
        if not curr:
            return None

        # ── 전일 종가 (히스토리 기반 정밀 계산) ──────────────────
        hist = t.history(period='5d')
        if not hist.empty:
            last_close = float(hist['Close'].iloc[-1])
            # 현재가(curr)가 히스토리 마지막 종가와 거의 같으면 (장 마감 상태면)
            # 기준은 그 전날 종가(iloc[-2])로 잡아야 함
            if abs(curr - last_close) / last_close < 0.0001:
                prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else last_close
            else:
                # 현재가가 장중에 변동 중이면, 히스토리 마지막 종가가 실제 '어제 종가'
                prev = last_close
        else:
            prev_fi = fi.get('previous_close') or fi.get('previousClose')
            prev    = float(prev_fi) if prev_fi else None

        if not prev:
            return None

        pct = (curr - prev) / prev * 100
        return curr, pct
    except Exception:
        return None

def fmt_price(price, ticker):
    if ticker == 'BTC-USD':
        return f"${price:>12,.0f}"
    elif ticker in ('GC=F', 'BZ=F', 'CL=F'):
        return f"${price:>12,.1f}"
    elif ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
        return f"{price:>12,.1f}"
    elif ticker == 'USDKRW=X':
        return f"₩{price:>12,.1f}"
    elif ticker in ('^TNX', '^VIX', '^KS11'):
        return f"{price:>12,.2f}"
    elif ticker in ('005930.KS', '379810.KS', '379800.KS', '390390.KS', '357870.KS', 'GOLD_KRX'):
        return f"₩{price:>12,.0f}"
    else:
        return f"${price:>12,.2f}"

def main():
    print(f"\n{'━'*60}")
    print(f"  Jason 실시간 시세   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*60}")
    print(f"  {'자산':<16}  {'현재가':>13}  {'등락률':>8}  {'방향'}")
    print(f"  {'─'*54}")

    for name, ticker in ASSETS:
        result = get_data(ticker)
        if result:
            price, pct = result
            arrow = '▲' if pct >= 0 else '▼'
            print(f"  {name}  {fmt_price(price, ticker)}  {pct:>+7.2f}%  {arrow}")
        else:
            print(f"  {name}  {'데이터 없음':>13}")

    print(f"  {'─'*54}")
    print(f"  ※ 미국 주식/ETF: 1분봉 prepost 실시간 | 선물·FX·지수·크립토: fast_info 24H | 한국: fast_info 정규장\n")

if __name__ == '__main__':
    main()
