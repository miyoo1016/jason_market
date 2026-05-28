#!/usr/bin/env python3
"""실시간 시세 조회 - Jason Market"""

import subprocess, json
import yfinance as yf
from datetime import datetime
from jm_lib.colors import ALERT, AMBER, CYAN, RESET, GREEN, RED, WARN


EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

ASSETS = [
    ('QQQM (나스닥100)', 'QQQM'),
    ('SPY (S&P500)',     'SPY'),
    ('Google (알파벳)',  'GOOGL'),
    ('삼성전자',         '005930.KS'),
    ('KOSPI (코스피)',   '^KS11'),
    ('KODEX 나스닥100', '379810.KS'),
    ('KODEX S&P500',    '379800.KS'),
    ('KODEX 미국반도체', '390390.KS'),
    ('Bitcoin (BTC)',    'BTC-USD'),
    ('달러/원 (USD/KRW)', 'USDKRW=X'),
    ('금 (Gold)',        'GC=F'),
    ('미국 10년물 국채',  '^TNX'),
    ('브렌트유 (Brent)', 'BZ=F'),
    ('WTI원유 (Crude)',  'CL=F'),
    ('US30 (다우존스)',  'YM=F'),
    ('US500 (S&P500)',   'ES=F'),
    ('USTECH (나스닥)',  'NQ=F'),
    ('US2000 (러셀)',    'RTY=F'),
    ('VIX (공포지수)',   '^VIX'),
]

def _assets_with_holdings():
    """기본 관심종목에 Google Sheet 최신 보유종목을 추가한다."""
    assets = list(ASSETS)
    seen = {ticker for _, ticker in assets}
    try:
        from xlsx_sync import load_portfolio
        for h in load_portfolio():
            ticker = h.get('ticker')
            if not ticker or ticker == 'CASH' or ticker in seen:
                continue
            name = h.get('name') or ticker
            assets.append((name, ticker))
            seen.add(ticker)
    except Exception:
        pass
    return assets

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

def get_data(ticker, name=""):
    if ticker == 'GOLD_KRX':
        return get_gold_krx()
    try:
        # ── 자산 분류 (이 모듈 고유 기준) ──────────────────────────
        # 글로벌 자산: 24H 거래 (00:00 UTC 시가 기준 등락률 계산)
        is_global = ticker in ('GC=F', 'CL=F', 'BZ=F', 'YM=F', 'ES=F', 'NQ=F', 'RTY=F',
                                'USDKRW=X', 'BTC-USD', '^VIX', '^TNX')
        # 주식/ETF: 프리·애프터마켓 포함하여 현재가 조회
        is_equity = ticker in ('GOOGL',) or ticker.endswith('.KS') or (
            ticker in ('QQQM', 'SPY') and not name.startswith('US'))

        # ── 가격 데이터 통합 조회 (jm_lib.yf_helpers) ──────────────
        from jm_lib.yf_helpers import get_price_data
        data = get_price_data(ticker, is_equity=is_equity, is_global=is_global)
        if not data:
            return None

        return data['curr'], data['pct']
    except Exception:
        return None

def fmt_price(price, ticker):
    if ticker == 'BTC-USD':
        return f"${price:>12,.0f}"
    elif ticker in ('GC=F', 'BZ=F', 'CL=F'):
        return f"{price:>12,.1f}"
    elif ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
        # CME 선물 — 인베스팅닷컴과 동일 포맷
        return f"{price:>12,.1f}"
    elif ticker == 'USDKRW=X':
        return f"₩{price:>12,.1f}"
    elif ticker in ('^TNX', '^VIX', '^KS11'):
        return f"{price:>12,.2f}"
    elif ticker.endswith('.KS') or ticker == 'GOLD_KRX':
        return f"₩{price:>12,.0f}"
    else:
        return f"${price:>12,.2f}"

def main():
    print(f"\n{'━'*60}")
    print(f"  Jason 실시간 시세   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*60}")
    print(f"  {'자산':<16}  {'현재가':>13}  {'등락률':>8}  {'방향'}")
    print(f"  {'─'*54}")

    for name, ticker in _assets_with_holdings():
        result = get_data(ticker, name)
        if result:
            price, pct = result
            arrow = '▲' if pct >= 0 else '▼'
            print(f"  {name}  {fmt_price(price, ticker)}  {pct:>+7.2f}%  {arrow}")
        else:
            print(f"  {name}  {'데이터 없음':>13}")

    print(f"  {'─'*54}")
    print(f"  ※ 주식·ETF: 전일 종가 대비 | 선물·FX·크립토·지수: 00:00 GMT 시가 대비\n")

if __name__ == '__main__':
    main()
