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
    """포트폴리오 보유 종목 + 시장 지표 합쳐서 ASSETS 딕셔너리 반환"""
    assets = {}
    seen_tickers = set()

    # 1. 포트폴리오 보유 종목 먼저 추가
    try:
        holdings = _load_pf()
        for h in holdings:
            if h.get('is_cash') or h.get('ticker') == 'CASH':
                continue
            ticker = h['ticker']
            name = h['name']
            if ticker == 'XLSX_PRICE':
                ticker = PROXY_MAP.get(name, 'SPY')
            elif ticker == 'GOLD_KRX':
                ticker = 'GC=F'
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                assets[f'{name:<10}'] = ticker
    except Exception:
        pass

    # 2. 기존 시장 지표 추가 (중복 제외)
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
        if v not in seen_tickers:
            seen_tickers.add(v)
            assets[k] = v
    return assets

ASSETS = _build_assets()

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

def generate_html(all_returns, timestamp):
    period_labels = [p[0] for p in PERIODS]

    # Build table rows
    table_rows = ""
    for name, rets in all_returns.items():
        # Compute heatmap background based on average of non-None values
        valid = [r for r in rets if r is not None]
        avg = sum(valid) / len(valid) if valid else 0
        if avg > 10:
            row_bg = "rgba(38,166,154,0.18)"
        elif avg > 3:
            row_bg = "rgba(38,166,154,0.10)"
        elif avg < -10:
            row_bg = "rgba(239,83,80,0.18)"
        elif avg < -3:
            row_bg = "rgba(239,83,80,0.10)"
        else:
            row_bg = "transparent"

        cells = ""
        for ret in rets:
            if ret is None:
                cells += f'<td style="color:#757575;">N/A</td>'
            elif ret > 0:
                cells += f'<td style="color:#26a69a;font-weight:600;">{ret:+.1f}%</td>'
            else:
                cells += f'<td style="color:#ef5350;font-weight:600;">{ret:+.1f}%</td>'
        table_rows += f'<tr style="background:{row_bg};"><td style="text-align:left;padding-left:10px;">{name.strip()}</td>{cells}</tr>\n'

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
        rankings_html += f'<div style="margin-bottom:10px;"><span style="color:#90caf9;font-weight:700;min-width:40px;display:inline-block;">{label}</span> {items}</div>\n'

    header_cells = "".join(f'<th>{lbl}</th>' for lbl in period_labels)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason 수익률 비교</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Segoe UI',sans-serif; margin:0; padding:20px 30px; }}
  .page {{ max-width:960px; margin:0 auto; }}
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
    print(f"\n{'━'*72}")
    print(f"  Jason 수익률 비교   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*72}")
    print("  데이터 수집 중 (약 10-20초)...\n")

    # 헤더
    period_labels = [p[0] for p in PERIODS]
    header = f"  {'자산':<14}"
    for label in period_labels:
        header += f"  {label:>8}"
    print(header)
    print(f"  {'─'*68}")

    # 수익률 수집
    all_returns = {}
    for name, ticker in ASSETS.items():
        row_returns = []
        for label, period in PERIODS:
            ret = get_return(ticker, period)
            row_returns.append(ret)
        all_returns[name] = row_returns

        # 출력
        line = f"  {name}"
        for ret in row_returns:
            line += f"  {fmt_ret(ret)}"
        print(line)

    print(f"  {'─'*68}")

    # 기간별 순위 (TOP 3)
    print(f"\n  기간별 수익률 순위")
    print(f"  {'─'*50}")
    for pi, (label, period) in enumerate(PERIODS):
        rets = [(name.strip(), all_returns[name][pi])
                for name in ASSETS if all_returns[name][pi] is not None]
        rets.sort(key=lambda x: x[1], reverse=True)
        top3 = rets[:3]

        top_str = '  '.join([f"{rank_label(i, len(rets))}{n}({v:+.1f}%)"
                              for i, (n, v) in enumerate(top3)])
        print(f"  {label:>4}: {top_str}")

    print(f"\n  ※ YTD = 올해 1월 1일 기준")
    print(f"  ※ 야후 파이낸스 기준 (15분 지연)\n")

    # HTML 저장 및 브라우저 열기
    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html_content = generate_html(all_returns, timestamp_str)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'returns_comparison.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"  HTML 저장: {html_path}")
    webbrowser.open(f'file://{html_path}')

if __name__ == '__main__':
    main()
