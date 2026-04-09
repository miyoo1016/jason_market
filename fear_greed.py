#!/usr/bin/env python3
"""공포탐욕지수 대시보드 - Jason Market
CNN Fear & Greed Index 실제 수치 사용
출처: https://edition.cnn.com/markets/fear-and-greed"""

import subprocess, json, yfinance as yf
from datetime import datetime

ALERT = '\033[38;5;203m'
GREEN = '\033[38;5;82m'
RESET = '\033[0m'
EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

# ── CNN Fear & Greed API ────────────────────────────────────
CNN_API = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_URL = "https://edition.cnn.com/markets/fear-and-greed"

def fetch_cnn_fng():
    """CNN 공식 공포탐욕지수 조회"""
    try:
        r = subprocess.run(
            ['curl', '-s', '-A',
             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
             '-H', f'Referer: {CNN_URL}',
             CNN_API],
            capture_output=True, timeout=15
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        fg = d['fear_and_greed']
        return {
            'score':          round(fg['score'], 1),
            'rating':         fg['rating'],
            'prev_close':     round(fg['previous_close'], 1),
            'prev_1week':     round(fg['previous_1_week'], 1),
            'prev_1month':    round(fg['previous_1_month'], 1),
            'prev_1year':     round(fg['previous_1_year'], 1),
            'timestamp':      fg['timestamp'],
        }
    except Exception as e:
        return None

def get_hist(ticker, period='5d'):
    try:
        h = yf.Ticker(ticker).history(period=period)
        return h if not h.empty else None
    except Exception:
        return None

def label_ko(rating):
    """CNN rating → 한국어"""
    mapping = {
        'extreme fear': '극도의 공포',
        'fear':         '공포',
        'neutral':      '중립',
        'greed':        '탐욕',
        'extreme greed':'극도의 탐욕',
    }
    return mapping.get(rating.lower(), rating)

def label_score(score):
    if score >= 75: return '극도의 탐욕'
    if score >= 55: return '탐욕'
    if score >= 45: return '중립'
    if score >= 25: return '공포'
    return '극도의 공포'

def draw_gauge(score):
    bar_len = 40
    filled  = int(score / 100 * bar_len)
    bar = '█' * filled + '░' * (bar_len - filled)
    return f"[{bar}] {score:.1f}/100"

def score_arrow(now, prev):
    if prev is None:
        return ''
    diff = now - prev
    if diff > 2:   return f'  ▲ +{diff:.1f}'
    if diff < -2:  return f'  ▼ {diff:.1f}'
    return f'  → {diff:+.1f}'

def main():
    print(f"\n{'━'*62}")
    print(f"  CNN 공포탐욕지수   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  출처: {CNN_URL}")
    print(f"{'━'*62}")
    print("  데이터 수집 중...")

    fng = fetch_cnn_fng()

    if fng is None:
        print(f"\n  ⚠ CNN API 조회 실패 — 직접 확인: {CNN_URL}\n")
        return

    score  = fng['score']
    rating = label_ko(fng['rating'])

    # ── 메인 지수 ─────────────────────────────────────────────
    print(f"\n  [ CNN Fear & Greed Index ]")
    print(f"  {draw_gauge(score)}")

    if score <= 25:
        print(f"  판정: {ALERT}{rating}{RESET}")
    elif score >= 75:
        print(f"  판정: {ALERT}{rating}{RESET}")
    else:
        print(f"  판정: {rating}")

    # ── 기간별 비교 ───────────────────────────────────────────
    print(f"\n  [ 기간별 비교 ]")
    print(f"  {'─'*45}")
    periods = [
        ('현재         ', score,              None),
        ('전일 종가    ', fng['prev_close'],  score),
        ('1주일 전     ', fng['prev_1week'],  score),
        ('1개월 전     ', fng['prev_1month'], score),
        ('1년 전       ', fng['prev_1year'],  score),
    ]
    for pname, val, base in periods:
        bar_len = 20
        filled  = int(val / 100 * bar_len)
        mini    = f"{'█'*filled}{'░'*(bar_len-filled)}"
        lbl     = label_score(val)
        arrow   = score_arrow(score, val) if base is not None else ''
        print(f"  {pname} {mini} {val:>5.1f}  {lbl}{arrow}")

    # ── 투자 가이드 ───────────────────────────────────────────
    print(f"\n  [ 투자 가이드 ]")
    print(f"  {'─'*45}")
    if score >= 75:
        print(alert_line(f"  ⚠ 극도의 탐욕 → 차익실현 고려, 추격 매수 자제"))
    elif score >= 55:
        print(f"  탐욕 → 포지션 유지, 과열 여부 모니터링")
    elif score >= 45:
        print(f"  중립 → 시장 방향 확인 후 대응")
    elif score >= 25:
        print(f"  공포 → 분할 매수 기회 검토")
    else:
        print(alert_line(f"  ⭐ 극도의 공포 → 적극 매수 기회 (워런 버핏 구간)"))

    # ── 글로벌 선물 시세 ──────────────────────────────────────
    print(f"\n  [ 글로벌 선물 시세 ]")
    print(f"  {'─'*45}")
    futures = [
        ('다우지수(CME)', 'YM=F'),
        ('S&P500(CME)',  'ES=F'),
        ('나스닥100(CME)', 'NQ=F'),
        ('러셀2000(CME)', 'RTY=F'),
        ('WTI원유(NYMEX)', 'CL=F'),
        ('달러/원      ', 'USDKRW=X'),
        ('코스피       ', '^KS11'),
    ]
    for fname, fticker in futures:
        fhist = get_hist(fticker, '5d')
        if fhist is not None and len(fhist) >= 2:
            fcurr = float(fhist['Close'].iloc[-1])
            fprev = float(fhist['Close'].iloc[-2])
            fpct  = (fcurr - fprev) / fprev * 100
            arrow = '▲' if fpct >= 0 else '▼'
            if fticker == 'USDKRW=X':
                val_str = f"₩{fcurr:,.1f}"
            elif fticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
                val_str = f"{fcurr:,.1f}"
            elif fticker == '^KS11':
                val_str = f"{fcurr:,.2f}"
            else:
                val_str = f"${fcurr:,.2f}"
            print(f"  {fname}  {val_str:>12}  {fpct:>+6.2f}%  {arrow}")

    print(f"\n  ※ CNN Fear & Greed Index — {CNN_URL}\n")

if __name__ == '__main__':
    main()
