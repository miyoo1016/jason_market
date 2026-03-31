#!/usr/bin/env python3
"""포트폴리오 손익 추적기 - Jason Market
구글드라이브 자산계산기.xlsx → 실시간 손익 계산 + HTML 대시보드"""

import os
import webbrowser
import tempfile
import threading
import yfinance as yf
from datetime import datetime
from xlsx_sync import load_portfolio

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
            return price
    except Exception:
        pass
    # fallback: GC=F 계산
    try:
        gc = yf.Ticker('GC=F').history(period='2d')
        return round(float(gc['Close'].iloc[-1]) * usdkrw / 31.1035, 0)
    except Exception:
        return None

def get_usdkrw():
    try:
        h = yf.Ticker('USDKRW=X').history(period='2d')
        return float(h['Close'].iloc[-1]) if not h.empty else 1450.0
    except Exception:
        return 1450.0

def fetch_all_prices(holdings, usdkrw):
    """병렬로 모든 종목 현재가 조회"""
    tickers = set()
    for h in holdings:
        t = h.get('ticker', '')
        if t and t not in ('CASH', 'GOLD_KRX', ''):
            tickers.add(t)

    cache = {}

    us_tickers = [t for t in tickers if not t.endswith('.KS') and '^KS' not in t]
    kr_tickers = [t for t in tickers if t.endswith('.KS') or '^KS' in t]

    def _fetch_us():
        """미국/글로벌: 1분봉 prepost → 프리·애프터마켓 포함 실시간 가격"""
        if not us_tickers:
            return
        try:
            data = yf.download(us_tickers, period='1d', interval='1m',
                               prepost=True, auto_adjust=True, progress=False, threads=True)
            closes = data['Close'] if 'Close' in data else data
            for t in us_tickers:
                try:
                    col = closes[t] if hasattr(closes, 'columns') and t in closes.columns else closes
                    val = float(col.dropna().iloc[-1])
                    cache[t] = val
                except Exception:
                    pass
        except Exception:
            pass

    def _fetch_kr():
        """한국 종목: 일봉 (정규장)"""
        if not kr_tickers:
            return
        try:
            data = yf.download(kr_tickers, period='2d',
                               auto_adjust=True, progress=False, threads=True)
            closes = data['Close'] if 'Close' in data else data
            for t in kr_tickers:
                try:
                    col = closes[t] if hasattr(closes, 'columns') and t in closes.columns else closes
                    val = float(col.dropna().iloc[-1])
                    cache[t] = val
                except Exception:
                    pass
        except Exception:
            pass

    def _fetch_single(t):
        """batch 실패 시 개별 조회 (KS 티커 fallback)"""
        if t not in cache:
            try:
                hist = yf.Ticker(t).history(period='2d')
                if not hist.empty:
                    cache[t] = float(hist['Close'].iloc[-1])
            except Exception:
                pass

    # GOLD_KRX 병렬 조회
    gold_result = [None]
    def _gold():
        gold_result[0] = _fetch_gold_krx(usdkrw)

    t_us = threading.Thread(target=_fetch_us, daemon=True)
    t_kr = threading.Thread(target=_fetch_kr, daemon=True)
    gt   = threading.Thread(target=_gold, daemon=True)
    t_us.start(); t_kr.start(); gt.start()
    t_us.join(timeout=30); t_kr.join(timeout=30); gt.join(timeout=30)

    # batch에서 빠진 티커 개별 재시도
    missing = [t for t in tickers if t not in cache]
    if missing:
        threads = [threading.Thread(target=_fetch_single, args=(t,), daemon=True) for t in missing]
        for t in threads: t.start()
        for t in threads: t.join(timeout=20)

    cache['GOLD_KRX_PRICE'] = gold_result[0]
    return cache

def get_price(h, price_cache, usdkrw):
    ticker = h.get('ticker', '')
    if ticker == 'CASH':
        return None
    if ticker == 'GOLD_KRX':
        return price_cache.get('GOLD_KRX_PRICE') or h.get('xlsx_price')
    # KS 티커 포함 모든 일반 티커 → 캐시에서 조회 (없으면 xlsx 저장값 fallback)
    return price_cache.get(ticker) or h.get('xlsx_price')

# ── 포맷 헬퍼 ─────────────────────────────────────────────

def fmt_krw(val):
    return f"₩{val:>15,.0f}"

def fmt_usd(val):
    return f"${val:>12,.0f}" if abs(val) >= 1000 else f"${val:>12,.2f}"

def fmt_pct(val):
    return f"{val:>+7.2f}%"

# ── 데이터 계산 ───────────────────────────────────────────

def calc_data(holdings, usdkrw):
    """모든 계좌 손익 계산 → accounts_data 반환"""
    valid = [h for h in holdings if h.get('ticker') and float(h.get('qty', 0)) > 0]
    price_cache = fetch_all_prices(valid, usdkrw)

    accounts = {}
    for h in valid:
        acc = h.get('account', '기타')
        accounts.setdefault(acc, []).append(h)

    accounts_data = {}
    for acc, items in accounts.items():
        rows = []
        acc_cost = acc_curr = 0

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
                    'val_krw': cash_krw, 'profit_krw': 0, 'pct': 0,
                })
                continue

            price = get_price(h, price_cache, usdkrw)
            if price is None:
                continue

            if cur == 'USD':
                cost_krw    = qty * avg   * usdkrw
                current_krw = qty * price * usdkrw
                avg_s  = f"${avg:,.2f}"
                pri_s  = f"${price:,.2f}"
            else:
                cost_krw    = qty * avg
                current_krw = qty * price
                avg_s  = f"₩{avg:,.0f}"
                pri_s  = f"₩{price:,.0f}"

            profit_krw = current_krw - cost_krw
            pct = profit_krw / cost_krw * 100 if cost_krw > 0 else 0
            acc_cost += cost_krw
            acc_curr += current_krw

            rows.append({
                'name': h['name'], 'qty': f"{qty:,.0f}", 'is_cash': False,
                'avg': avg_s, 'price': pri_s, 'cur': cur,
                'val_krw': current_krw, 'profit_krw': profit_krw, 'pct': pct,
            })

        acc_profit = acc_curr - acc_cost
        acc_pct    = acc_profit / acc_cost * 100 if acc_cost > 0 else 0
        accounts_data[acc] = {
            'rows': rows,
            'cost':   acc_cost,
            'curr':   acc_curr,
            'profit': acc_profit,
            'pct':    acc_pct,
        }

    return accounts_data

# ── 터미널 출력 ───────────────────────────────────────────

def print_terminal(accounts_data, usdkrw, timestamp):
    print(f"\n{'━'*90}")
    print(f"  Jason & 와이프 포트폴리오 손익   {timestamp}")
    print(f"  환율: ₩{usdkrw:,.2f}/USD")
    print(f"{'━'*90}")

    grand_cost = grand_curr = 0

    for acc, d in accounts_data.items():
        print(f"  ┌─ {acc} {'─'*60}")
        print(f"  │ {'종목':<16} {'수량':>8} {'평단가':>12} {'현재가':>12} {'평가금액(₩)':>16} {'손익(₩)':>14} {'수익률':>8}")
        print(f"  │ {'─'*90}")

        for r in d['rows']:
            if r['is_cash']:
                line = (f"  │ {r['name']:<16} {'현금':>8} {'':>12} {'':>12} "
                        f"{fmt_krw(r['val_krw']):>16} {'₩0':>14} {'0.00%':>8}")
            else:
                line = (f"  │ {r['name']:<16} {r['qty']:>8} "
                        f"{r['avg']:>12} {r['price']:>12} "
                        f"{fmt_krw(r['val_krw']):>16} "
                        f"{fmt_krw(r['profit_krw']):>14} "
                        f"{fmt_pct(r['pct']):>8}")
            print(alert_line(line))

        print(f"  │ {'─'*90}")
        summary = (f"  │ {'[계좌합계]':<16} {'':>8} {'':>12} {'':>12} "
                   f"{fmt_krw(d['curr']):>16} "
                   f"{fmt_krw(d['profit']):>14} "
                   f"{fmt_pct(d['pct']):>8}")
        print(alert_line(summary))
        print(f"  └{'─'*91}\n")

        grand_cost += d['cost']
        grand_curr += d['curr']

    grand_profit = grand_curr - grand_cost
    grand_pct    = grand_profit / grand_cost * 100 if grand_cost > 0 else 0
    grand_usd    = grand_curr / usdkrw

    print(f"  {'━'*90}")
    print(alert_line(f"    총 평가금액  : {fmt_krw(grand_curr)}  (${grand_usd:,.0f})"))
    print(alert_line(f"    총 손익      : {fmt_krw(grand_profit)}  ({grand_pct:+.2f}%)"))
    print(f"  {'━'*90}")
    print(f"\n  ※ 데이터 출처: 구글드라이브 자산계산기.xlsx\n")

    return grand_cost, grand_curr, grand_profit, grand_pct, grand_usd

# ── HTML 생성 ─────────────────────────────────────────────

def generate_html(accounts_data, usdkrw, timestamp):
    grand_cost = sum(d['cost'] for d in accounts_data.values())
    grand_curr = sum(d['curr'] for d in accounts_data.values())
    grand_profit = grand_curr - grand_cost
    grand_pct    = grand_profit / grand_cost * 100 if grand_cost > 0 else 0
    grand_usd    = grand_curr / usdkrw

    # 수익색
    def pnl_color(val):
        return '#2ecc71' if val >= 0 else '#e74c3c'

    def pnl_bg(val):
        return '#f0fff4' if val >= 0 else '#fff0f0'

    def sign(val):
        return '+' if val >= 0 else ''

    # 계좌별 HTML
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
        <td class="num pct" style="color:#888">0.00%</td>
      </tr>"""
            else:
                pc = pnl_color(r['profit_krw'])
                rows_html += f"""
      <tr>
        <td class="name-cell">{r['name']}</td>
        <td class="num center">{r['qty']}</td>
        <td class="num">{r['avg']}</td>
        <td class="num">{r['price']}</td>
        <td class="num">₩{r['val_krw']:,.0f}</td>
        <td class="num" style="color:{pc}">{sign(r['profit_krw'])}₩{r['profit_krw']:,.0f}</td>
        <td class="num pct" style="color:{pc}">{sign(r['pct'])}{r['pct']:.2f}%</td>
      </tr>"""

        acc_col = pnl_color(d['profit'])
        acc_bg  = pnl_bg(d['profit'])
        account_sections += f"""
  <div class="acc-card">
    <div class="acc-header">
      <span class="acc-name">{acc}</span>
      <span class="acc-val">₩{d['curr']:,.0f}</span>
      <span class="acc-pnl" style="color:{acc_col}">{sign(d['profit'])}₩{d['profit']:,.0f} ({sign(d['pct'])}{d['pct']:.2f}%)</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>종목</th><th class="center">수량</th><th>평단가</th><th>현재가</th>
          <th>평가금액</th><th>손익</th><th>수익률</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr style="background:{acc_bg}">
          <td colspan="4" style="font-weight:700;padding:10px 12px">계좌 합계</td>
          <td class="num" style="font-weight:700">₩{d['curr']:,.0f}</td>
          <td class="num" style="color:{acc_col};font-weight:700">{sign(d['profit'])}₩{d['profit']:,.0f}</td>
          <td class="num pct" style="color:{acc_col};font-weight:700">{sign(d['pct'])}{d['pct']:.2f}%</td>
        </tr>
      </tfoot>
    </table>
  </div>"""

    gpc = pnl_color(grand_profit)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — 포트폴리오 손익</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#222;font-size:14px}}
.header{{background:#1a1a2e;color:#fff;padding:20px 28px}}
.header h1{{font-size:20px;font-weight:700}}
.header .sub{{font-size:12px;color:#aaa;margin-top:3px}}
.container{{max-width:1400px;margin:0 auto;padding:20px 16px 60px}}

/* 종합 요약 */
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}}
.sbox{{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.sbox.grand{{background:#1a1a2e;color:#fff}}
.sbox .sl{{font-size:11px;color:#999;margin-bottom:5px}}
.sbox.grand .sl{{color:#aaa}}
.sbox .sv{{font-size:22px;font-weight:800;line-height:1.1}}
.sbox .sv2{{font-size:12px;color:#888;margin-top:4px}}
.sbox.grand .sv2{{color:#aaa}}

/* 계좌 카드 */
.acc-card{{background:#fff;border-radius:10px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden}}
.acc-header{{display:flex;align-items:center;gap:12px;padding:14px 18px;background:#fafafa;border-bottom:1px solid #eee}}
.acc-name{{font-size:14px;font-weight:700;flex:1}}
.acc-val{{font-size:15px;font-weight:700}}
.acc-pnl{{font-size:13px;font-weight:600}}

/* 테이블 */
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
tfoot td{{font-size:13px}}

.footer{{text-align:center;font-size:11px;color:#bbb;margin-top:30px}}
</style>
</head>
<body>
<div class="header">
  <h1>Jason Market — 포트폴리오 손익</h1>
  <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 환율 ₩{usdkrw:,.2f}/USD</div>
</div>
<div class="container">

  <!-- 종합 요약 -->
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
    <div class="sbox">
      <div class="sl">투자 원금</div>
      <div class="sv">₩{grand_cost:,.0f}</div>
    </div>
    <div class="sbox">
      <div class="sl">계좌 수</div>
      <div class="sv">{len(accounts_data)}개</div>
      <div class="sv2">환율 ₩{usdkrw:,.0f}/USD</div>
    </div>
  </div>

  <!-- 계좌별 상세 -->
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

    usdkrw = get_usdkrw()
    print(f"  현재 환율: ₩{usdkrw:,.2f}/USD\n")

    accounts_data = calc_data(holdings, usdkrw)
    if not accounts_data:
        print("  유효한 보유 종목 없음.")
        return

    print_terminal(accounts_data, usdkrw, timestamp)

    # HTML 대시보드
    html = generate_html(accounts_data, usdkrw, timestamp)
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
