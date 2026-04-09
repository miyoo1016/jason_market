#!/usr/bin/env python3
"""차트 대시보드 - Jason Market
16개 종목 캔들차트 (5분봉/15분봉/1시간봉/일봉/주봉/월봉/연봉/최대) 브라우저에서 확인"""

import os, sys, json, webbrowser, threading
import yfinance as yf
from datetime import datetime

ALERT = '\033[38;5;203m'
RESET = '\033[0m'
EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

ASSETS = [
    ('Nasdaq QQQM', 'QQQM'),
    ('S&P500 SPY',  'SPY'),
    ('Google',      'GOOGL'),
    ('코스피',      '^KS11'),
    ('삼성전자',    '005930.KS'),
    ('Bitcoin',     'BTC-USD'),
    ('달러/원',     'USDKRW=X'),
    ('금(COMEX선물)', 'GC=F'),
    ('미국 10년물 국채', '^TNX'),
    ('브렌트유(ICE)', 'BZ=F'),
    ('WTI원유(NYMEX)', 'CL=F'),
    ('다우지수(CME선물)', 'YM=F'),
    ('S&P500(CME선물)', 'ES=F'),
    ('나스닥100(CME선물)', 'NQ=F'),
    ('러셀2000(CME선물)', 'RTY=F'),
    ('VIX(현물)',    '^VIX'),
]

# (interval_key, 표시명, yf_interval, period)
# '1y' 키는 월봉 데이터를 연봉으로 집계, 'max' 키는 3개월봉 최대 범위
INTERVALS = [
    ('5m',  '5분봉',   '5m',  '2d'),
    ('15m', '15분봉',  '15m', '5d'),
    ('1h',  '1시간봉', '1h',  '30d'),
    ('1d',  '일봉',    '1d',  '1y'),
    ('1wk', '주봉',    '1wk', '5y'),
    ('1mo', '월봉',    '1mo', '10y'),
    ('1y',  '연봉',    '1mo', 'max'),   # 월봉 fetch → 연도별 집계
    ('max', '최대',    '3mo', 'max'),   # 분기봉, 최대 기간
]

# ── 데이터 수집 ───────────────────────────────────────────

def aggregate_yearly(monthly_data):
    """월봉 리스트 → 연봉(연도별 OHLC 집계) 리스트"""
    from datetime import datetime as _dt
    yearly = {}
    for c in monthly_data:
        yr = _dt.fromtimestamp(c['time'], tz=__import__('datetime').timezone.utc).year
        if yr not in yearly:
            # 연도 첫 거래일 타임스탬프 (1월 1일 UTC 근사)
            yearly[yr] = {
                'time':  int(_dt(yr, 1, 1).timestamp()),
                'open':  c['open'],
                'high':  c['high'],
                'low':   c['low'],
                'close': c['close'],
            }
        else:
            yearly[yr]['high']  = max(yearly[yr]['high'],  c['high'])
            yearly[yr]['low']   = min(yearly[yr]['low'],   c['low'])
            yearly[yr]['close'] = c['close']
    result = sorted(yearly.values(), key=lambda x: x['time'])
    return result


def fetch_ohlcv(ticker, iv_key, yf_interval, period):
    try:
        hist = yf.Ticker(ticker).history(period=period, interval=yf_interval)
        if hist.empty:
            return []
        # 타임존 제거 (UTC 기준)
        if hist.index.tzinfo is not None:
            hist.index = hist.index.tz_convert('UTC').tz_localize(None)

        seen = set()
        data = []
        for ts, row in hist.iterrows():
            t = int(ts.timestamp())
            if t in seen:
                continue
            seen.add(t)
            o = round(float(row['Open']),  6)
            h = round(float(row['High']),  6)
            l = round(float(row['Low']),   6)
            c = round(float(row['Close']), 6)
            if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                continue
            # 잘못된 캔들 보정
            h = max(h, o, c)
            l = min(l, o, c)
            data.append({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})

        data.sort(key=lambda x: x['time'])

        # 연봉: 월봉 데이터를 연도별로 집계
        if iv_key == '1y':
            data = aggregate_yearly(data)

        return data
    except Exception:
        return []

def collect_all():
    """16개 종목 × 8개 봉종류 병렬 수집"""
    all_data = {ticker: {} for _, ticker in ASSETS}
    lock = threading.Lock()
    done = [0]

    def fetch_asset(name, ticker):
        for iv_key, _, yf_iv, period in INTERVALS:
            d = fetch_ohlcv(ticker, iv_key, yf_iv, period)
            with lock:
                all_data[ticker][iv_key] = d
        with lock:
            done[0] += 1
            print(f"  수집 중... {done[0]}/{len(ASSETS)}  ({name}){' '*20}", end='\r')

    threads = [threading.Thread(target=fetch_asset, args=(n, t)) for n, t in ASSETS]
    for th in threads: th.start()
    for th in threads: th.join()
    print(f"  수집 완료 ({len(ASSETS)}개 종목){' '*30}")
    return all_data

# ── HTML 생성 ─────────────────────────────────────────────

def generate_html(all_data, timestamp):
    assets_js = json.dumps(ASSETS, ensure_ascii=False)
    data_js   = json.dumps(all_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — 차트 대시보드</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#f4f4f4;color:#222;font-family:'Segoe UI',system-ui,sans-serif;}}
.header{{padding:13px 20px;background:#fff;border-bottom:1px solid #ddd;display:flex;justify-content:space-between;align-items:center;}}
.header h1{{font-size:15px;color:#111;letter-spacing:.3px;}}
.header .meta{{font-size:11px;color:#888;}}
.controls{{padding:9px 20px;background:#fff;border-bottom:1px solid #ddd;display:flex;gap:6px;align-items:center;}}
.controls .lbl{{font-size:11px;color:#888;margin-right:6px;}}
.btn{{padding:4px 13px;border:1px solid #ccc;background:#f0f0f0;color:#555;border-radius:3px;cursor:pointer;font-size:12px;transition:all .12s;}}
.btn:hover{{background:#e4e4e4;color:#222;}}
.btn.active{{background:#1a5fa8;border-color:#1a5fa8;color:#fff;font-weight:600;}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#ddd;}}
.chart-box{{background:#fff;padding:9px;}}
.chart-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:7px;}}
.chart-name{{font-size:11px;font-weight:600;color:#444;}}
.chart-info{{text-align:right;}}
.chart-price{{font-size:13px;font-weight:700;}}
.chart-pct{{font-size:10px;margin-top:1px;}}
.up{{color:#1a8a7a;}}.down{{color:#d32f2f;}}.neutral{{color:#888;}}
.chart-wrap{{position:relative;height:165px;}}
.no-data{{display:flex;align-items:center;justify-content:center;height:165px;color:#bbb;font-size:11px;}}
@media(max-width:1200px){{.grid{{grid-template-columns:repeat(3,1fr);}}}}
@media(max-width:800px){{.grid{{grid-template-columns:repeat(2,1fr);}}}}
</style>
</head>
<body>
<div class="header">
  <h1>Jason Market — 차트 대시보드</h1>
  <div class="meta">기준: {timestamp} &nbsp;|&nbsp; 야후 파이낸스 (15분 지연) &nbsp;|&nbsp; 브라우저에서 확대·스크롤 가능</div>
</div>
<div class="controls">
  <span class="lbl">봉 단위:</span>
  <button class="btn active" id="btn-5m"  onclick="sw('5m',this)">5분봉</button>
  <button class="btn"        id="btn-15m" onclick="sw('15m',this)">15분봉</button>
  <button class="btn"        id="btn-1h"  onclick="sw('1h',this)">1시간봉</button>
  <button class="btn"        id="btn-1d"  onclick="sw('1d',this)">일봉</button>
  <button class="btn"        id="btn-1wk" onclick="sw('1wk',this)">주봉</button>
  <button class="btn"        id="btn-1mo" onclick="sw('1mo',this)">월봉</button>
  <button class="btn"        id="btn-1y"  onclick="sw('1y',this)">연봉</button>
  <button class="btn"        id="btn-max" onclick="sw('max',this)">최대</button>
</div>
<div class="grid" id="grid"></div>

<script>
const ASSETS   = {assets_js};
const ALL_DATA = {data_js};
let CUR = '5m';
let CHARTS = [];

const FMT = {{
  'BTC-USD':   p=>'$'+p.toLocaleString('en',{{maximumFractionDigits:0}}),
  'USDKRW=X':  p=>'₩'+p.toLocaleString('en',{{minimumFractionDigits:1,maximumFractionDigits:1}}),
  '005930.KS': p=>'₩'+p.toLocaleString('en',{{maximumFractionDigits:0}}),
  'GC=F':      p=>'$'+p.toLocaleString('en',{{minimumFractionDigits:1,maximumFractionDigits:1}}),
  'BZ=F':      p=>'$'+p.toFixed(2),
  'CL=F':      p=>'$'+p.toFixed(2),
  '^TNX':      p=>p.toFixed(2)+'%',
  '^VIX':      p=>p.toFixed(2),
  '^KS11':     p=>p.toLocaleString('en',{{minimumFractionDigits:2,maximumFractionDigits:2}}),
  'YM=F':      p=>p.toLocaleString('en',{{minimumFractionDigits:1,maximumFractionDigits:1}}),
  'ES=F':      p=>p.toLocaleString('en',{{minimumFractionDigits:1,maximumFractionDigits:1}}),
  'NQ=F':      p=>p.toLocaleString('en',{{minimumFractionDigits:1,maximumFractionDigits:1}}),
  'RTY=F':     p=>p.toLocaleString('en',{{minimumFractionDigits:1,maximumFractionDigits:1}}),
  'QQQM':      p=>'$'+p.toFixed(2),
  'SPY':       p=>'$'+p.toFixed(2),
  'GOOGL':     p=>'$'+p.toFixed(2),
}};

function fp(price, ticker) {{
  if (!price && price !== 0) return 'N/A';
  const fn = FMT[ticker];
  return fn ? fn(price) : '$'+price.toFixed(2);
}}

function sw(iv, el) {{
  document.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  CUR = iv;
  render();
}}

function render() {{
  CHARTS.forEach(c=>c.remove());
  CHARTS = [];
  const grid = document.getElementById('grid');
  grid.innerHTML = '';

  ASSETS.forEach(([name, ticker]) => {{
    const data = (ALL_DATA[ticker]||{{}})[CUR]||[];
    let curr=null, pct=0;
    if (data.length>=2) {{
      curr = data[data.length-1].close;
      const prev = data[data.length-2].close;
      pct = (curr-prev)/prev*100;
    }} else if (data.length===1) {{
      curr = data[0].close;
    }}

    const priceStr = fp(curr, ticker);
    const pctStr   = (curr&&data.length>=2) ? (pct>=0?'+':'')+pct.toFixed(2)+'%' : '';
    const cls      = pct>0.001?'up':pct<-0.001?'down':'neutral';
    const sid      = 'c'+ticker.replace(/[^a-zA-Z0-9]/g,'_');

    const box = document.createElement('div');
    box.className = 'chart-box';
    box.innerHTML = `
      <div class="chart-header">
        <span class="chart-name">${{name}}</span>
        <div class="chart-info">
          <div class="chart-price ${{cls}}">${{priceStr}}</div>
          <div class="chart-pct  ${{cls}}">${{pctStr}}</div>
        </div>
      </div>
      <div class="chart-wrap" id="${{sid}}"></div>`;
    grid.appendChild(box);

    const wrap = document.getElementById(sid);

    if (data.length < 3) {{
      wrap.innerHTML = '<div class="no-data">데이터 없음 (장 마감 또는 미지원)</div>';
      return;
    }}

    const longTerm = ['1wk','1mo','1y','max'].includes(CUR);
    const chart = LightweightCharts.createChart(wrap, {{
      width:  wrap.offsetWidth || 300,
      height: 165,
      layout: {{ background:{{color:'#ffffff'}}, textColor:'#444' }},
      grid:   {{ vertLines:{{color:'#f0f0f0'}}, horzLines:{{color:'#f0f0f0'}} }},
      crosshair: {{ mode:1 }},
      rightPriceScale: {{ borderColor:'#ddd', scaleMargins:{{top:.08,bottom:.08}} }},
      timeScale: {{
        borderColor:'#ddd',
        timeVisible: !longTerm,
        secondsVisible: false,
      }},
      handleScroll: true,
      handleScale:  true,
    }});

    const cs = chart.addCandlestickSeries({{
      upColor:'#26a69a', downColor:'#ef5350',
      borderVisible: false,
      wickUpColor:'#26a69a', wickDownColor:'#ef5350',
    }});

    cs.setData(data);
    chart.timeScale().fitContent();
    CHARTS.push(chart);

    new ResizeObserver(()=>chart.applyOptions({{width:wrap.offsetWidth}})).observe(wrap);
  }});
}}

render();
</script>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""

# ── 메인 ─────────────────────────────────────────────────

def main():
    print(f"\n{'━'*55}")
    print(f"  Jason 차트 대시보드")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*55}")
    print("  16개 종목 × 8봉종류 데이터 수집 중...")
    print("  (병렬 처리, 약 30-50초 소요)\n")

    all_data = collect_all()

    ok = sum(
        1 for _, ticker in ASSETS
        if any(len(all_data[ticker].get(iv, [])) > 2 for iv,_,_,_ in INTERVALS)
    )
    print(f"\n  {ok}/{len(ASSETS)}개 종목 데이터 수집 완료")

    timestamp    = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_content = generate_html(all_data, timestamp)

    DIR       = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(DIR, 'chart_dashboard.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"  브라우저 오픈 중...")
    webbrowser.open(f'file://{html_path}')
    print(f"  완료!\n")
    print(f"  브라우저에서:")
    print(f"  - 5분봉 / 15분봉 / 1시간봉 / 일봉 / 주봉 / 월봉 / 연봉 / 최대 전환 가능")
    print(f"  - 마우스 스크롤로 확대/축소")
    print(f"  - 드래그로 좌우 이동\n")

if __name__ == '__main__':
    main()
