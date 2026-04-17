#!/usr/bin/env python3
"""포트폴리오 손익 추적기 - Jason Market
구글드라이브 자산계산기.xlsx → 실시간 손익 계산 + HTML 대시보드"""

import os
import webbrowser
import tempfile
import threading
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from xlsx_sync import load_portfolio, sync_to_json, update_xlsx_live_fx

ALERT  = '\033[38;5;203m'
RESET  = '\033[0m'
EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

# ── 가격 조회 ──────────────────────────────────────────────

_price_cache = {}

def _fetch_gold_krx(usdkrw):
    """KRX 금현물 — 네이버 모바일 증권 API (한국거래소 공식, M04020000)"""
    import subprocess, json, re
    res = {'curr': None, 'prev': None}
    try:
        r = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0',
             'https://api.stock.naver.com/marketindex/metals/M04020000'],
            capture_output=True, timeout=10
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        price_str = d.get('closePrice') or d.get('currentPrice') or ''
        price = float(price_str.replace(',', ''))
        if price > 0:
            res['curr'] = price
            # 네이버 API에서 전일비(compare)를 통해 전일종가 유추
            diff = float(str(d.get('compareToPreviousPrice', '0')).replace(',', ''))
            sign = 1 if d.get('fluctuationCode') in ('1', '2') else -1
            if d.get('fluctuationCode') == '3': sign = 0
            res['prev'] = price - (diff * sign)
            return res
    except Exception:
        pass
    # fallback: GC=F 계산
    try:
        gc = yf.Ticker('GC=F').history(period='5d')
        if len(gc) >= 2:
            res['curr'] = round(float(gc['Close'].iloc[-1]) * usdkrw / 31.1035, 0)
            res['prev'] = round(float(gc['Close'].iloc[-2]) * usdkrw / 31.1035, 0)
            return res
    except Exception:
        pass
    return res

def get_usdkrw():
    """실시간 환율(FastInfo) 및 전일 종가 조회"""
    try:
        tk = yf.Ticker('USDKRW=X')
        # 1. 실시간 가격 (FastInfo)
        curr = tk.fast_info.get('last_price') or tk.fast_info.get('lastPrice')
        
        # 2. 전일 종가 및 백업 데이터 (History)
        h = tk.history(period='3d')
        if not h.empty:
            # 실시간 가격이 없으면 history 마지막 값 사용
            if not curr:
                curr = h['Close'].iloc[-1]
            
            # 전일 종가 결정 (현재가가 오늘 데이터면 그 전날 데이터 사용)
            if len(h) >= 2:
                prev = h['Close'].iloc[-2]
            else:
                prev = h['Close'].iloc[-1]
        else:
            prev = curr or 1450.0
            
        return float(curr or 1450.0), float(prev or 1450.0)
    except Exception:
        return 1450.0, 1450.0

def _reset_yf_cookie():
    """yfinance 쿠키 캐시 초기화 — s키 동기화 후 Invalid Crumb 방지"""
    try:
        from yfinance.cache import get_cookie_cache
        get_cookie_cache().store('curlCffi', None)
    except Exception:
        pass

def fetch_all_prices(holdings, usdkrw):
    """병렬로 모든 종목 현재가+전일종가 조회 (1일 손익용)"""
    _reset_yf_cookie()
    tickers = set()
    for h in holdings:
        t = h.get('ticker', '')
        if t and t not in ('CASH', 'GOLD_KRX', ''):
            tickers.add(t)

    cache = {} # ticker -> {'curr': float, 'prev': float}

    us_tickers = [t for t in tickers if not t.endswith('.KS') and '^KS' not in t]
    kr_tickers = [t for t in tickers if t.endswith('.KS') or '^KS' in t]

    def _update_cache(t, curr, prev=None):
        if curr != curr: return
        if t not in cache: cache[t] = {'curr': curr, 'prev': prev}
        else:
            if curr: cache[t]['curr'] = curr
            if prev: cache[t]['prev'] = prev

    def _fetch_us():
        if not us_tickers: return
        
        # 1. 분봉 데이터 수집 (현재 세션 최우선)
        try:
            # period='1d'는 현재 진행 중인 세션(프리마켓 포함)을 가져옵니다.
            data = yf.download(us_tickers, period='1d', interval='1m',
                               prepost=True, auto_adjust=True, progress=False, threads=True)
            closes = data['Close'] if 'Close' in data else data
            for t in us_tickers:
                try:
                    col = closes[t] if hasattr(closes, 'columns') and t in closes.columns else closes
                    valid = col.dropna()
                    if not valid.empty:
                        _update_cache(t, float(valid.iloc[-1]))
                except Exception: pass
        except Exception: pass

        # 2. 개별 Ticker 속성으로 보강 (프리/애프터마켓 가격 직접 확인)
        def _fetch_single_info(t):
            try:
                tk = yf.Ticker(t)
                info = tk.info
                live_price = (
                    info.get('preMarketPrice') or 
                    info.get('regularMarketPrice') or 
                    info.get('postMarketPrice')
                )
                prev = info.get('regularMarketPreviousClose') or info.get('previousClose')
                
                # 인베스팅닷컴 동기화 보정: 글로벌 자산은 00:00 UTC 기준 % 계산을 위해 prev를 시가로 대체
                is_global = t in ('GC=F', 'CL=F', 'BZ=F', 'USDKRW=X', 'BTC-USD', 'DIA', 'SPY', 'QQQM', 'IWM', '^VIX', '^TNX')
                if is_global:
                    try:
                        from datetime import timezone
                        h_int = tk.history(period='2d', interval='1h')
                        if not h_int.empty:
                            h_int.index = h_int.index.tz_convert('UTC')
                            today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                            today_data = h_int.loc[h_int.index >= today_utc]
                            if not today_data.empty:
                                prev = float(today_data['Open'].iloc[0])
                    except: pass

                if live_price:
                    _update_cache(t, float(live_price), float(prev) if prev else None)
            except Exception: pass

        # 병렬로 상세 정보 조회 (시간이 걸릴 수 있으므로 스레드 활용)
        info_threads = [threading.Thread(target=_fetch_single_info, args=(t,), daemon=True) for t in us_tickers]
        for th in info_threads: th.start()
        for th in info_threads: th.join(timeout=5)

    def _fetch_kr():
        if not kr_tickers: return
        try:
            data = yf.download(kr_tickers, period='5d', auto_adjust=True, progress=False, threads=True)
            closes = data['Close'] if 'Close' in data else data
            for t in kr_tickers:
                try:
                    col = closes[t] if hasattr(closes, 'columns') and t in closes.columns else closes
                    valid = col.dropna()
                    if len(valid) >= 2:
                        _update_cache(t, float(valid.iloc[-1]), float(valid.iloc[-2]))
                    elif not valid.empty:
                        _update_cache(t, float(valid.iloc[-1]))
                except Exception: pass
        except Exception: pass

    # GOLD_KRX 병렬 조회
    gold_result = {'curr': None, 'prev': None}
    def _gold():
        res = _fetch_gold_krx(usdkrw)
        gold_result.update(res)

    t_us = threading.Thread(target=_fetch_us, daemon=True)
    t_kr = threading.Thread(target=_fetch_kr, daemon=True)
    gt   = threading.Thread(target=_gold, daemon=True)
    t_us.start(); t_kr.start(); gt.start()
    t_us.join(timeout=30); t_kr.join(timeout=30); gt.join(timeout=30)

    # 누락건 개별 재조회
    for t in tickers:
        if t not in cache or cache[t].get('prev') is None:
            try:
                tk = yf.Ticker(t)
                fi = tk.fast_info
                curr = getattr(fi, 'last_price', None)
                if not curr and hasattr(fi, 'get'):
                    curr = fi.get('lastPrice') or fi.get('last_price')

                prev = getattr(fi, 'previous_close', None)
                if not prev and hasattr(fi, 'get'):
                    prev = fi.get('previousClose') or fi.get('previous_close')
                    
                if not prev:
                    h = tk.history(period='5d')
                    if len(h) >= 2:
                        prev = float(h['Close'].iloc[-2])
                        if not curr: curr = float(h['Close'].iloc[-1])
                _update_cache(t, float(curr) if curr else None, float(prev) if prev else None)
            except Exception: pass

    cache['GOLD_KRX_PRICE'] = gold_result
    return cache

def get_price(h, price_cache, usdkrw):
    ticker = h.get('ticker', '')
    if ticker == 'CASH':
        return None, None
    
    if ticker == 'GOLD_KRX':
        data = price_cache.get('GOLD_KRX_PRICE', {})
    else:
        data = price_cache.get(ticker, {})

    curr = data.get('curr')
    prev = data.get('prev')

    if curr is None or curr != curr:
        curr = h.get('xlsx_price')
    
    return curr, prev

# ── 포맷 헬퍼 ─────────────────────────────────────────────

def fmt_krw(val):
    return f"₩{val:>15,.0f}"

def fmt_usd(val):
    return f"${val:>12,.0f}" if abs(val) >= 1000 else f"${val:>12,.2f}"

def fmt_pct(val):
    return f"{val:>+7.2f}%"

# ── 현금 추적 (일일·총손익 기준값 저장) ──────────────────────
import json as _json_module

_CASH_TRACKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cash_tracker.json')

def _load_cash_tracker():
    """cash_tracker.json 로드. 없으면 빈 dict 반환."""
    try:
        with open(_CASH_TRACKER_PATH, encoding='utf-8') as f:
            return _json_module.load(f)
    except Exception:
        return {}

def _save_cash_tracker(tracker: dict):
    """cash_tracker.json 저장."""
    try:
        with open(_CASH_TRACKER_PATH, 'w', encoding='utf-8') as f:
            _json_module.dump(tracker, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ── 데이터 계산 ───────────────────────────────────────────

def calc_data(holdings, usdkrw_tuple):
    """모든 계좌 손익 계산 → (accounts_data, updated_cash_tracker) 반환"""
    usdkrw, prev_usdkrw = usdkrw_tuple
    valid = [h for h in holdings if h.get('ticker') and float(h.get('qty', 0)) > 0]
    price_cache = fetch_all_prices(valid, usdkrw)

    tracker      = _load_cash_tracker()          # 기존 저장값
    new_tracker  = {}                             # 이번 실행 후 저장할 값
    today_str    = datetime.now().strftime('%Y-%m-%d')
    cash_idx_map = {}                             # acc → 이 계좌에서 몇 번째 현금 행인지

    accounts = {}
    for h in valid:
        acc = h.get('account', '기타')
        accounts.setdefault(acc, []).append(h)

    accounts_data = {}
    for acc, items in accounts.items():
        rows = []
        acc_cost = acc_curr = acc_daily_profit = 0
        acc_list = tracker.get(acc, [])  # 기존 tracker의 이 계좌 데이터

        for h in items:
            qty = float(h['qty'])
            avg = float(h['avg_price'])
            cur = h.get('currency', 'KRW')

            if h.get('is_cash') or h.get('ticker') == 'CASH':
                cash_krw = avg if cur == 'KRW' else avg * usdkrw

                # ── 이 계좌의 몇 번째 현금 행인지 인덱스 확인 ──────
                idx = cash_idx_map.get(acc, 0)
                cash_idx_map[acc] = idx + 1

                # ── tracker 데이터 로드 ──────────────────────────
                if idx < len(acc_list):
                    entry = acc_list[idx]
                else:
                    # 처음 등장 → 기준값 = 현재 잔액 (손익 0으로 시작)
                    entry = {'cost_basis': cash_krw, 'prev_balance': cash_krw, 'prev_date': today_str}

                cost_basis   = entry.get('cost_basis', cash_krw)
                prev_date    = entry.get('prev_date', today_str)
                prev_balance = entry.get('prev_balance', cash_krw)

                # 전일과 날짜가 같으면 same-day → daily 집계 유지
                if prev_date == today_str:
                    daily_profit_krw = cash_krw - prev_balance  # 오늘 이미 한 번 실행했을 때 누적
                else:
                    daily_profit_krw = cash_krw - prev_balance  # 전일 대비 변동

                profit_krw = cash_krw - cost_basis
                pct        = profit_krw / cost_basis * 100 if cost_basis > 0 else 0

                # new_tracker에 기록 (cost_basis 는 보존, prev_balance 만 갱신)
                new_entry = {
                    'cost_basis':   cost_basis,       # 절대 덮어쓰지 않음
                    'prev_balance': cash_krw,          # 이번 실행 기준으로 갱신
                    'prev_date':    today_str,
                }
                if acc not in new_tracker:
                    new_tracker[acc] = []
                new_tracker[acc].append(new_entry)

                acc_cost         += cost_basis
                acc_curr         += cash_krw
                acc_daily_profit += daily_profit_krw

                rows.append({
                    'name': h['name'], 'qty': '현금', 'is_cash': True,
                    'avg': f'₩{cost_basis:,.0f}', 'price': f'₩{cash_krw:,.0f}', 'cur': cur,
                    'val_krw': cash_krw, 'profit_krw': profit_krw,
                    'daily_profit_krw': daily_profit_krw, 'pct': pct,
                    'fx_pnl': 0, 'price_pnl': profit_krw, 'base_fx': 0,
                    'is_precision': False,
                })
                continue

            price, prev_close = get_price(h, price_cache, usdkrw)
            if price is None: continue

            base_fx = h.get('base_usdkrw', usdkrw)
            is_usd = (cur == 'USD')

            p_cost = h.get('precision_cost_krw')
            is_usd = (cur == 'USD')

            if is_usd:
                # ── 구글시트 기준 손익 계산 ──────────────────────────────
                # 손익(₩) = qty × (현재가 - 평단가) × 현재환율
                # cost_krw = qty × 평단가 × 현재환율  (매입환율 미사용, 시트와 동일)
                cost_krw    = qty * avg * usdkrw
                current_krw = qty * price * usdkrw
                # 1일 손익: (오늘가 - 어제가) × 현재환율 × 수량 (주가 변동분)
                if prev_close:
                    daily_profit_krw = (price - prev_close) * usdkrw * qty
                else:
                    daily_profit_krw = 0
                avg_s  = f"${avg:,.2f}"; pri_s  = f"${price:,.2f}"

                # 환차 정보 (보조 표시용 — 시트 외 추가 정보)
                purchase_fx = p_cost if (p_cost is not None and p_cost < 10000) else base_fx
                fx_pnl   = (usdkrw - purchase_fx) * avg * qty
                price_pnl = qty * (price - avg) * usdkrw  # = profit_krw
            else:
                cost_krw    = p_cost if p_cost is not None else (qty * avg)
                current_krw = qty * price
                daily_profit_krw = (price - prev_close) * qty if prev_close else 0
                avg_s  = f"₩{avg:,.0f}"; pri_s  = f"₩{price:,.0f}"
                fx_pnl = 0
                price_pnl = current_krw - cost_krw

            profit_krw = current_krw - cost_krw
            pct = profit_krw / cost_krw * 100 if cost_krw > 0 else 0
            acc_cost += cost_krw
            acc_curr += current_krw
            acc_daily_profit += daily_profit_krw

            rows.append({
                'name': h['name'], 'qty': f"{qty:,.0f}", 'is_cash': False,
                'avg': avg_s, 'price': pri_s, 'cur': cur,
                'val_krw': current_krw, 'profit_krw': profit_krw, 
                'daily_profit_krw': daily_profit_krw, 'pct': pct,
                'fx_pnl': fx_pnl, 'price_pnl': price_pnl, 'base_fx': base_fx,
                'is_precision': (p_cost is not None)
            })

        acc_profit = acc_curr - acc_cost
        acc_pct    = acc_profit / acc_cost * 100 if acc_cost > 0 else 0
        accounts_data[acc] = {
            'rows': rows, 'cost': acc_cost, 'curr': acc_curr,
            'profit': acc_profit, 'daily_profit': acc_daily_profit, 'pct': acc_pct,
        }

    return accounts_data, new_tracker

# ── 터미널 출력 ───────────────────────────────────────────

def print_terminal(accounts_data, usdkrw, timestamp):
    print(f"\n{'━'*105}")
    print(f"  Jason & 와이프 포트폴리오 손익   {timestamp}")
    print(f"  환율: ₩{usdkrw:,.2f}/USD")
    print(f"{'━'*105}")

    grand_cost = grand_curr = grand_daily = 0

    for acc, d in accounts_data.items():
        print(f"  ┌─ {acc} {'─'*75}")
        print(f"  │ {'종목':<16} {'수량':>8} {'평단가':>12} {'현재가':>12} {'평가금액(₩)':>16} {'총손익(₩)':>14} {'1일손익(₩)':>12} {'수익률':>8}")
        print(f"  │ {'─'*105}")

        for r in d['rows']:
            if r['is_cash']:
                line = (f"  │ {r['name']:<16} {'현금':>8} {r['avg']:>12} {r['price']:>12} "
                        f"{fmt_krw(r['val_krw']):>16} "
                        f"{fmt_krw(r['profit_krw']):>14} "
                        f"{fmt_krw(r['daily_profit_krw']):>12} "
                        f"{fmt_pct(r['pct']):>8}")
            else:
                line = (f"  │ {r['name']:<16} {r['qty']:>8} "
                        f"{r['avg']:>12} {r['price']:>12} "
                        f"{fmt_krw(r['val_krw']):>16} "
                        f"{fmt_krw(r['profit_krw']):>14} "
                        f"{fmt_krw(r['daily_profit_krw']):>12} "
                        f"{fmt_pct(r['pct']):>8}")
            print(alert_line(line))

        print(f"  │ {'─'*105}")
        summary = (f"  │ {'[계좌합계]':<16} {'':>8} {'':>12} {'':>12} "
                   f"{fmt_krw(d['curr']):>16} "
                   f"{fmt_krw(d['profit']):>14} "
                   f"{fmt_krw(d['daily_profit']):>12} "
                   f"{fmt_pct(d['pct']):>8}")
        print(alert_line(summary))
        print(f"  └{'─'*106}\n")

        grand_cost += d['cost']
        grand_curr += d['curr']
        grand_daily += d['daily_profit']

    grand_profit = grand_curr - grand_cost
    grand_pct    = grand_profit / grand_cost * 100 if grand_cost > 0 else 0
    grand_usd    = grand_curr / usdkrw
    grand_fx_pnl = sum(sum(r.get('fx_pnl', 0) for r in d['rows']) for d in accounts_data.values())

    print(f"  {'━'*105}")
    print(alert_line(f"    총 평가금액  : {fmt_krw(grand_curr)}  (${grand_usd:,.0f})"))
    print(alert_line(f"    총 손익      : {fmt_krw(grand_profit)}  ({grand_pct:+.2f}%)"))
    print(alert_line(f"    총 1일 손익  : {fmt_krw(grand_daily)} (주가+환율 변동 합산)"))
    print(f"  {'━'*105}")
    print(f"\n  ※ 데이터 출처: 구글드라이브 자산계산기.xlsx\n")

    return grand_cost, grand_curr, grand_profit, grand_pct, grand_usd, grand_daily

# ── HTML 생성 ─────────────────────────────────────────────

def generate_html(accounts_data, usdkrw_tuple, timestamp):
    usdkrw, prev_usdkrw = usdkrw_tuple
    grand_cost = sum(d['cost'] for d in accounts_data.values())
    grand_curr = sum(d['curr'] for d in accounts_data.values())
    grand_daily = sum(d['daily_profit'] for d in accounts_data.values())
    grand_profit = grand_curr - grand_cost
    grand_pct    = grand_profit / grand_cost * 100 if grand_cost > 0 else 0
    grand_usd    = grand_curr / usdkrw

    def pnl_color(val):
        return '#00838f' if val >= 0 else '#c62828' # Teal / Red (CLAUDE.md 규칙 적용)

    def pnl_bg(val):
        return '#f0fff4' if val >= 0 else '#fff0f0'

    def sign(val):
        return '+' if val >= 0 else ''

    account_sections = ''
    for acc, d in accounts_data.items():
        rows_html = ''
        for r in d['rows']:
            if r['is_cash']:
                pc  = pnl_color(r['profit_krw'])
                pdc = pnl_color(r['daily_profit_krw'])
                rows_html += f"""
      <tr class="cash-row">
        <td class="name-cell">{r['name']}<span class="fx-tag" style="background:#e8f5e9;color:#2e7d32;margin-left:4px">예금</span></td>
        <td class="center">현금</td>
        <td class="num" style="color:#888">{r['avg']}</td>
        <td class="num" style="color:#888">{r['price']}</td>
        <td class="num">₩{r['val_krw']:,.0f}</td>
        <td class="num" style="color:{pc}">{sign(r['profit_krw'])}₩{r['profit_krw']:,.0f}</td>
        <td class="num" style="color:{pdc}">{sign(r['daily_profit_krw'])}₩{r['daily_profit_krw']:,.0f}</td>
        <td class="num pct" style="color:{pc}">{sign(r['pct'])}{r['pct']:.2f}%</td>
      </tr>"""
            else:
                pc = pnl_color(r['profit_krw'])
                pdc = pnl_color(r['daily_profit_krw'])
                # USD의 경우 환차 이익 표시 태그 추가
                fx_info = ""
                if r['cur'] == 'USD' and abs(r.get('fx_pnl', 0)) > 100:
                    fxc = pnl_color(r['fx_pnl'])
                    fx_info = f'<br><span class="fx-tag" style="color:{fxc};background:none;padding:0">환차 {sign(r["fx_pnl"])}₩{r["fx_pnl"]:,.0f}</span>'
                
                precision_tag = '<span class="fx-tag" style="background:#e0f2f1;color:#00695c">정밀</span>' if r.get('is_precision') else ""
                
                rows_html += f"""
      <tr>
        <td class="name-cell">{r['name']}{precision_tag}{fx_info}</td>
        <td class="num center">{r['qty']}</td>
        <td class="num">{r['avg']}</td>
        <td class="num">{r['price']}</td>
        <td class="num">₩{r['val_krw']:,.0f}</td>
        <td class="num" style="color:{pc}">{sign(r['profit_krw'])}₩{r['profit_krw']:,.0f}</td>
        <td class="num" style="color:{pdc}">{sign(r['daily_profit_krw'])}₩{r['daily_profit_krw']:,.0f}</td>
        <td class="num pct" style="color:{pc}">{sign(r['pct'])}{r['pct']:.2f}%</td>
      </tr>"""

        acc_col = pnl_color(d['profit'])
        acc_dcol = pnl_color(d['daily_profit'])
        acc_bg  = pnl_bg(d['profit'])
        account_sections += f"""
  <div class="acc-card">
    <div class="acc-header">
      <span class="acc-name">{acc}</span>
      <span class="acc-val">₩{d['curr']:,.0f}</span>
      <span class="acc-pnl" style="color:{acc_col}">총 {sign(d['profit'])}₩{d['profit']:,.0f} ({sign(d['pct'])}{d['pct']:.2f}%)</span>
      <span class="acc-pnl" style="color:{acc_dcol};margin-left:15px">1일 {sign(d['daily_profit'])}₩{d['daily_profit']:,.0f}</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>종목</th><th class="center">수량</th><th>평단가</th><th>현재가</th>
          <th>평가금액</th><th>총손익</th><th>1일손익</th><th>수익률</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr style="background:{acc_bg}">
          <td colspan="4" style="font-weight:700;padding:10px 12px">계좌 합계</td>
          <td class="num" style="font-weight:700">₩{d['curr']:,.0f}</td>
          <td class="num" style="color:{acc_col};font-weight:700">{sign(d['profit'])}₩{d['profit']:,.0f}</td>
          <td class="num" style="color:{acc_dcol};font-weight:700">{sign(d['daily_profit'])}₩{d['daily_profit']:,.0f}</td>
          <td class="num pct" style="color:{acc_col};font-weight:700">{sign(d['pct'])}{d['pct']:.2f}%</td>
        </tr>
      </tfoot>
    </table>
  </div>"""

    gpc = pnl_color(grand_profit)
    gdc = pnl_color(grand_daily)

    # ── 히트맵 데이터 (JS 임베드용) ─────────────────────────
    # 같은 종목이 여러 계좌에 있으면 평가금액·손익 합산, 수익률은 가중평균
    # 현금 포함 (pct=0, profit=0)
    import json as _json
    _hm_merged = {}   # name → dict
    for acc, d in accounts_data.items():
        for r in d['rows']:
            name      = r['name']
            val       = r['val_krw']
            daily_krw = r['daily_profit_krw']
            profit_krw = r['profit_krw']          # 총 증감금액
            pct       = r['pct']
            daily_pct = (daily_krw / val * 100) if val else 0
            is_cash   = r['is_cash']

            if name in _hm_merged:
                ex = _hm_merged[name]
                old_val   = ex['val']
                total_val = old_val + val
                ex['pct']        = (ex['pct'] * old_val + pct * val) / total_val if total_val else 0
                ex['daily_krw']  += daily_krw
                ex['profit_krw'] += profit_krw
                ex['daily_pct']  = ex['daily_krw'] / total_val * 100 if total_val else 0
                ex['val']        = total_val
                if acc not in ex['acc']:
                    ex['acc'] += ' + ' + acc
            else:
                _hm_merged[name] = {
                    'name':       name,
                    'pct':        pct,
                    'daily_pct':  daily_pct,
                    'val':        val,
                    'daily_krw':  daily_krw,
                    'profit_krw': profit_krw,
                    'price':      r.get('price', ''),
                    'acc':        acc,
                    'is_cash':    is_cash,
                }

    # 최종 반올림
    heatmap_items = []
    for it in _hm_merged.values():
        heatmap_items.append({
            'name':       it['name'],
            'pct':        round(it['pct'], 2),
            'daily_pct':  round(it['daily_pct'], 2),
            'val':        round(it['val']),
            'daily_krw':  round(it['daily_krw']),
            'profit_krw': round(it['profit_krw']),
            'price':      it['price'],
            'acc':        it['acc'],
            'is_cash':    it['is_cash'],
        })
    heatmap_json = _json.dumps(heatmap_items, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — 포트폴리오 손익</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f6f8;color:#222;font-size:14px}}
.header{{background:#1a1a2e;color:#fff;padding:18px 28px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
.header-text{{flex:1}}
.header h1{{font-size:20px;font-weight:700}}
.header .sub{{font-size:12px;color:#aaa;margin-top:3px}}
.btn-heatmap{{padding:8px 18px;background:#00838f;color:#fff;border:none;border-radius:7px;
              cursor:pointer;font-size:13px;font-weight:700;letter-spacing:.3px;
              box-shadow:0 2px 8px rgba(0,0,0,.25);transition:background .2s;white-space:nowrap}}
.btn-heatmap:hover{{background:#00696f}}
.btn-heatmap.active{{background:#e65100}}
.btn-heatmap.active:hover{{background:#bf4000}}
.container{{max-width:1400px;margin:0 auto;padding:20px 16px 60px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-bottom:20px}}
.sbox{{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.sbox.grand{{background:#1a1a2e;color:#fff}}
.sbox .sl{{font-size:11px;color:#999;margin-bottom:5px}}
.sbox.grand .sl{{color:#aaa}}
.sbox .sv{{font-size:22px;font-weight:800;line-height:1.1}}
.sbox .sv2{{font-size:12px;color:#888;margin-top:4px}}
.sbox.grand .sv2{{color:#aaa}}
.acc-card{{background:#fff;border-radius:10px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden}}
.acc-header{{display:flex;align-items:center;gap:12px;padding:14px 18px;background:#fafafa;border-bottom:1px solid #eee}}
.acc-name{{font-size:14px;font-weight:700;flex:1}}
.acc-val{{font-size:15px;font-weight:700}}
.acc-pnl{{font-size:13px;font-weight:600}}
table{{width:100%;border-collapse:collapse}}
th{{background:#f5f5f5;padding:9px 12px;text-align:left;font-size:11px;font-weight:700;color:#888;white-space:nowrap;border-bottom:2px solid #eee}}
td{{padding:10px 12px;border-bottom:1px solid #f5f5f5;font-size:13px}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#fafafa}}
.cash-row td{{color:#888;background:#fafffe}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.pct{{font-weight:600}}
.center{{text-align:center}}
.name-cell{{font-weight:600}}
.fx-tag{{font-size:10px;padding:2px 4px;background:#f0f7ff;color:#0056b3;border-radius:3px;margin-left:4px}}
.footer{{text-align:center;font-size:11px;color:#bbb;margin-top:30px}}

/* ── 히트맵 ────────────────────────────────────────────── */
#heatmap-view{{display:none;margin-bottom:20px}}
#heatmap-view.show{{display:block}}
.hm-wrap{{
  background:#fff;border-radius:12px;padding:16px 16px 12px;
  box-shadow:0 1px 6px rgba(0,0,0,.08);
}}
.hm-header{{display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap}}
.hm-title{{font-size:12px;color:#666;font-weight:600;letter-spacing:.4px;flex:1}}
.hm-tabs{{display:flex;gap:6px}}
.hm-tab{{
  padding:5px 14px;font-size:12px;font-weight:700;border:none;
  border-radius:5px;cursor:pointer;transition:background .15s,color .15s;
  background:#f0f2f5;color:#666;
}}
.hm-tab.active{{background:#00838f;color:#fff}}
#hm-canvas{{
  position:relative;width:100%;height:520px;overflow:hidden;border-radius:6px;
}}
.hm-tile{{position:absolute;box-sizing:border-box;padding:2px;cursor:default;}}
.hm-inner{{
  width:100%;height:100%;border-radius:5px;
  display:flex;flex-direction:column;justify-content:center;align-items:center;
  overflow:hidden;transition:filter .15s,background .35s;
  gap:1px;
}}
.hm-tile:hover .hm-inner{{filter:brightness(1.18) saturate(1.1);}}
.hm-name{{
  font-size:11px;font-weight:600;color:rgba(255,255,255,.82);
  text-shadow:0 1px 4px rgba(0,0,0,.7);letter-spacing:.5px;
  text-align:center;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:92%;
  text-transform:uppercase;
}}
.hm-pct{{
  font-size:18px;font-weight:900;color:#fff;
  text-shadow:0 2px 8px rgba(0,0,0,.55),0 1px 2px rgba(0,0,0,.4);
  margin-top:2px;line-height:1;letter-spacing:-.3px;
}}
.hm-val{{
  font-size:11px;font-weight:600;color:rgba(255,255,255,.78);
  text-shadow:0 1px 4px rgba(0,0,0,.6);margin-top:3px;
}}
.hm-amount{{
  font-size:10px;font-weight:500;color:rgba(255,255,255,.65);
  text-shadow:0 1px 3px rgba(0,0,0,.5);margin-top:1px;
}}
.hm-legend{{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:11px;color:#888}}
.hm-legend-bar{{
  flex:1;height:8px;border-radius:4px;
  background:linear-gradient(to right,
    #ff3c3c,#c62828,#5a1a1a,#1a2a1a,#1a6e3a,#00dc5a);
}}
</style>
</head>
<body>
<div class="header">
  <div class="header-text">
    <h1>Jason Market — 포트폴리오 손익</h1>
    <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 실시간 환율 ₩{usdkrw:,.2f}/USD</div>
  </div>
  <button class="btn-heatmap" id="btn-hm" onclick="toggleHeatmap()">🟦 히트맵 보기</button>
</div>
<div class="container">
  <!-- 히트맵 뷰 -->
  <div id="heatmap-view">
    <div class="hm-wrap">
      <div class="hm-header">
        <div class="hm-title">PORTFOLIO HEATMAP &nbsp;·&nbsp; 타일 크기 = 평가금액 비중</div>
        <div class="hm-tabs">
          <button class="hm-tab active" id="tab-total" onclick="switchMode('total')">📊 총 수익률</button>
          <button class="hm-tab"        id="tab-daily" onclick="switchMode('daily')">📅 일일 수익률</button>
        </div>
      </div>
      <div id="hm-canvas"></div>
      <div class="hm-legend">
        <span style="color:#ff3c3c">▼ 대폭 하락</span>
        <div class="hm-legend-bar"></div>
        <span style="color:#00dc5a">▲ 대폭 상승</span>
        &nbsp;|&nbsp;<span>색상 기준 ±10%</span>
      </div>
    </div>
  </div>

  <div id="table-view">
  <div class="summary">
    <div class="sbox grand">
      <div class="sl">총 평가금액</div>
      <div class="sv">₩{grand_curr:,.0f}</div>
      <div class="sv2">${grand_usd:,.0f}</div>
    </div>
    <div class="sbox" style="border-left:4px solid {gpc}">
      <div class="sl">총 손익</div>
      <div class="sv" style="color:{gpc}">{sign(grand_profit)}₩{grand_profit:,.0f}</div>
      <div class="sv2" style="color:{gpc}">{sign(grand_pct)}{grand_pct:.2f}%</div>
    </div>
    <div class="sbox" style="border-left:4px solid {gdc}">
      <div class="sl">총 1일 손익 (주가+환율)</div>
      <div class="sv" style="color:{gdc}">{sign(grand_daily)}₩{grand_daily:,.0f}</div>
      <div class="sv2" style="color:#888">전일 환율 ₩{prev_usdkrw:,.2f} 대비</div>
    </div>
  </div>
  {account_sections}
  <div class="footer">Jason Market · {timestamp} · 구글드라이브 자산계산기.xlsx 자동 동기화</div>
  </div><!-- /table-view -->
</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#00838f;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.2)">📋 전체 복사</button>
<script>
var _hmData = {heatmap_json};
var _hmBuilt = false;

/* ═══════════════════════════════════════════════════════
   Squarified Treemap  (Bruls, Huizing, van Wijk 1999)
   ═══════════════════════════════════════════════════════ */
function squarify(nodes, x, y, w, h) {{
  var out = [];
  var sorted = nodes.slice().sort(function(a,b){{return b.val-a.val;}});

  function layout(items, rx, ry, rw, rh) {{
    if (!items.length || rw < 1 || rh < 1) return;
    if (items.length === 1) {{
      out.push({{item:items[0], x:rx, y:ry, w:rw, h:rh}});
      return;
    }}
    var sub   = items.reduce(function(s,i){{return s+i.val;}}, 0);
    var scale = rw * rh / sub;
    var short = Math.min(rw, rh);

    /* 최적 row 탐색 */
    var row=[], rowSum=0, prevW=Infinity, split=0;
    for (var k=0; k<items.length; k++) {{
      row.push(items[k]); rowSum+=items[k].val;
      var cur = worst(row, rowSum, short, scale);
      if (cur > prevW) {{ row.pop(); rowSum-=items[k].val; break; }}
      prevW=cur; split=k+1;
    }}

    /* row 배치 */
    var rowArea = rowSum * scale;
    if (rw <= rh) {{                        /* 가로 strip (위) */
      var sh = rowArea / rw, cx = rx;
      row.forEach(function(it) {{
        var iw = it.val / rowSum * rw;
        out.push({{item:it, x:cx, y:ry, w:iw, h:sh}}); cx+=iw;
      }});
      layout(items.slice(split), rx, ry+sh, rw, rh-sh);
    }} else {{                               /* 세로 strip (왼쪽) */
      var sw = rowArea / rh, cy = ry;
      row.forEach(function(it) {{
        var ih = it.val / rowSum * rh;
        out.push({{item:it, x:rx, y:cy, w:sw, h:ih}}); cy+=ih;
      }});
      layout(items.slice(split), rx+sw, ry, rw-sw, rh);
    }}
  }}

  function worst(row, rowSum, short, scale) {{
    var ra = rowSum*scale, sd = ra/short, w=0;
    row.forEach(function(it) {{
      var nd = it.val/rowSum*short;
      var r  = Math.max(sd/nd, nd/sd);
      if (r>w) w=r;
    }});
    return w;
  }}

  layout(sorted, x, y, w, h);
  return out;
}}

/* ══════════════════════════════════════════════════════
   색상 계산
   0% 근처 = 어두운 중립
   상승 폭 클수록 → 밝은 녹색 (#00dc5a)
   하락 폭 클수록 → 밝은 빨간색 (#ff3c3c)
   기준: ±10%  (초과분은 클리핑)
   ══════════════════════════════════════════════════════ */
function hmColor(pct) {{
  var t = Math.min(1, Math.abs(pct) / 10);   /* 0 → 1 (폭 크기) */
  var r, g, b;
  if (pct >= 0) {{
    /* 어두운 중립 #1a2a1a  →  밝은 초록 #00dc5a */
    r = Math.round(26  + (0   - 26 ) * t);
    g = Math.round(42  + (220 - 42 ) * t);
    b = Math.round(26  + (90  - 26 ) * t);
  }} else {{
    /* 어두운 중립 #2a1a1a  →  밝은 빨강 #ff3c3c */
    r = Math.round(42  + (255 - 42 ) * t);
    g = Math.round(26  + (60  - 26 ) * t);
    b = Math.round(26  + (60  - 26 ) * t);
  }}
  return 'rgb('+r+','+g+','+b+')';
}}

/* ══════════════════════════════════
   모드 상태 & 타일 참조 캐시
   ══════════════════════════════════ */
var _mode    = 'total';   /* 'total' | 'daily' */
var _tilRefs = [];        /* {{inner, pctEl, item, div}} */

/* ══════════════════════════════════
   금액 포맷  (±₩1.2억 / ±₩234만)
   ══════════════════════════════════ */
function fmtKrw(v) {{
  var sign = v >= 0 ? '+' : '-';
  var abs  = Math.abs(v);
  if (abs >= 1e8) return sign+'₩'+(abs/1e8).toFixed(1)+'억';
  if (abs >= 1e4) return sign+'₩'+Math.round(abs/1e4)+'만';
  return sign+'₩'+abs.toLocaleString();
}}
function fmtVal(v) {{
  if (v >= 1e8) return '₩'+(v/1e8).toFixed(1)+'억';
  return '₩'+Math.round(v/1e4)+'만';
}}

/* ══════════════════════════════════
   타일 렌더링 (최초 1회)
   ══════════════════════════════════ */
function buildHeatmap() {{
  if (_hmBuilt) return;
  _hmBuilt = true;

  var canvas = document.getElementById('hm-canvas');
  var W = canvas.offsetWidth || 900;
  var H = 520;
  var tiles = squarify(_hmData, 0, 0, W, H);

  tiles.forEach(function(t) {{
    var item    = t.item;
    var minSide = Math.min(t.w, t.h);

    /* 타일 크기에 따라 표시 레벨 결정 */
    var showName   = t.w > 45  && t.h > 30;
    var showPct    = t.w > 30  && t.h > 22;
    var showVal    = minSide > 58;
    var showAmount = minSide > 78;

    var fName   = Math.max(9,  Math.min(13, minSide*0.13)) + 'px';
    var fPct    = Math.max(11, Math.min(22, minSide*0.22)) + 'px';
    var fSub    = Math.max(8,  Math.min(12, minSide*0.11)) + 'px';

    /* 타일 외곽 */
    var div = document.createElement('div');
    div.className = 'hm-tile';
    div.style.cssText = 'left:'+t.x+'px;top:'+t.y+'px;width:'+t.w+'px;height:'+t.h+'px';

    /* 내부 */
    var inner = document.createElement('div');
    inner.className = 'hm-inner';

    /* ① 종목명 */
    if (showName) {{
      var el = document.createElement('div');
      el.className  = 'hm-name';
      el.style.fontSize = fName;
      el.textContent = item.is_cash ? '현금' : item.name;
      inner.appendChild(el);
    }}

    /* ② 증감율 (모드 전환 대상) */
    var pctEl = null;
    if (showPct) {{
      pctEl = document.createElement('div');
      pctEl.className = 'hm-pct';
      pctEl.style.fontSize = fPct;
      inner.appendChild(pctEl);
    }}

    /* ③ 총 평가액 */
    if (showVal) {{
      var el = document.createElement('div');
      el.className = 'hm-val';
      el.style.fontSize = fSub;
      el.textContent = fmtVal(item.val);
      inner.appendChild(el);
    }}

    /* ④ 증감금액 (모드에 따라 일/총 하나만 표시) */
    var amountEl = null;
    if (showAmount) {{
      amountEl = document.createElement('div');
      amountEl.className = 'hm-amount';
      amountEl.style.fontSize = fSub;
      inner.appendChild(amountEl);
    }}

    div.appendChild(inner);
    canvas.appendChild(div);

    _tilRefs.push({{
      inner:inner, pctEl:pctEl, amountEl:amountEl,
      div:div, item:item
    }});
  }});

  /* 초기 색상·수치 적용 */
  _applyMode();
}}

/* ══════════════════════════════════
   모드 적용 (색상 + 수치 갱신)
   ══════════════════════════════════ */
function _applyMode() {{
  _tilRefs.forEach(function(ref) {{
    var item = ref.item;
    var pct  = _mode === 'daily' ? item.daily_pct : item.pct;
    var sign = pct >= 0 ? '+' : '';

    /* 색상: 현금은 중립 슬레이트 */
    ref.inner.style.background = item.is_cash ? '#546e7a' : hmColor(pct);

    /* ② 증감율 */
    if (ref.pctEl)
      ref.pctEl.textContent = item.is_cash ? '-' : (sign + pct.toFixed(2) + '%');

    /* ④ 증감금액 — 모드에 따라 일/총 하나만 */
    if (ref.amountEl) {{
      if (item.is_cash) {{
        ref.amountEl.textContent = '';
      }} else if (_mode === 'daily') {{
        ref.amountEl.textContent = '일 ' + fmtKrw(item.daily_krw);
      }} else {{
        ref.amountEl.textContent = '총 ' + fmtKrw(item.profit_krw);
      }}
    }}

    /* 툴팁 */
    ref.div.title =
      item.name +
      ' | ' + (_mode==='daily'?'일일':'총') + ' ' + sign + pct.toFixed(2) + '%' +
      ' | 평가 ' + fmtVal(item.val) +
      ' | 일 ' + fmtKrw(item.daily_krw) +
      ' | 총 ' + fmtKrw(item.profit_krw) +
      ' | ' + item.acc;
  }});
}}

/* ══════════════════════════════════
   모드 전환 버튼
   ══════════════════════════════════ */
function switchMode(mode) {{
  _mode = mode;
  document.getElementById('tab-total').classList.toggle('active', mode==='total');
  document.getElementById('tab-daily').classList.toggle('active', mode==='daily');
  if (_hmBuilt) _applyMode();
}}

/* ══════════════════════════════════
   히트맵 ↔ 테이블 토글
   ══════════════════════════════════ */
function toggleHeatmap() {{
  var hv  = document.getElementById('heatmap-view');
  var tv  = document.getElementById('table-view');
  var btn = document.getElementById('btn-hm');
  if (hv.classList.contains('show')) {{
    hv.classList.remove('show');
    tv.style.display = '';
    btn.textContent = '🟦 히트맵 보기';
    btn.classList.remove('active');
  }} else {{
    buildHeatmap();
    hv.classList.add('show');
    tv.style.display = 'none';
    btn.textContent = '📋 테이블 보기';
    btn.classList.add('active');
    window.scrollTo({{top:0, behavior:'smooth'}});
  }}
}}

/* ══════════════════════════════════
   복사
   ══════════════════════════════════ */
function copyReport() {{
  var el = document.querySelector('#table-view') || document.body;
  navigator.clipboard.writeText(el.innerText).then(function() {{
    var b = document.getElementById('copy-btn');
    b.textContent='✅ 복사 완료!'; b.style.background='#2e7d32';
    setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#00838f';}},2500);
  }}).catch(function() {{
    var t=document.createElement('textarea'); t.value=el.innerText;
    document.body.appendChild(t); t.select(); document.execCommand('copy'); document.body.removeChild(t);
  }});
}}
</script>
</body>
</html>"""
    return html

# ── 메인 ─────────────────────────────────────────────────

def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*90}")
    print(f"  Jason & 와이프 포트폴리오 손익   {timestamp}")
    print(f"{'━'*90}")
    print("  xlsx 동기화 및 가격 조회 중...\n")

    # ── [FIX] xlsx 자동 sync 비활성화 → portfolio.json이 덮어씌워지는 문제 방지 ──
    # holdings = load_portfolio()  # 이 호출은 sync_to_json()을 통해 portfolio.json을 덮어씌움
    # 대신 직접 portfolio.json을 읽기
    import os
    portfolio_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio.json')
    if os.path.exists(portfolio_json_path):
        import json
        with open(portfolio_json_path, encoding='utf-8') as f:
            portfolio_data = json.load(f)
        holdings = []
        for acc, items in portfolio_data.items():
            for item in items:
                item['account'] = acc
                holdings.append(item)
    else:
        holdings = None

    if not holdings:
        print("  보유 종목 없음. portfolio.json 파일을 확인하세요.")
        return

    usdkrw_tuple = get_usdkrw()
    usdkrw, _ = usdkrw_tuple
    print(f"  현재 환율: ₩{usdkrw:,.2f}/USD\n")

    # ── [NEW] 엑셀 O14 셀 실시간 업데이트 ───────────────────
    update_xlsx_live_fx(usdkrw)

    accounts_data, new_cash_tracker = calc_data(holdings, usdkrw_tuple)
    if not accounts_data:
        print("  유효한 보유 종목 없음.")
        return

    # 현금 추적값 저장 (다음 실행 시 일일손익 계산용)
    _save_cash_tracker(new_cash_tracker)

    print_terminal(accounts_data, usdkrw, timestamp)

    html = generate_html(accounts_data, usdkrw_tuple, timestamp)
    tmp  = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='portfolio_tracker_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")

if __name__ == '__main__':
    main()
