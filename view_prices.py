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
        t  = yf.Ticker(ticker)
        fi = t.fast_info
        
        # ── 기초 데이터 추출 ──────────────────────────
        prev = getattr(fi, 'previous_close', None)
        open_val = getattr(fi, 'open', None)
        
        # 2. 글로벌 자산 00:00 UTC 시가 찾기
        is_global = ticker in ('GC=F', 'CL=F', 'BZ=F', 'YM=F', 'ES=F', 'NQ=F', 'RTY=F',
                                'USDKRW=X', 'BTC-USD', '^VIX', '^TNX')
        if is_global:
            try:
                from datetime import timezone
                h_int = t.history(period='2d', interval='1h')
                if not h_int.empty:
                    h_int.index = h_int.index.tz_convert('UTC')
                    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    today_data = h_int.loc[h_int.index >= today_utc]
                    if not today_data.empty:
                        open_val = float(today_data['Open'].iloc[0])
            except: pass

        # fallback
        if not prev:
            hist = t.history(period='5d')
            if len(hist) >= 2: prev = float(hist['Close'].iloc[-2])

        # ── 현재가 추출 (프리/애프터마켓 포함) ─────────────────────
        is_equity = ticker in ('GOOGL',) or ticker.endswith('.KS') or (
            ticker in ('QQQM', 'SPY') and not name.startswith('US'))
        curr = None
        if is_equity:
            try:
                h1m = t.history(period='1d', interval='1m', prepost=True)
                if not h1m.empty: curr = float(h1m['Close'].iloc[-1])
            except: pass
        
        if not curr:
            curr = getattr(fi, 'last_price', None)

        if not curr or not prev: return None

        if open_val:
            pct = (curr - open_val) / open_val * 100
        else:
            pct = (curr - prev) / prev * 100
            
        return curr, pct
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

    for name, ticker in ASSETS:
        result = get_data(ticker, name)
        if result:
            price, pct = result
            arrow = '▲' if pct >= 0 else '▼'
            print(f"  {name}  {fmt_price(price, ticker)}  {pct:>+7.2f}%  {arrow}")
        else:
            print(f"  {name}  {'데이터 없음':>13}")

    print(f"  {'─'*54}")
    print(f"  ※ 지수: Investing.com (현물기반) | 글로벌: 00:00 GMT 시가 대비 등락률\n")

if __name__ == '__main__':
    main()
