#!/usr/bin/env python3
"""가격 알리미 - Jason Market
목표 가격에 도달하면 터미널에서 즉시 알림을 줍니다.
price_alerts.json에 알림 목록을 저장합니다."""

import json
import os
import time
import sys
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

ALERTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'price_alerts.json')

PRESET_ASSETS = {
    '1':  ('Bitcoin',      'BTC-USD'),
    '2':  ('Gold',         'GC=F'),
    '3':  ('Brent유',      'BZ=F'),
    '4':  ('WTI원유',      'CL=F'),
    '5':  ('다우선물',     'YM=F'),
    '6':  ('S&P선물',      'ES=F'),
    '7':  ('나스닥선물',   'NQ=F'),
    '8':  ('러셀2000',     'RTY=F'),
    '9':  ('VIX',          '^VIX'),
    '10': ('미국10년물',   '^TNX'),
    '11': ('달러/원',      'USDKRW=X'),
    '12': ('Google',       'GOOGL'),
    '13': ('Nasdaq QQQM',  'QQQM'),
    '14': ('S&P500 SPY',   'SPY'),
    '15': ('Samsung',      '005930.KS'),
    '16': ('코스피',    '^KS11'),
    '17': ('직접 입력',    ''),
}

# ── 파일 I/O ──────────────────────────────────────────────

def load_alerts():
    try:
        with open(ALERTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_alerts(alerts):
    with open(ALERTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

# ── 현재가 조회 ───────────────────────────────────────────

def get_price(ticker):
    try:
        hist = yf.Ticker(ticker).history(period='1d')
        if hist.empty:
            return None
        return float(hist['Close'].iloc[-1])
    except Exception:
        return None

# ── 알림 발동 ─────────────────────────────────────────────

def trigger_alert(alert, curr_price):
    direction = "도달" if alert['condition'] == 'above' else "하락"
    msg = (
        f"\n{'='*55}\n"
        f"  가격 알림 발동!\n"
        f"  {'='*51}\n"
        f"  자산   : {alert['name']} ({alert['ticker']})\n"
        f"  목표가 : {alert['target_price']:,.2f}\n"
        f"  현재가 : {curr_price:,.2f}\n"
        f"  조건   : {alert['target_price']:,.2f} {direction}\n"
        f"  시각   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"  메모   : {alert.get('memo', '')}\n"
        f"{'='*55}\n"
    )
    # 터미널 벨 소리
    print('\a', end='', flush=True)
    print(msg)

# ── 메뉴: 알림 추가 ──────────────────────────────────────

def add_alert():
    print(f"\n  [ 알림 추가 ]")
    print(f"  {'─'*40}")
    print("  자산 선택:")
    for k, (name, ticker) in PRESET_ASSETS.items():
        if ticker:
            print(f"    {k}. {name} ({ticker})")
        else:
            print(f"    {k}. {name}")

    choice = input("  선택: ").strip()
    if choice in PRESET_ASSETS and PRESET_ASSETS[choice][1]:
        name, ticker = PRESET_ASSETS[choice]
    elif choice == '17':
        name   = input("  자산명: ").strip()
        ticker = input("  티커 (예: AAPL): ").strip().upper()
    else:
        print(f"  취소")
        return

    # 현재가 표시
    curr = get_price(ticker)
    if curr:
        print(f"  현재가: {curr:,.2f}")

    try:
        target = float(input("  목표 가격: ").strip().replace(',', ''))
    except ValueError:
        print(f"  ⚠ 숫자를 입력하세요")
        return

    if curr and target > curr:
        condition = 'above'
        cond_str  = f"{target:,.2f} 이상 도달 시"
    else:
        condition = 'below'
        cond_str  = f"{target:,.2f} 이하 하락 시"

    memo = input("  메모 (선택사항, Enter 건너뜀): ").strip()

    alert = {
        'id':           int(datetime.now().timestamp()),
        'name':         name,
        'ticker':       ticker,
        'target_price': target,
        'condition':    condition,
        'memo':         memo,
        'created':      datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'triggered':    False,
    }

    alerts = load_alerts()
    alerts.append(alert)
    save_alerts(alerts)
    print(f"\n  알림 추가됨: {name} → {cond_str}")

# ── 메뉴: 알림 목록 ──────────────────────────────────────

def list_alerts():
    alerts = load_alerts()
    active = [a for a in alerts if not a.get('triggered')]

    print(f"\n  [ 현재 알림 목록 ({len(active)}개) ]")
    print(f"  {'─'*56}")

    if not active:
        print(f"  등록된 알림 없음")
        return

    print(f"  {'번호':>4}  {'자산':<14} {'목표가':>12} {'조건':<10} {'메모'}")
    print(f"  {'─'*56}")
    for i, a in enumerate(active, 1):
        cond = '↑ 이상' if a['condition'] == 'above' else '↓ 이하'
        memo = a.get('memo', '')[:15]
        print(f"  {i:>4}  {a['name']:<14} {a['target_price']:>12,.2f} {cond:<10} {memo}")

# ── 메뉴: 알림 삭제 ──────────────────────────────────────

def delete_alert():
    alerts  = load_alerts()
    active  = [a for a in alerts if not a.get('triggered')]

    if not active:
        print(f"  삭제할 알림 없음")
        return

    list_alerts()
    try:
        idx = int(input("\n  삭제할 번호: ").strip()) - 1
        if 0 <= idx < len(active):
            target_id = active[idx]['id']
            alerts = [a for a in alerts if a.get('id') != target_id]
            save_alerts(alerts)
            print(f"  삭제됨")
        else:
            print(f"  ⚠ 잘못된 번호")
    except ValueError:
        print(f"  ⚠ 숫자를 입력하세요")

# ── 실시간 모니터링 ──────────────────────────────────────

def monitor(interval=60):
    print(f"\n  가격 모니터링 시작")
    print(f"  Ctrl+C 로 중지\n")

    try:
        while True:
            alerts  = load_alerts()
            active  = [a for a in alerts if not a.get('triggered')]

            if not active:
                print(f"  등록된 알림 없음. 먼저 알림을 추가하세요.")
                return

            now = datetime.now().strftime('%H:%M:%S')
            print(f"  [{now}] 가격 확인 중... ({len(active)}개 알림)", end='\r')

            triggered_ids = []
            for alert in active:
                curr = get_price(alert['ticker'])
                if curr is None:
                    continue

                hit = (
                    (alert['condition'] == 'above' and curr >= alert['target_price']) or
                    (alert['condition'] == 'below' and curr <= alert['target_price'])
                )
                if hit:
                    trigger_alert(alert, curr)
                    triggered_ids.append(alert['id'])

            # 발동된 알림 처리
            if triggered_ids:
                for a in alerts:
                    if a.get('id') in triggered_ids:
                        a['triggered'] = True
                        a['triggered_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                save_alerts(alerts)

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\n  모니터링 중지")

# ── 메인 메뉴 ────────────────────────────────────────────

def main():
    print(f"\n{'━'*55}")
    print(f"  Jason 가격 알리미")
    print(f"{'━'*55}")

    while True:
        print(f"\n  1. 알림 추가")
        print(f"  2. 알림 목록 보기")
        print(f"  3. 알림 삭제")
        print(f"  4. 모니터링 시작 (실시간 감시)")
        print(f"  0. 종료")

        choice = input("\n  선택: ").strip()

        if choice == '1':
            add_alert()
        elif choice == '2':
            list_alerts()
        elif choice == '3':
            delete_alert()
        elif choice == '4':
            list_alerts()
            try:
                sec = int(input(f"\n  확인 주기(초, 기본 60): ").strip() or '60')
            except ValueError:
                sec = 60
            monitor(sec)
        elif choice == '0':
            print(f"  종료")
            break
        else:
            print(f"  ⚠ 잘못된 입력")

if __name__ == '__main__':
    # 인수로 --monitor 전달 시 바로 모니터링 시작
    if len(sys.argv) > 1 and sys.argv[1] == '--monitor':
        list_alerts()
        monitor(60)
    else:
        main()
