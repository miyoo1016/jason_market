#!/usr/bin/env python3
"""섹터 흐름 분석 - Jason Market
S&P500 11개 섹터 ETF 자금 흐름 분석"""

import os
import webbrowser
import tempfile
import threading
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, date

ALERT = '\033[38;5;203m'
RESET = '\033[0m'
EXTREME = ['극도공포', '극도탐욕', '강력매도', '강력매수', '매우높음', '즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

SECTORS = [
    ('XLK',  '기술 Technology'),
    ('XLC',  '커뮤니케이션 Communication'),
    ('XLY',  '임의소비재 Consumer Disc.'),
    ('XLF',  '금융 Financials'),
    ('XLV',  '헬스케어 Healthcare'),
    ('XLI',  '산업재 Industrials'),
    ('XLE',  '에너지 Energy'),
    ('XLB',  '소재 Materials'),
    ('XLP',  '필수소비재 Consumer Staples'),
    ('XLRE', '부동산 Real Estate'),
    ('XLU',  '유틸리티 Utilities'),
    ('SPY',  'S&P500 (기준)'),
]

# (key, label, yf_period)
PERIODS = [
    ('1d',  '1일',  '5d'),
    ('1w',  '1주',  '10d'),
    ('1m',  '1달',  '1mo'),
    ('3m',  '3달',  '3mo'),
    ('ytd', 'YTD',  'ytd'),
]

def calc_returns_from_hist(close):
    """Close 시리즈에서 모든 기간 수익률 계산."""
    close = close.dropna()
    if len(close) < 2:
        return {pk: None for pk, _, _ in PERIODS}
    curr = float(close.iloc[-1])
    res  = {}

    def pct(prev_val):
        if prev_val == 0 or np.isnan(prev_val) or np.isnan(curr):
            return None
        return (curr - prev_val) / prev_val * 100

    # 1d: 직전 거래일 대비
    res['1d'] = pct(float(close.iloc[-2])) if len(close) >= 2 else None

    # 1w: 약 5 거래일 전
    res['1w'] = pct(float(close.iloc[-6])) if len(close) >= 6 else None

    # 1m: 약 21 거래일 전
    res['1m'] = pct(float(close.iloc[-22])) if len(close) >= 22 else None

    # 3m: 약 63 거래일 전
    res['3m'] = pct(float(close.iloc[-64])) if len(close) >= 64 else None

    # YTD: 올해 1월 1일 이후 첫 거래일
    try:
        tz   = close.index.tz
        ytd_start = pd.Timestamp(f'{close.index[-1].year}-01-01', tz=tz)
        ytd  = close[close.index >= ytd_start]
        res['ytd'] = pct(float(ytd.iloc[0])) if len(ytd) >= 2 else None
    except Exception:
        res['ytd'] = None

    return res

def fetch_ticker_returns(ticker):
    """티커 1년 데이터 1회 요청 → 모든 기간 수익률 반환."""
    try:
        hist = yf.Ticker(ticker).history(period='1y')
        if hist is None or hist.empty:
            return {pk: None for pk, _, _ in PERIODS}
        return calc_returns_from_hist(hist['Close'])
    except Exception:
        return {pk: None for pk, _, _ in PERIODS}

def collect_all():
    """모든 섹터를 병렬로 1회 요청. 반환: {ticker: {period_key: pct}}"""
    results = {}
    lock    = threading.Lock()

    def fetch(ticker):
        val = fetch_ticker_returns(ticker)
        with lock:
            results[ticker] = val

    threads = []
    for ticker, _ in SECTORS:
        t = threading.Thread(target=fetch, args=(ticker,), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results

def fmt_pct(val):
    if val is None:
        return '  N/A  '
    return f'{val:+.2f}%'

def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*60}")
    print(f"  Jason 섹터 흐름 분석   {timestamp}")
    print(f"{'━'*60}")
    print("  데이터 수집 중 (약 15초)...")

    data = collect_all()

    # 1일 수익률 기준 정렬 (SPY 제외하고 정렬, SPY는 마지막에 추가)
    sector_list = [(t, n) for t, n in SECTORS if t != 'SPY']
    sector_list.sort(key=lambda x: (data[x[0]].get('1d') or -999), reverse=True)
    # SPY 마지막
    sector_list.append(('SPY', 'S&P500 (기준)'))

    print(f"\n  [ 섹터 흐름 - 1일 기준 정렬 ]")
    print(f"  {'─'*75}")
    print(f"  {'섹터':<24} {'1일':>8} {'1주':>8} {'1달':>8} {'3달':>8} {'YTD':>8}  순위")
    print(f"  {'─'*75}")

    rank = 1
    for ticker, name in sector_list:
        d = data[ticker]
        r1d  = d.get('1d')
        r1w  = d.get('1w')
        r1m  = d.get('1m')
        r3m  = d.get('3m')
        rytd = d.get('ytd')
        rank_str = f'↑{rank}위' if ticker != 'SPY' else '← 기준'
        label = f'{name[:18]} {ticker}'
        line = (f"  {label:<24} {fmt_pct(r1d):>8} {fmt_pct(r1w):>8} "
                f"{fmt_pct(r1m):>8} {fmt_pct(r3m):>8} {fmt_pct(rytd):>8}  {rank_str}")
        print(line)
        if ticker != 'SPY':
            rank += 1
    print()

    # ── HTML 생성 ──────────────────────────────────────────────
    html = generate_html(data, timestamp)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='sector_flow_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")

def generate_html(data, timestamp):
    # 기간별 섹터 정렬 데이터 준비
    period_data = {}
    for pk, plabel, _ in PERIODS:
        sorted_sectors = sorted(
            [(t, n, data[t].get(pk)) for t, n in SECTORS if t != 'SPY'],
            key=lambda x: (x[2] if x[2] is not None else -999),
            reverse=True
        )
        spy_val = data['SPY'].get(pk)
        period_data[pk] = {'sectors': sorted_sectors, 'spy': spy_val, 'label': plabel}

    def build_chart_data(pk):
        d = period_data[pk]
        sectors = d['sectors']
        labels  = [f"{n[:12]} ({t})" for t, n, _ in sectors]
        values  = [round(v, 2) if v is not None else 0 for _, _, v in sectors]
        colors  = ['rgba(46,204,113,0.75)' if v >= 0 else 'rgba(231,76,60,0.75)'
                   for v in values]
        spy_val = d['spy']
        return labels, values, colors, spy_val

    # 첫 번째 기간(1d) 데이터로 초기 차트 생성
    labels_json_all = {}
    values_json_all = {}
    colors_json_all = {}
    spy_json_all    = {}
    for pk, _, _ in PERIODS:
        lbs, vals, cols, spy = build_chart_data(pk)
        import json
        labels_json_all[pk] = json.dumps(lbs, ensure_ascii=False)
        values_json_all[pk] = json.dumps(vals)
        colors_json_all[pk] = json.dumps(cols)
        spy_json_all[pk]    = spy if spy is not None else 0

    # 상세 테이블 행
    def build_table_rows():
        rows = []
        for ticker, name in SECTORS:
            d = data[ticker]
            is_spy = ticker == 'SPY'
            r1d = d.get('1d')
            r1w = d.get('1w')
            r1m = d.get('1m')
            r3m = d.get('3m')
            ryt = d.get('ytd')
            def cell(v):
                if v is None:
                    return '<td style="color:#bbb">N/A</td>'
                c = '#2ecc71' if v >= 0 else '#e74c3c'
                return f'<td style="color:{c};font-weight:600">{v:+.2f}%</td>'
            spy_style = ' style="background:#eef4ff"' if is_spy else ''
            rows.append(f"""
      <tr{spy_style}>
        <td><strong>{ticker}</strong></td>
        <td>{name}</td>
        {cell(r1d)}{cell(r1w)}{cell(r1m)}{cell(r3m)}{cell(ryt)}
      </tr>""")
        return '\n'.join(rows)

    table_rows = build_table_rows()

    import json as _json

    # JavaScript 데이터 블록
    js_data_blocks = []
    for pk, plabel, _ in PERIODS:
        js_data_blocks.append(
            f'  periodData["{pk}"] = {{'
            f'labels:{labels_json_all[pk]},'
            f'values:{values_json_all[pk]},'
            f'colors:{colors_json_all[pk]},'
            f'spy:{spy_json_all[pk]}}};'
        )
    js_data = '\n'.join(js_data_blocks)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jason Market — 섹터 흐름 분석</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f4f4f4; color: #333; }}
    .header {{ background: #1a1a2e; color: #fff; padding: 24px 32px; }}
    .header h1 {{ font-size: 22px; font-weight: 700; }}
    .header .subtitle {{ color: #aaa; font-size: 13px; margin-top: 4px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
    .tab-btn {{ padding: 9px 20px; border: none; border-radius: 6px;
               cursor: pointer; font-size: 14px; font-weight: 600;
               background: #ddd; color: #555; transition: all 0.2s; }}
    .tab-btn.active {{ background: #1a1a2e; color: #fff; }}
    .tab-btn:hover:not(.active) {{ background: #ccc; }}
    .card {{ background: #fff; border-radius: 10px; padding: 20px;
             box-shadow: 0 2px 8px rgba(0,0,0,0.07); margin-bottom: 20px; }}
    .card-title {{ font-size: 16px; font-weight: 700; margin-bottom: 16px; }}
    .chart-wrap {{ position: relative; height: 400px; }}
    .spy-note {{ font-size: 12px; color: #3498db; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #f8f8f8; padding: 10px 12px; text-align: center;
          font-size: 12px; color: #666; font-weight: 600;
          border-bottom: 2px solid #e0e0e0; }}
    th:nth-child(1), th:nth-child(2) {{ text-align: left; }}
    td {{ padding: 9px 12px; border-bottom: 1px solid #f0f0f0;
          font-size: 13px; text-align: center; }}
    td:nth-child(1), td:nth-child(2) {{ text-align: left; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #fafafa; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Jason Market — 섹터 흐름 분석</h1>
    <div class="subtitle">S&P500 11개 섹터 ETF 수익률 &nbsp;|&nbsp; 업데이트: {timestamp}</div>
  </div>
  <div class="container">
    <div class="tabs">
      <button class="tab-btn active" onclick="switchPeriod('1d',this)">1일</button>
      <button class="tab-btn" onclick="switchPeriod('1w',this)">1주</button>
      <button class="tab-btn" onclick="switchPeriod('1m',this)">1달</button>
      <button class="tab-btn" onclick="switchPeriod('3m',this)">3달</button>
      <button class="tab-btn" onclick="switchPeriod('ytd',this)">YTD</button>
    </div>

    <div class="card">
      <div class="card-title" id="chart-title">섹터 수익률 — 1일</div>
      <div class="chart-wrap">
        <canvas id="sectorChart"></canvas>
      </div>
      <div class="spy-note" id="spy-note">SPY 기준: N/A</div>
    </div>

    <div class="card">
      <div class="card-title">전체 기간 상세 테이블</div>
      <table>
        <thead>
          <tr>
            <th>티커</th>
            <th>섹터명</th>
            <th>1일</th>
            <th>1주</th>
            <th>1달</th>
            <th>3달</th>
            <th>YTD</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>
  </div>

  <script>
    const periodData = {{}};
{js_data}

    const ctx = document.getElementById('sectorChart').getContext('2d');
    let chart = null;

    function renderChart(pk) {{
      const d = periodData[pk];
      const periodLabels = {{'1d':'1일','1w':'1주','1m':'1달','3m':'3달','ytd':'YTD'}};
      document.getElementById('chart-title').textContent = '섹터 수익률 — ' + (periodLabels[pk]||pk);
      document.getElementById('spy-note').textContent = 'SPY 기준: ' + (d.spy >= 0 ? '+' : '') + d.spy.toFixed(2) + '%';

      const spyLine = {{
        type: 'line',
        label: 'SPY 기준',
        data: Array(d.labels.length).fill(d.spy),
        borderColor: '#3498db',
        borderDash: [6,4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        order: 0,
      }};

      const barData = {{
        type: 'bar',
        label: '수익률 (%)',
        data: d.values,
        backgroundColor: d.colors,
        borderRadius: 4,
        order: 1,
      }};

      if (chart) chart.destroy();
      chart = new Chart(ctx, {{
        type: 'bar',
        data: {{ labels: d.labels, datasets: [spyLine, barData] }},
        options: {{
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: true, position: 'top' }},
            tooltip: {{
              callbacks: {{
                label: ctx => ' ' + (ctx.parsed.x >= 0 ? '+' : '') + ctx.parsed.x.toFixed(2) + '%'
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{ color: '#eee' }},
              ticks: {{ callback: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%' }}
            }},
            y: {{ grid: {{ display: false }} }}
          }}
        }}
      }});
    }}

    function switchPeriod(pk, btn) {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderChart(pk);
    }}

    renderChart('1d');
  </script>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""
    return html

if __name__ == '__main__':
    main()
