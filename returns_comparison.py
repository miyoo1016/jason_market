#!/usr/bin/env python3
"""수익률 비교 - Jason Market"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from xlsx_sync import load_portfolio as _load_pf
import os
import json
import webbrowser

ALERT = '\033[38;5;203m'  # 연한 빨간색 (극단 경고에만)
RESET = '\033[0m'

EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

PROXY_MAP = {
    'KODEX 나스닥100': 'QQQ',
    'KODEX S&P500':   'SPY',
    'KODEX 미국반도체': 'SOXX',
}

def _build_assets():
    """포트폴리오 보유 종목 + 시장 지표 → ASSETS dict, AVG_PRICE dict"""
    assets = {}
    avg_prices = {}   # ticker → avg_price (KRW 환산) — 포트폴리오 종목만
    seen = set()

    # 1. 포트폴리오 보유 종목 (동일 종목 합산 후 가중 평단가)
    try:
        qty_sum  = {}  # ticker → 총수량
        cost_sum = {}  # ticker → 총원가 (KRW)
        usdkrw_base = {}  # ticker → base_usdkrw
        for h in _load_pf():
            if h.get('is_cash') or h.get('ticker') == 'CASH': continue
            ticker = h['ticker']
            name   = h['name']
            if ticker == 'XLSX_PRICE': ticker = PROXY_MAP.get(name, 'SPY')
            elif ticker == 'GOLD_KRX': ticker = 'GC=F'
            if not ticker: continue

            qty = float(h.get('qty', 0) or 0)
            avg = float(h.get('avg_price', 0) or 0)
            cur = h.get('currency', 'KRW')
            base_fx = float(h.get('base_usdkrw', 1350) or 1350)

            cost_krw = avg * qty * (base_fx if cur == 'USD' else 1)

            if ticker not in seen:
                seen.add(ticker)
                assets[f'{name:<10}'] = ticker

            qty_sum[ticker]  = qty_sum.get(ticker, 0)  + qty
            cost_sum[ticker] = cost_sum.get(ticker, 0) + cost_krw
            usdkrw_base[ticker] = base_fx

        # 가중 평단가 계산 (KRW 환산)
        for tk in qty_sum:
            if qty_sum[tk] > 0:
                avg_prices[tk] = cost_sum[tk] / qty_sum[tk]  # 주당 원가(KRW)
    except Exception:
        pass

    # 2. 시장 지표 추가 (중복 제외)
    market = {
        'Bitcoin    ': 'BTC-USD',
        'Brent유(ICE)': 'BZ=F',
        'WTI원유(NYMEX)': 'CL=F',
        '다우지수(CME선물)': 'YM=F',
        'S&P500(CME선물)': 'ES=F',
        '나스닥100(CME선물)': 'NQ=F',
        '러셀2000(CME선물)': 'RTY=F',
        'S&P500 SPY ': 'SPY',
        '코스피      ': '^KS11',
        '달러/원    ': 'USDKRW=X',
        '미국 10년물 국채': '^TNX',
        'VIX(현물)   ': '^VIX',
    }
    for k, v in market.items():
        if v not in seen:
            seen.add(v)
            assets[k] = v
    return assets, avg_prices

ASSETS, AVG_PRICES = _build_assets()


def get_since_avg(ticker, avg_price_krw):
    """평단가 대비 현재 수익률 (KRW 환산 기준)"""
    try:
        hist = yf.Ticker(ticker).history(period='5d')
        if hist.empty: return None
        curr = float(hist['Close'].dropna().iloc[-1])
        is_krw = ticker.endswith('.KS') or ticker in ('^KS11', 'USDKRW=X', '^TNX', '^VIX')
        if not is_krw:
            # USD 자산: 현재가 × 현재 환율 → KRW 환산
            try:
                fx = yf.Ticker('USDKRW=X').history(period='2d')
                usdkrw = float(fx['Close'].iloc[-1]) if not fx.empty else 1450.0
            except Exception:
                usdkrw = 1450.0
            curr_krw = curr * usdkrw
        else:
            curr_krw = curr
        if avg_price_krw <= 0: return None
        return (curr_krw - avg_price_krw) / avg_price_krw * 100
    except Exception:
        return None

PERIODS = [
    ('1주',  '5d'),
    ('1달',  '1mo'),
    ('3달',  '3mo'),
    ('6달',  '6mo'),
    ('YTD',  'ytd'),
    ('1년',  '1y'),
]

def get_return(ticker, period):
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty or len(hist) < 2:
            return None
        hist = hist.dropna(subset=['Close'])
        if len(hist) < 2:
            return None
        start = float(hist['Close'].iloc[0])
        end   = float(hist['Close'].iloc[-1])
        if start == 0 or np.isnan(start) or np.isnan(end):
            return None
        return (end - start) / start * 100
    except Exception:
        return None

def fmt_ret(val):
    if val is None:
        return f"{'N/A':>8}"
    return f"{val:>+7.1f}%"

def rank_label(idx, total):
    """순위 이모지"""
    if idx == 0:
        return "🥇"
    if idx == 1:
        return "🥈"
    if idx == 2:
        return "🥉"
    return "  "

def _ret_cell_html(ret, highlight=False):
    if ret is None:
        return '<td style="color:#757575;">–</td>'
    color = "#26a69a" if ret >= 0 else "#ef5350"
    bold  = "font-weight:800;" if highlight else "font-weight:600;"
    border = "border-left:2px solid #1a5fa8;" if highlight else ""
    return f'<td style="color:{color};{bold}{border}">{ret:+.1f}%</td>'

def generate_html(all_returns, since_avg, timestamp):
    """
    all_returns: {name: [ret_1w, ret_1m, ...]}
    since_avg:   {name: float|None}  — 평단가 기준 수익률 (포트폴리오 종목만)
    """
    period_labels = [p[0] for p in PERIODS]
    has_since = any(v is not None for v in since_avg.values())

    # Build table rows
    table_rows = ""
    for name, rets in all_returns.items():
        valid = [r for r in rets if r is not None]
        avg   = sum(valid) / len(valid) if valid else 0
        if avg > 10:   row_bg = "rgba(38,166,154,0.18)"
        elif avg > 3:  row_bg = "rgba(38,166,154,0.10)"
        elif avg < -10:row_bg = "rgba(239,83,80,0.18)"
        elif avg < -3: row_bg = "rgba(239,83,80,0.10)"
        else:           row_bg = "transparent"

        cells = "".join(_ret_cell_html(r) for r in rets)

        # 매입 이후 수익률 셀 (포트폴리오 종목만)
        sa = since_avg.get(name)
        if has_since:
            cells += _ret_cell_html(sa, highlight=True) if sa is not None else '<td style="color:#555;">–</td>'

        table_rows += (f'<tr style="background:{row_bg};">'
                       f'<td style="text-align:left;padding-left:10px;">{name.strip()}</td>'
                       f'{cells}</tr>\n')

    # Build rankings section
    rankings_html = ""
    for pi, (label, period) in enumerate(PERIODS):
        rets = [(name.strip(), all_returns[name][pi])
                for name in all_returns if all_returns[name][pi] is not None]
        rets.sort(key=lambda x: x[1], reverse=True)
        top3 = rets[:3]
        medals = ["🥇", "🥈", "🥉"]
        items = ""
        for i, (n, v) in enumerate(top3):
            color = "#26a69a" if v >= 0 else "#ef5350"
            items += f'<span style="margin-right:18px;">{medals[i]} <b>{n}</b> <span style="color:{color};">{v:+.1f}%</span></span>'
        rankings_html += (f'<div style="margin-bottom:10px;">'
                          f'<span style="color:#90caf9;font-weight:700;min-width:40px;display:inline-block;">{label}</span>'
                          f' {items}</div>\n')

    since_th = '<th style="color:#ffd54f;border-left:2px solid #1a5fa8;">매입후</th>' if has_since else ''
    header_cells = "".join(f'<th>{lbl}</th>' for lbl in period_labels) + since_th

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason 수익률 비교</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Segoe UI',sans-serif; margin:0; padding:20px 30px; }}
  .page {{ max-width:1100px; margin:0 auto; }}
  h1 {{ color:#90caf9; font-size:1.6em; margin-bottom:4px; }}
  .ts {{ color:#757575; font-size:0.85em; margin-bottom:24px; }}
  table {{ width:100%; border-collapse:collapse; background:#16213e; border-radius:8px; overflow:hidden; margin-bottom:32px; }}
  th {{ background:#0f3460; color:#90caf9; padding:10px 14px; text-align:right; font-size:0.9em; }}
  th:first-child {{ text-align:left; padding-left:10px; }}
  td {{ padding:9px 14px; text-align:right; font-size:0.88em; border-bottom:1px solid #1e2a45; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover {{ background:rgba(144,202,249,0.06) !important; }}
  .section-title {{ color:#90caf9; font-size:1.1em; font-weight:700; margin-bottom:14px; border-left:3px solid #1a5fa8; padding-left:10px; }}
  .rankings {{ background:#16213e; border-radius:8px; padding:18px 20px; margin-bottom:32px; }}
  .note {{ color:#757575; font-size:0.8em; margin-top:8px; }}
</style>
</head>
<body>
<div class="page">
  <h1>Jason 수익률 비교</h1>
  <div class="ts">{timestamp}</div>

  <div class="section-title">자산별 수익률</div>
  <table>
    <thead><tr><th>자산</th>{header_cells}</tr></thead>
    <tbody>
{table_rows}
    </tbody>
  </table>

  <div class="section-title">기간별 수익률 순위 (TOP 3)</div>
  <div class="rankings">
{rankings_html}
  </div>

  <div class="note">※ YTD = 올해 1월 1일 기준 &nbsp;|&nbsp; ※ 야후 파이낸스 기준 (15분 지연)</div>
</div>

<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""
    return html


def main():
    print(f"\n{'━'*78}")
    print(f"  Jason 수익률 비교   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*78}")
    print("  데이터 수집 중 (약 10-20초)...\n")

    # 헤더
    period_labels = [p[0] for p in PERIODS]
    header = f"  {'자산':<14}" + "".join(f"  {lbl:>8}" for lbl in period_labels) + "  {'매입후':>8}"
    print(header)
    print(f"  {'─'*78}")

    # 수익률 수집 + 매입후 수익률
    all_returns = {}
    since_avg   = {}   # name → float|None

    # 현재 환율 1회만 조회
    try:
        _fx = yf.Ticker('USDKRW=X').history(period='2d')
        usdkrw_now = float(_fx['Close'].iloc[-1]) if not _fx.empty else 1450.0
    except Exception:
        usdkrw_now = 1450.0

    for name, ticker in ASSETS.items():
        row_returns = []
        for label, period in PERIODS:
            ret = get_return(ticker, period)
            row_returns.append(ret)
        all_returns[name] = row_returns

        # 매입 이후 수익률 (평단가 기반, 포트폴리오 종목만)
        avg_krw = AVG_PRICES.get(ticker)
        if avg_krw and avg_krw > 0:
            try:
                hist = yf.Ticker(ticker).history(period='2d')
                if not hist.empty:
                    curr = float(hist['Close'].dropna().iloc[-1])
                    is_krw = ticker.endswith('.KS') or ticker in ('^KS11', 'USDKRW=X')
                    curr_krw = curr if is_krw else curr * usdkrw_now
                    since_ret = (curr_krw - avg_krw) / avg_krw * 100
                    since_avg[name] = since_ret
                else:
                    since_avg[name] = None
            except Exception:
                since_avg[name] = None
        else:
            since_avg[name] = None

        # 터미널 출력
        line = f"  {name}"
        for ret in row_returns:
            line += f"  {fmt_ret(ret)}"
        sa = since_avg.get(name)
        line += f"  {fmt_ret(sa):>8}" if sa is not None else f"  {'–':>8}"
        print(line)

    print(f"  {'─'*78}")

    # 기간별 순위 (TOP 3)
    print(f"\n  기간별 수익률 순위")
    print(f"  {'─'*54}")
    for pi, (label, period) in enumerate(PERIODS):
        rets = [(name.strip(), all_returns[name][pi])
                for name in ASSETS if all_returns[name][pi] is not None]
        rets.sort(key=lambda x: x[1], reverse=True)
        top3 = rets[:3]
        top_str = '  '.join([f"{rank_label(i, len(rets))}{n}({v:+.1f}%)"
                              for i, (n, v) in enumerate(top3)])
        print(f"  {label:>4}: {top_str}")

    # 매입 이후 순위
    pf_rets = [(n.strip(), v) for n, v in since_avg.items() if v is not None]
    if pf_rets:
        pf_rets.sort(key=lambda x: x[1], reverse=True)
        top_str = '  '.join([f"{rank_label(i,len(pf_rets))}{n}({v:+.1f}%)"
                              for i, (n, v) in enumerate(pf_rets[:3])])
        print(f"  {'매입후':>4}: {top_str}")

    print(f"\n  ※ YTD = 올해 1월 1일 기준  ※ 매입후 = 평단가(KRW환산) 기준 수익률")
    print(f"  ※ 야후 파이낸스 기준 (15분 지연)\n")

    # HTML 저장 및 브라우저 열기
    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html_content  = generate_html(all_returns, since_avg, timestamp_str)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'returns_comparison.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"  HTML 저장: {html_path}")
    webbrowser.open(f'file://{html_path}')

if __name__ == '__main__':
    main()
