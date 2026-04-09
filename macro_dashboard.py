#!/usr/bin/env python3
"""거시경제 지표 대시보드 - Jason Market
금리, 달러, 환율, 유가 등 큰 그림 + HTML 차트 출력"""

import os, json, webbrowser
import yfinance as yf
from datetime import datetime

ALERT = '\033[38;5;203m'
CYAN  = '\033[36m'
AMBER = '\033[38;5;214m'
RESET = '\033[0m'
BOLD  = '\033[1m'

DIR      = os.path.dirname(os.path.abspath(__file__))
HTML_OUT = os.path.join(DIR, 'macro_dashboard.html')

# (표시명, 티커, 단위, 설명, 카테고리)
MACRO_ITEMS = [
    ('미국 10년 금리',      '^TNX',     '%',   '높을수록 성장주↓ 달러↑',      '금리'),
    ('미국 2년 금리',       '^IRX',     '%',   '연준 기준금리 방향 선행',      '금리'),
    ('달러인덱스 DXY',      'DX-Y.NYB', 'pt',  '높을수록 신흥국↓ 금↓ 원자재↓', '달러/환율'),
    ('달러/원 환율',        'USDKRW=X', '원',  '높을수록 수입물가↑',           '달러/환율'),
    ('공포지수 VIX',        '^VIX',     'pt',  '25↑주의 / 30↑공포',            '변동성'),
    ('금 COMEX',            'GC=F',     'USD', '안전자산, 달러와 역상관',       '원자재'),
    ('브렌트유 ICE',        'BZ=F',     'USD', '글로벌 원유 기준가',            '원자재'),
    ('WTI 원유 NYMEX',      'CL=F',     'USD', '미국 원유 기준 / 인플레 지표',  '원자재'),
    ('구리 COMEX',          'HG=F',     'USD', '경기 선행 지표 (닥터 쿠퍼)',    '원자재'),
    ('다우 선물 CME',       'YM=F',     'pt',  '미국 우량주 30종 선물',         '미국 선물'),
    ('S&P500 선물',         'ES=F',     'pt',  'S&P500 선물 (24H 거래)',         '미국 선물'),
    ('나스닥100 선물',      'NQ=F',     'pt',  '기술주 나스닥100 선물',          '미국 선물'),
    ('러셀2000 선물',       'RTY=F',    'pt',  '미국 중소형주 선물',             '미국 선물'),
    ('S&P500',              '^GSPC',    'pt',  '미국 대형주 벤치마크',           '주요 지수'),
    ('나스닥100',           '^NDX',     'pt',  '기술주 중심',                    '주요 지수'),
    ('코스피',              '^KS11',    'pt',  '한국 대표 지수',                  '주요 지수'),
    ('비트코인',            'BTC-USD',  'USD', '대표 암호화폐 / 위험선호 지표',  '암호화폐'),
]

CHART_ASSETS = [
    ('^TNX',     '미국 10년 금리 (%)',   '#e65100', False),
    ('DX-Y.NYB', '달러인덱스 DXY',       '#6a1b9a', False),
    ('USDKRW=X', '달러/원 환율',         '#1565c0', False),
    ('^VIX',     'VIX 공포지수',         '#c62828', False),
    ('GC=F',     '금 (USD)',              '#f9a825', False),
    ('BZ=F',     '브렌트유 (USD)',        '#4e342e', False),
    ('^GSPC',    'S&P500',               '#00838f', False),
    ('^NDX',     '나스닥100',            '#1976d2', False),
    ('^KS11',    '코스피',               '#2e7d32', False),
    ('BTC-USD',  '비트코인 (USD)',        '#ff6f00', False),
]

CATEGORIES_ORDER = ['금리', '달러/환율', '변동성', '원자재', '미국 선물', '주요 지수', '암호화폐']

# ── 데이터 수집 ────────────────────────────────────────────────

def get_daily(ticker):
    try:
        hist = yf.Ticker(ticker).history(period='5d')
        if hist.empty or len(hist) < 2:
            return None, None, None
        curr = float(hist['Close'].iloc[-1])
        prev = float(hist['Close'].iloc[-2])
        pct  = (curr - prev) / prev * 100
        return curr, prev, pct
    except:
        return None, None, None

def get_history_1y(ticker):
    try:
        hist = yf.Ticker(ticker).history(period='1y', interval='1d')
        if hist.empty:
            return [], []
        dates  = [str(d.date()) for d in hist.index]
        closes = [round(float(c), 4) for c in hist['Close']]
        return dates, closes
    except:
        return [], []

def get_yearly_pct(ticker):
    try:
        hist = yf.Ticker(ticker).history(period='1y')
        if hist.empty or len(hist) < 2:
            return None
        s = float(hist['Close'].iloc[0])
        e = float(hist['Close'].iloc[-1])
        return (e - s) / s * 100
    except:
        return None

# ── 해석 ──────────────────────────────────────────────────────

def interpret(ticker, curr, pct):
    if ticker == '^VIX':
        if curr > 30: return ('극도 공포', 'danger')
        if curr > 25: return ('공포',      'warn')
        if curr > 20: return ('주의',      'warn')
        return ('안정', 'good')
    if ticker == '^TNX':
        if curr > 4.5: return ('고금리 주의', 'danger')
        if curr > 4.0: return ('금리 부담',   'warn')
        return ('안정', 'good')
    if ticker == 'DX-Y.NYB':
        if curr > 105: return ('달러 강세', 'warn')
        if curr > 100: return ('달러 보통', 'neutral')
        return ('달러 약세', 'good')
    if ticker == 'USDKRW=X':
        if curr > 1400: return ('원화 약세', 'warn')
        if curr > 1300: return ('주의',      'neutral')
        return ('원화 강세', 'good')
    if ticker == 'HG=F':
        if pct and pct > 1:  return ('경기 기대↑', 'good')
        if pct and pct < -1: return ('경기 우려↑', 'warn')
        return ('중립', 'neutral')
    if ticker == 'BTC-USD':
        if pct and pct > 3:  return ('강한 상승', 'good')
        if pct and pct < -3: return ('강한 하락', 'danger')
        return ('보합', 'neutral')
    if ticker in ('BZ=F', 'CL=F'):
        if curr > 90: return ('고유가 경고', 'danger')
        if curr > 75: return ('보통',        'neutral')
        return ('저유가', 'good')
    if ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F', '^GSPC', '^NDX', '^KS11'):
        if pct and pct > 1:  return ('강세', 'good')
        if pct and pct < -1: return ('약세', 'danger')
        return ('보합', 'neutral')
    return ('—', 'neutral')

# ── 값 포맷 ───────────────────────────────────────────────────

def fmt_val(val, unit):
    if val is None: return 'N/A'
    if unit == '%':  return f"{val:.2f}%"
    if unit == '원': return f"₩{val:,.1f}"
    if val >= 10000: return f"{val:,.0f}"
    if val >= 1000:  return f"{val:,.1f}"
    return f"{val:.3f}"

# ── 터미널 출력 ────────────────────────────────────────────────

def print_terminal(data_by_cat):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*68}")
    print(f"  {BOLD}Jason 거시경제 대시보드{RESET}   {now}")
    print(f"{'━'*68}")

    for cat in CATEGORIES_ORDER:
        items = data_by_cat.get(cat, [])
        if not items:
            continue
        print(f"\n  {CYAN}{cat}{RESET}")
        print(f"  {'─'*64}")
        print(f"  {'지표':<20} {'현재값':>10} {'일간':>9}  {'신호':<12} {'설명'}")
        print(f"  {'─'*64}")
        for row in items:
            name, curr, pct, unit, desc, signal, ticker = row
            val_str   = fmt_val(curr, unit) if curr else 'N/A'
            pct_str   = f"{pct:>+7.2f}%" if pct is not None else '    N/A'
            sig_label = interpret(ticker, curr, pct)[0] if curr else '—'
            color = ALERT if signal == 'danger' else (AMBER if signal == 'warn' else '')
            reset = RESET if color else ''
            print(f"  {name:<20} {val_str:>10} {pct_str}  {color}{sig_label:<12}{reset} {desc}")

    print(f"\n{'━'*68}")
    print(f"  ※ 야후 파이낸스 기준 (15분 지연) | HTML 차트: macro_dashboard.html\n")

# ── HTML 생성 ─────────────────────────────────────────────────

def build_html(data_by_cat, chart_data, now_str):

    # ── 상단 요약 카드 (핵심 6개) ──────────────────────────────
    summary_tickers = ['^TNX', 'USDKRW=X', '^VIX', 'GC=F', 'BZ=F', '^GSPC']
    summary_labels  = ['10년 금리', '달러/원', 'VIX', '금', '브렌트유', 'S&P500']
    summary_cards_html = ''

    ticker_lookup = {}
    for cat_items in data_by_cat.values():
        for row in cat_items:
            name, curr, pct, unit, desc, signal, ticker = row
            ticker_lookup[ticker] = row

    for i, tk in enumerate(summary_tickers):
        row = ticker_lookup.get(tk)
        if not row:
            continue
        name, curr, pct, unit, desc, signal, _ = row
        val_str = fmt_val(curr, unit) if curr else 'N/A'
        pct_str = f"{pct:+.2f}%" if pct is not None else 'N/A'
        arrow   = '▲' if (pct or 0) >= 0 else '▼'
        clr_map = {'good': '#00838f', 'warn': '#e65100', 'danger': '#c62828', 'neutral': '#546e7a'}
        color   = clr_map.get(signal, '#546e7a')
        pct_color = '#00838f' if (pct or 0) >= 0 else '#c62828'
        summary_cards_html += f"""
        <div class="sum-card">
          <div class="sum-label">{summary_labels[i]}</div>
          <div class="sum-val">{val_str}</div>
          <div class="sum-pct" style="color:{pct_color}">{arrow} {pct_str}</div>
          <div class="sum-signal" style="background:{color}">{name if signal != 'neutral' else '—'}</div>
        </div>"""

    # ── 카테고리 테이블 ────────────────────────────────────────
    tables_html = ''
    cat_icons = {
        '금리': '📈', '달러/환율': '💵', '변동성': '⚡',
        '원자재': '🛢', '미국 선물': '🇺🇸', '주요 지수': '📊', '암호화폐': '🪙'
    }
    for cat in CATEGORIES_ORDER:
        items = data_by_cat.get(cat, [])
        if not items:
            continue
        icon  = cat_icons.get(cat, '')
        rows  = ''
        for row in items:
            name, curr, pct, unit, desc, signal, ticker = row
            val_str = fmt_val(curr, unit) if curr else 'N/A'
            pct_str = f"{pct:+.2f}%" if pct is not None else 'N/A'
            arrow   = '▲' if (pct or 0) >= 0 else '▼'
            pct_color = '#00838f' if (pct or 0) >= 0 else '#c62828'
            sig_map = {'good': ('#e8f5e9', '#2e7d32', '●'), 'warn': ('#fff3e0', '#e65100', '●'),
                       'danger': ('#ffebee', '#c62828', '●'), 'neutral': ('#f5f6f8', '#546e7a', '○')}
            bg, fc, dot = sig_map.get(signal, sig_map['neutral'])
            sig_label, _ = interpret(ticker, curr, pct) if curr else ('—', 'neutral')
            rows += f"""
            <tr>
              <td class="td-name">{name}</td>
              <td class="td-val">{val_str}</td>
              <td class="td-pct" style="color:{pct_color}">{arrow} {pct_str}</td>
              <td><span class="badge" style="background:{bg};color:{fc}">{dot} {sig_label}</span></td>
              <td class="td-desc">{desc}</td>
            </tr>"""

        tables_html += f"""
        <div class="cat-block">
          <div class="cat-title">{icon} {cat}</div>
          <table class="macro-table">
            <thead>
              <tr><th>지표</th><th>현재값</th><th>일간 등락</th><th>신호</th><th>설명</th></tr>
            </thead>
            <tbody>{rows}
            </tbody>
          </table>
        </div>"""

    # ── 1년 차트 JS 데이터 ─────────────────────────────────────
    charts_js = ''
    charts_html = ''
    for i, (ticker, label, color, _) in enumerate(CHART_ASSETS):
        dates, closes = chart_data.get(ticker, ([], []))
        if not dates:
            continue
        cid = f"chart_{i}"
        js_dates  = json.dumps(dates)
        js_closes = json.dumps(closes)

        # 등락 색상 결정
        trend_color = color
        if closes and len(closes) >= 2:
            trend_color = '#00838f' if closes[-1] >= closes[0] else '#c62828'

        charts_js += f"""
        (function() {{
          var ctx = document.getElementById('{cid}').getContext('2d');
          var dates = {js_dates};
          var data  = {js_closes};
          new Chart(ctx, {{
            type: 'line',
            data: {{
              labels: dates,
              datasets: [{{
                label: '{label}',
                data: data,
                borderColor: '{color}',
                backgroundColor: '{color}18',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.3
              }}]
            }},
            options: {{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                  mode: 'index', intersect: false,
                  callbacks: {{
                    label: function(ctx) {{
                      return ' ' + ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString();
                    }}
                  }}
                }}
              }},
              scales: {{
                x: {{
                  ticks: {{ maxTicksLimit: 6, font: {{ size: 10 }} }},
                  grid: {{ color: '#f0f0f0' }}
                }},
                y: {{
                  ticks: {{ font: {{ size: 10 }},
                    callback: function(v) {{ return v.toLocaleString(); }}
                  }},
                  grid: {{ color: '#f0f0f0' }}
                }}
              }}
            }}
          }});
        }})();"""

        # 차트 카드
        last_val = f"{closes[-1]:,.2f}" if closes else 'N/A'
        yy_row   = ticker_lookup.get(ticker)
        yy_pct   = ''
        if yy_row:
            _, curr_v, pct_v, unit_v, _, _, _ = yy_row
            if pct_v is not None:
                pct_color = '#00838f' if pct_v >= 0 else '#c62828'
                arrow_v   = '▲' if pct_v >= 0 else '▼'
                yy_pct    = f'<span style="color:{pct_color};font-size:12px">{arrow_v} {pct_v:+.2f}%</span>'

        charts_html += f"""
        <div class="chart-card">
          <div class="chart-title">{label} <span class="chart-cur">{last_val}</span> {yy_pct}</div>
          <div class="chart-wrap"><canvas id="{cid}"></canvas></div>
        </div>"""

    # ── 1년 수익률 바 차트 ─────────────────────────────────────
    yearly_items = [
        ('^GSPC', 'S&P500'), ('^NDX', '나스닥100'), ('^KS11', '코스피'),
        ('GC=F',  '금'), ('BZ=F', '브렌트유'), ('CL=F', 'WTI유가'),
        ('USDKRW=X', '달러/원'), ('BTC-USD', '비트코인'),
    ]
    y_labels, y_values, y_colors = [], [], []
    for tk, lb in yearly_items:
        row = ticker_lookup.get(tk)
        if not row:
            continue
        dates_h, closes_h = chart_data.get(tk, ([], []))
        if closes_h and len(closes_h) >= 2:
            yp = (closes_h[-1] - closes_h[0]) / closes_h[0] * 100
            y_labels.append(lb)
            y_values.append(round(yp, 2))
            y_colors.append('#00838f' if yp >= 0 else '#c62828')

    yearly_bar_js = f"""
    (function() {{
      var ctx = document.getElementById('yearlyBar').getContext('2d');
      new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: {json.dumps(y_labels)},
          datasets: [{{
            data: {json.dumps(y_values)},
            backgroundColor: {json.dumps(y_colors)},
            borderRadius: 6,
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                label: function(ctx) {{ return ' ' + ctx.parsed.y.toFixed(2) + '%'; }}
              }}
            }}
          }},
          scales: {{
            x: {{ ticks: {{ font: {{ size: 12 }} }} }},
            y: {{
              ticks: {{
                callback: function(v) {{ return v + '%'; }},
                font: {{ size: 11 }}
              }},
              grid: {{ color: '#f0f0f0' }}
            }}
          }}
        }}
      }});
    }})();"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>거시경제 대시보드 — Jason Market</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Apple SD Gothic Neo', sans-serif;
          background: #f5f6f8; color: #1a1a2e; font-size: 14px; }}

  /* ── 헤더 ── */
  .header {{ background: #fff; border-bottom: 3px solid #00838f;
             padding: 18px 28px; display: flex; align-items: center;
             justify-content: space-between; }}
  .header h1 {{ font-size: 20px; font-weight: 700; color: #00838f; }}
  .header .ts {{ font-size: 12px; color: #888; }}

  /* ── 요약 카드 ── */
  .summary {{ display: grid; grid-template-columns: repeat(6, 1fr);
              gap: 12px; padding: 20px 28px 0; }}
  .sum-card {{ background: #fff; border-radius: 10px; padding: 14px 16px;
               box-shadow: 0 1px 4px rgba(0,0,0,.06); text-align: center; }}
  .sum-label {{ font-size: 11px; color: #888; margin-bottom: 6px; font-weight: 600;
                text-transform: uppercase; letter-spacing: .5px; }}
  .sum-val   {{ font-size: 18px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }}
  .sum-pct   {{ font-size: 12px; font-weight: 600; margin-bottom: 6px; }}
  .sum-signal{{ display: inline-block; padding: 2px 10px; border-radius: 20px;
                font-size: 11px; font-weight: 700; color: #fff; }}

  /* ── 컨텐츠 영역 ── */
  .main {{ padding: 20px 28px; }}
  .section-title {{ font-size: 16px; font-weight: 700; color: #1a1a2e;
                    margin: 28px 0 14px; border-left: 4px solid #00838f;
                    padding-left: 10px; }}

  /* ── 카테고리 그리드 ── */
  .cat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .cat-block {{ background: #fff; border-radius: 10px; overflow: hidden;
                box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .cat-title {{ padding: 10px 16px; font-size: 13px; font-weight: 700;
                background: #f8f9fa; border-bottom: 1px solid #e8e8e8;
                color: #37474f; }}
  .macro-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .macro-table thead tr {{ background: #fafbfc; }}
  .macro-table th {{ padding: 8px 12px; text-align: left; font-size: 11px;
                     color: #90a4ae; font-weight: 600; border-bottom: 1px solid #ebebeb; }}
  .macro-table tbody tr:hover {{ background: #fafbfc; }}
  .macro-table td {{ padding: 9px 12px; border-bottom: 1px solid #f2f2f2; }}
  .td-name {{ font-weight: 600; color: #263238; }}
  .td-val  {{ font-weight: 700; text-align: right; font-family: 'SF Mono', monospace; }}
  .td-pct  {{ text-align: right; font-weight: 600; font-size: 12px; font-family: 'SF Mono', monospace; }}
  .td-desc {{ color: #90a4ae; font-size: 11px; }}
  .badge   {{ display: inline-block; padding: 2px 8px; border-radius: 20px;
              font-size: 11px; font-weight: 700; }}

  /* ── 차트 그리드 ── */
  .chart-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }}
  .chart-card {{ background: #fff; border-radius: 10px; padding: 16px 20px;
                 box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .chart-title {{ font-size: 13px; font-weight: 700; color: #263238;
                  margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }}
  .chart-cur {{ font-family: 'SF Mono', monospace; color: #00838f; font-weight: 700; }}
  .chart-wrap {{ height: 160px; position: relative; }}

  /* ── 1년 수익률 ── */
  .yearly-card {{ background: #fff; border-radius: 10px; padding: 20px;
                  box-shadow: 0 1px 4px rgba(0,0,0,.06); margin-top: 16px; }}
  .yearly-wrap {{ height: 200px; position: relative; }}

  /* ── 푸터 ── */
  .footer {{ text-align: center; padding: 20px; color: #aaa; font-size: 11px; }}

  @media (max-width: 900px) {{
    .summary   {{ grid-template-columns: repeat(3,1fr); }}
    .cat-grid  {{ grid-template-columns: 1fr; }}
    .chart-grid{{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 거시경제 대시보드</h1>
  <div class="ts">Jason Market &nbsp;|&nbsp; {now_str} &nbsp;|&nbsp; 야후 파이낸스 기준 (15분 지연)</div>
</div>

<!-- 요약 카드 -->
<div class="summary">
  {summary_cards_html}
</div>

<div class="main">

  <!-- 카테고리 테이블 -->
  <div class="section-title">📋 지표 현황</div>
  <div class="cat-grid">
    {tables_html}
  </div>

  <!-- 1년 라인 차트 -->
  <div class="section-title">📈 1년 가격 추이</div>
  <div class="chart-grid">
    {charts_html}
  </div>

  <!-- 1년 수익률 바 차트 -->
  <div class="section-title">🏆 1년 수익률 비교</div>
  <div class="yearly-card">
    <div class="yearly-wrap"><canvas id="yearlyBar"></canvas></div>
  </div>

</div>

<div class="footer">※ 데이터 출처: Yahoo Finance &nbsp;|&nbsp; Jason Market 거시경제 대시보드</div>

<script>
{charts_js}
{yearly_bar_js}
</script>
</body>
</html>"""

    return html

# ── 메인 ──────────────────────────────────────────────────────

def main():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*60}")
    print(f"  {BOLD}Jason 거시경제 대시보드{RESET}   {now_str}")
    print(f"{'━'*60}")
    print("  데이터 수집 중... (30~40초 소요)\n")

    ticker_map = {item[1]: item for item in MACRO_ITEMS}
    data_by_cat = {cat: [] for cat in CATEGORIES_ORDER}
    ticker_rows = {}

    # 일간 데이터
    for name, ticker, unit, desc, cat in MACRO_ITEMS:
        curr, prev, pct = get_daily(ticker)
        sig_label, signal = interpret(ticker, curr, pct) if curr else ('—', 'neutral')
        row = (name, curr, pct, unit, desc, signal, ticker)
        data_by_cat[cat].append(row)
        ticker_rows[ticker] = row

    # 1년 히스토리 (차트용)
    print("  차트 데이터 수집 중...")
    chart_data = {}
    for ticker, label, color, _ in CHART_ASSETS:
        dates, closes = get_history_1y(ticker)
        chart_data[ticker] = (dates, closes)

    # 터미널 출력
    print_terminal(data_by_cat)

    # HTML 생성
    html = build_html(data_by_cat, chart_data, now_str)
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"  HTML 저장: {HTML_OUT}")
    webbrowser.open(f'file://{HTML_OUT}')

if __name__ == '__main__':
    main()
