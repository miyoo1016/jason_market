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

def fetch_all_prices(holdings, usdkrw):
    """병렬로 모든 종목 현재가+전일종가 조회 (1일 손익용)"""
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
                # Ticker.info는 느리지만 프리마켓 가격을 가장 정확히 담고 있음
                info = tk.info
                # 프리마켓 -> 장중 -> 포스트마켓 순서로 유효한 가격 찾기
                live_price = (
                    info.get('preMarketPrice') or 
                    info.get('regularMarketPrice') or 
                    info.get('postMarketPrice')
                )
                prev = info.get('regularMarketPreviousClose') or info.get('previousClose')
                
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

# ── 데이터 계산 ───────────────────────────────────────────

def calc_data(holdings, usdkrw_tuple):
    """모든 계좌 손익 계산 → accounts_data 반환"""
    usdkrw, prev_usdkrw = usdkrw_tuple
    valid = [h for h in holdings if h.get('ticker') and float(h.get('qty', 0)) > 0]
    price_cache = fetch_all_prices(valid, usdkrw)

    accounts = {}
    for h in valid:
        acc = h.get('account', '기타')
        accounts.setdefault(acc, []).append(h)

    accounts_data = {}
    for acc, items in accounts.items():
        rows = []
        acc_cost = acc_curr = acc_daily_profit = 0

        for h in items:
            qty = float(h['qty'])
            avg = float(h['avg_price'])
            cur = h.get('currency', 'KRW')

            if h.get('is_cash') or h.get('ticker') == 'CASH':
                cash_krw = avg if cur == 'KRW' else avg * usdkrw
                acc_cost += cash_krw
                acc_curr += cash_krw
                rows.append({
                    'name': h['name'], 'qty': '현금', 'is_cash': True,
                    'avg': '', 'price': '', 'cur': cur,
                    'val_krw': cash_krw, 'profit_krw': 0, 'daily_profit_krw': 0, 'pct': 0,
                })
                continue

            price, prev_close = get_price(h, price_cache, usdkrw)
            if price is None: continue

            base_fx = h.get('base_usdkrw', usdkrw)
            is_usd = (cur == 'USD')

            p_cost = h.get('precision_cost_krw')
            is_usd = (cur == 'USD')

            if is_usd:
                # 1순위: H열 정밀 데이터 (환율일수도, 총액일수도 있음)
                if p_cost is not None:
                    if p_cost < 10000: # 환율로 입력한 경우 (예: 1463.01)
                        cost_krw = qty * avg * p_cost
                    else: # 총액으로 입력한 경우 (예: 55,000,000)
                        cost_krw = p_cost
                else: # 데이터가 없으면 기존 기준환율 사용
                    cost_krw = qty * avg * base_fx
                
                current_krw = qty * price * usdkrw
                # 1일 손익: (오늘가*오늘환율 - 어제가*어제환율) * 수량 -> 환차손익 포함
                if prev_close:
                    daily_profit_krw = (price * usdkrw - prev_close * prev_usdkrw) * qty
                else:
                    daily_profit_krw = 0
                avg_s  = f"${avg:,.2f}"; pri_s  = f"${price:,.2f}"
                
                # 정밀 데이터(환율/총액)를 바탕으로 주가 수익과 환차 수익을 더 정확히 분리
                # 실질 구매 환율(eff_base_fx) 도출
                eff_base_fx = p_cost if (p_cost is not None and p_cost < 10000) else (cost_krw / (qty * avg) if (qty * avg) > 0 else base_fx)
                
                fx_pnl = (usdkrw - eff_base_fx) * avg * qty
                price_pnl = current_krw - cost_krw - fx_pnl
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

    return accounts_data

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
                line = (f"  │ {r['name']:<16} {'현금':>8} {'':>12} {'':>12} "
                        f"{fmt_krw(r['val_krw']):>16} {'₩0':>14} {'₩0':>12} {'0.00%':>8}")
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
                rows_html += f"""
      <tr class="cash-row">
        <td class="name-cell">{r['name']}</td>
        <td class="center">현금</td>
        <td>-</td><td>-</td>
        <td class="num">₩{r['val_krw']:,.0f}</td>
        <td class="num" style="color:#888">₩0</td>
        <td class="num" style="color:#888">₩0</td>
        <td class="num pct" style="color:#888">0.00%</td>
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

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — 포트폴리오 손익</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f6f8;color:#222;font-size:14px}}
.header{{background:#1a1a2e;color:#fff;padding:20px 28px}}
.header h1{{font-size:20px;font-weight:700}}
.header .sub{{font-size:12px;color:#aaa;margin-top:3px}}
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
</style>
</head>
<body>
<div class="header">
  <h1>Jason Market — 포트폴리오 손익</h1>
  <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 실시간 환율 ₩{usdkrw:,.2f}/USD</div>
</div>
<div class="container">
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
</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
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

    holdings = load_portfolio()
    if not holdings:
        print("  보유 종목 없음. xlsx 파일을 확인하세요.")
        return

    usdkrw_tuple = get_usdkrw()
    usdkrw, _ = usdkrw_tuple
    print(f"  현재 환율: ₩{usdkrw:,.2f}/USD\n")

    # ── [NEW] 엑셀 O14 셀 실시간 업데이트 ───────────────────
    update_xlsx_live_fx(usdkrw)

    accounts_data = calc_data(holdings, usdkrw_tuple)
    if not accounts_data:
        print("  유효한 보유 종목 없음.")
        return

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
