#!/usr/bin/env python3
"""지지/저항 레벨 분析 - Jason Market"""

import os, webbrowser, tempfile
import yfinance as yf
import numpy as np
from datetime import datetime
from xlsx_sync import load_portfolio as _load_pf

ALERT = '\033[38;5;203m'
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

def _asset_type(ticker):
    if ticker == 'BTC-USD':   return 'crypto'
    if ticker in ('GC=F', 'BZ=F', 'CL=F'): return 'commodity'
    if ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'): return 'futures'
    if ticker == '005930.KS' or ticker.endswith('.KS'): return 'krstock'
    if ticker == '^KS11':     return 'krindex'
    if ticker == 'USDKRW=X':  return 'fx'
    if ticker in ('^TNX', '^VIX'): return 'index'
    if ticker.startswith('^'): return 'index'
    return 'etf'

def _build_assets():
    assets = {}
    seen = set()
    try:
        holdings = _load_pf()
        for h in holdings:
            if h.get('is_cash') or h.get('ticker') == 'CASH':
                continue
            ticker = h['ticker']
            name   = h['name']
            if ticker == 'XLSX_PRICE':
                ticker = PROXY_MAP.get(name, 'SPY')
            elif ticker == 'GOLD_KRX':
                ticker = 'GC=F'
            if ticker and ticker not in seen:
                seen.add(ticker)
                assets[f'{name:<10}'] = (ticker, _asset_type(ticker))
    except Exception:
        pass

    market = {
        'Bitcoin    ': ('BTC-USD',   'crypto'),
        '금(COMEX선물) ': ('GC=F',      'commodity'),
        '브렌트유(ICE) ': ('BZ=F',      'commodity'),
        'WTI원유(NYMEX)': ('CL=F',      'commodity'),
        '다우지수(CME선물)': ('YM=F',      'futures'),
        'S&P500(CME선물)': ('ES=F',      'futures'),
        '나스닥100(CME선물)': ('NQ=F',      'futures'),
        '러셀2000(CME선물)': ('RTY=F',     'futures'),
        '코스피      ': ('^KS11',    'krindex'),
        '달러/원    ': ('USDKRW=X', 'fx'),
        '미국 10년물 국채': ('^TNX',     'index'),
        'VIX(현물)   ': ('^VIX',     'index'),
    }
    for k, (v, at) in market.items():
        if v not in seen:
            seen.add(v)
            assets[k] = (v, at)
    return assets

ASSETS = _build_assets()

def fmt_level(price, asset_type):
    if asset_type == 'crypto':   return f"${price:>12,.0f}"
    if asset_type == 'commodity':return f"${price:>12,.1f}"
    if asset_type == 'futures':  return f"{price:>12,.1f}"
    if asset_type == 'krstock':  return f"₩{price:>12,.0f}"
    if asset_type == 'fx':       return f"₩{price:>12,.1f}"
    if asset_type in ('index','krindex'): return f"{price:>12,.2f}"
    return f"${price:>12,.2f}"

def _mk_fmt(at):
    """HTML용 간결 포맷 함수 반환"""
    def fmt(v):
        if at == 'crypto':   return f"${v:,.0f}"
        if at == 'commodity':return f"${v:,.1f}"
        if at == 'futures':  return f"{v:,.1f}"
        if at == 'krstock':  return f"₩{v:,.0f}"
        if at == 'fx':       return f"₩{v:,.1f}"
        if at in ('index','krindex'): return f"{v:,.2f}"
        return f"${v:,.2f}"
    return fmt

def find_pivot_highs(high, window=5):
    pivots = []
    for i in range(window, len(high) - window):
        if high[i] == max(high[i - window: i + window + 1]):
            pivots.append(high[i])
    return pivots

def find_pivot_lows(low, window=5):
    pivots = []
    for i in range(window, len(low) - window):
        if low[i] == min(low[i - window: i + window + 1]):
            pivots.append(low[i])
    return pivots

def cluster_levels(levels, tolerance_pct=0.015):
    if not levels:
        return []
    levels = sorted(levels)
    clusters = [[levels[0]]]
    for price in levels[1:]:
        if (price - clusters[-1][-1]) / clusters[-1][-1] < tolerance_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return [np.mean(c) for c in clusters]

def analyze_sr(name, ticker, asset_type):
    try:
        # 1년 데이터 사용: 최근 급락 자산도 현재가 아래 지지 레벨 탐색 가능
        hist = yf.Ticker(ticker).history(period='1y')
        if hist.empty or len(hist) < 30:
            return None

        close  = list(hist['Close'])
        high   = list(hist['High'])
        low    = list(hist['Low'])
        curr   = close[-1]

        # 미국/글로벌 티커: 1분봉 prepost로 실시간 현재가 갱신
        if not (ticker.endswith('.KS') or ticker in ('^KS11',)):
            try:
                h1m = yf.Ticker(ticker).history(period='1d', interval='1m', prepost=True)
                if not h1m.empty:
                    curr = float(h1m['Close'].iloc[-1])
            except Exception:
                pass

        pivot_highs = find_pivot_highs(high, window=5)
        pivot_lows  = find_pivot_lows(low,  window=5)

        resistances = cluster_levels([p for p in pivot_highs if p > curr])
        supports    = cluster_levels([p for p in pivot_lows  if p < curr])

        # 1년 데이터 = 52주 고/저점
        high_52w = float(hist['High'].max())
        low_52w  = float(hist['Low'].min())

        return {
            'name':        name.strip(),
            'ticker':      ticker,
            'asset_type':  asset_type,
            'curr':        curr,
            'resistances': resistances[:3],
            'supports':    supports[-3:],
            'high_52w':    high_52w,
            'low_52w':     low_52w,
        }
    except Exception as e:
        print(f"  ⚠ {name.strip()} 오류: {e}")
        return None

def nearest_pct(curr, level):
    return (level - curr) / curr * 100

# ── SVG 가격 사다리 차트 ─────────────────────────────────────

def _svg_ladder(r):
    """52주 범위 위에 지지/저항/현재가를 시각화하는 SVG 반환."""
    curr = r['curr']
    h52  = r['high_52w']
    l52  = r['low_52w']
    at   = r['asset_type']
    fmt  = _mk_fmt(at)

    if (np.isnan(h52) or np.isnan(l52) or np.isnan(curr)
            or h52 == l52 or h52 < l52):
        return '<p style="color:#aaa;font-size:12px;padding:20px 0">52주 데이터 없음</p>'

    CH = 320   # 차트 높이
    CW = 34    # 가격 바 폭
    PL = 78    # 왼쪽 패딩 (%, 레이블)
    PR = 128   # 오른쪽 패딩 (가격)
    PT = 16    # 상단 여백
    PB = 16    # 하단 여백
    TW = PL + CW + PR
    TH = CH + PT + PB

    def py(price):
        ratio = (price - l52) / (h52 - l52)
        return PT + CH * (1.0 - ratio)

    items = []

    # 배경 그라데이션 (위=빨강, 아래=초록)
    items.append(
        '<defs>'
        '<linearGradient id="sr-grad" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#fdecea" stop-opacity="0.8"/>'
        '<stop offset="45%" stop-color="#f9f9f9"/>'
        '<stop offset="100%" stop-color="#e8f5e9" stop-opacity="0.8"/>'
        '</linearGradient></defs>'
    )
    items.append(
        f'<rect x="{PL}" y="{PT}" width="{CW}" height="{CH}" '
        f'fill="url(#sr-grad)" rx="3" stroke="#e0e0e0" stroke-width="1"/>'
    )

    # 현재가 이하 블루 오버레이
    yc = py(curr)
    fill_h = (PT + CH) - yc
    if fill_h > 0:
        items.append(
            f'<rect x="{PL}" y="{yc:.1f}" width="{CW}" height="{fill_h:.1f}" '
            f'fill="rgba(26,95,168,0.08)" rx="0"/>'
        )

    # 52주 고점 점선
    yh = py(h52)
    items.append(
        f'<line x1="{PL-4}" y1="{yh:.1f}" x2="{PL+CW+4}" y2="{yh:.1f}" '
        f'stroke="#ccc" stroke-width="1" stroke-dasharray="3,3"/>'
    )
    items.append(
        f'<text x="{PL-6}" y="{yh+4:.1f}" text-anchor="end" '
        f'font-size="9" fill="#bbb">52H</text>'
    )
    items.append(
        f'<text x="{PL+CW+6}" y="{yh+4:.1f}" font-size="9" fill="#bbb">{fmt(h52)}</text>'
    )

    # 52주 저점 점선
    yl = py(l52)
    items.append(
        f'<line x1="{PL-4}" y1="{yl:.1f}" x2="{PL+CW+4}" y2="{yl:.1f}" '
        f'stroke="#ccc" stroke-width="1" stroke-dasharray="3,3"/>'
    )
    items.append(
        f'<text x="{PL-6}" y="{yl+4:.1f}" text-anchor="end" '
        f'font-size="9" fill="#bbb">52L</text>'
    )
    items.append(
        f'<text x="{PL+CW+6}" y="{yl+4:.1f}" font-size="9" fill="#bbb">{fmt(l52)}</text>'
    )

    # 저항 레벨 (빨강)
    for lv in sorted(r['resistances']):
        yp  = py(lv)
        pct = nearest_pct(curr, lv)
        items.append(
            f'<line x1="{PL}" y1="{yp:.1f}" x2="{PL+CW}" y2="{yp:.1f}" '
            f'stroke="#ef5350" stroke-width="2.5"/>'
        )
        items.append(
            f'<circle cx="{PL}" cy="{yp:.1f}" r="4.5" fill="#ef5350" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<circle cx="{PL+CW}" cy="{yp:.1f}" r="4.5" fill="#ef5350" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<text x="{PL-8}" y="{yp+4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#ef5350" font-weight="700">+{pct:.1f}%</text>'
        )
        items.append(
            f'<text x="{PL+CW+8}" y="{yp+4:.1f}" font-size="10" fill="#c62828">{fmt(lv)}</text>'
        )

    # 현재가 (파랑, 굵게)
    items.append(
        f'<polygon points="{PL-3},{yc:.1f} {PL-13},{yc-6:.1f} {PL-13},{yc+6:.1f}" fill="#1a5fa8"/>'
    )
    items.append(
        f'<line x1="{PL-3}" y1="{yc:.1f}" x2="{PL+CW+3}" y2="{yc:.1f}" '
        f'stroke="#1a5fa8" stroke-width="3"/>'
    )
    items.append(
        f'<polygon points="{PL+CW+3},{yc:.1f} {PL+CW+13},{yc-6:.1f} {PL+CW+13},{yc+6:.1f}" '
        f'fill="#1a5fa8"/>'
    )
    items.append(
        f'<text x="{PL-16}" y="{yc+4:.1f}" text-anchor="end" '
        f'font-size="11" fill="#1a5fa8" font-weight="800">현재가</text>'
    )
    items.append(
        f'<text x="{PL+CW+16}" y="{yc+4:.1f}" '
        f'font-size="11" fill="#1a5fa8" font-weight="800">{fmt(curr)}</text>'
    )

    # 지지 레벨 (초록)
    for lv in sorted(r['supports'], reverse=True):
        yp  = py(lv)
        pct = nearest_pct(curr, lv)
        items.append(
            f'<line x1="{PL}" y1="{yp:.1f}" x2="{PL+CW}" y2="{yp:.1f}" '
            f'stroke="#26a69a" stroke-width="2.5"/>'
        )
        items.append(
            f'<circle cx="{PL}" cy="{yp:.1f}" r="4.5" fill="#26a69a" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<circle cx="{PL+CW}" cy="{yp:.1f}" r="4.5" fill="#26a69a" '
            f'stroke="white" stroke-width="1.5"/>'
        )
        items.append(
            f'<text x="{PL-8}" y="{yp+4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#26a69a" font-weight="700">{pct:.1f}%</text>'
        )
        items.append(
            f'<text x="{PL+CW+8}" y="{yp+4:.1f}" font-size="10" fill="#1a7a6a">{fmt(lv)}</text>'
        )

    return (f'<svg width="{TW}" height="{TH}" viewBox="0 0 {TW} {TH}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(items)}</svg>')


# ── HTML 생성 ─────────────────────────────────────────────

def generate_html(all_results, timestamp):
    cards = ''
    for r in all_results:
        if not r:
            continue
        curr   = r['curr']
        at     = r['asset_type']
        ticker = r['ticker']
        name   = r['name']
        h52    = r['high_52w']
        l52    = r['low_52w']
        fmt    = _mk_fmt(at)

        # 52주 위치 %
        pos_pct = 0.0
        if (h52 != l52 and not np.isnan(h52) and not np.isnan(l52)
                and not np.isnan(curr)):
            pos_pct = (curr - l52) / (h52 - l52) * 100
        pos_pct = max(0.0, min(100.0, pos_pct))

        high_pct = nearest_pct(curr, h52) if not np.isnan(h52) else 0
        low_pct  = nearest_pct(curr, l52) if not np.isnan(l52) else 0

        # 저항 레벨 행
        res_rows = ''
        for lv in sorted(r['resistances'], reverse=True):
            pct = nearest_pct(curr, lv)
            bar_w = min(abs(pct) * 3, 100)
            res_rows += (
                f'<tr>'
                f'<td class="lv-price rc">{fmt(lv)}</td>'
                f'<td class="lv-pct rc">+{pct:.2f}%</td>'
                f'<td class="lv-bar"><div class="bar-r" style="width:{bar_w:.0f}%"></div></td>'
                f'</tr>'
            )
        if not res_rows:
            res_rows = '<tr><td colspan="3" class="empty">저항 레벨 없음 (52주 고점 근처)</td></tr>'

        # 지지 레벨 행
        sup_rows = ''
        for lv in sorted(r['supports'], reverse=True):
            pct = nearest_pct(curr, lv)
            bar_w = min(abs(pct) * 3, 100)
            sup_rows += (
                f'<tr>'
                f'<td class="lv-price sc">{fmt(lv)}</td>'
                f'<td class="lv-pct sc">{pct:.2f}%</td>'
                f'<td class="lv-bar"><div class="bar-s" style="width:{bar_w:.0f}%"></div></td>'
                f'</tr>'
            )
        if not sup_rows:
            sup_rows = '<tr><td colspan="3" class="empty">지지 레벨 없음 (52주 저점 근처)</td></tr>'

        svg = _svg_ladder(r)

        cards += f"""
<div class="card">
  <div class="chdr">
    <div class="chdr-l">
      <span class="ctick">{ticker}</span>
      <span class="cname">{name}</span>
    </div>
    <div class="chdr-r">
      <span class="cprice">{fmt(curr)}</span>
      <span class="cpos">52주 {pos_pct:.0f}% 위치</span>
    </div>
  </div>
  <div class="cbody">

    <!-- SVG 가격 사다리 -->
    <div class="svg-col">
      <div class="col-title">📈 가격 레벨 차트</div>
      {svg}
      <div class="legend">
        <span class="rc">● 저항</span>
        <span class="blue">● 현재가</span>
        <span class="sc">● 지지</span>
        <span style="color:#ccc">-- 52주 범위</span>
      </div>
    </div>

    <!-- 수치 상세 -->
    <div class="detail-col">

      <div class="sec-block">
        <div class="sec-hdr rh">🔴 저항 레벨 (상승 저항)</div>
        <table class="lv-tbl">
          <thead><tr><th>가격</th><th>거리</th><th>강도</th></tr></thead>
          <tbody>{res_rows}</tbody>
        </table>
      </div>

      <div class="curr-band">▶ 현재가 &nbsp;<strong>{fmt(curr)}</strong></div>

      <div class="sec-block">
        <div class="sec-hdr sh">🟢 지지 레벨 (하락 지지)</div>
        <table class="lv-tbl">
          <thead><tr><th>가격</th><th>거리</th><th>강도</th></tr></thead>
          <tbody>{sup_rows}</tbody>
        </table>
      </div>

      <!-- 52주 통계 -->
      <div class="w52">
        <div class="w52-item">
          <div class="w52-lbl">52주 고점</div>
          <div class="w52-val rc">{fmt(h52)}</div>
          <div class="w52-sub rc">{high_pct:+.1f}%</div>
        </div>
        <div class="w52-item">
          <div class="w52-lbl">현재가 위치</div>
          <div class="w52-val blue">{pos_pct:.0f}%</div>
          <div class="w52-track"><div class="w52-dot" style="left:{pos_pct:.1f}%"></div></div>
        </div>
        <div class="w52-item">
          <div class="w52-lbl">52주 저점</div>
          <div class="w52-val sc">{fmt(l52)}</div>
          <div class="w52-sub sc">{low_pct:+.1f}%</div>
        </div>
      </div>

    </div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason Market — 지지/저항 레벨</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#f0f2f5;color:#222;font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;}}

.top-hdr{{padding:14px 24px;background:#1a1a2e;color:#fff;}}
.top-hdr h1{{font-size:17px;font-weight:700;}}
.top-hdr .sub{{font-size:11px;color:#aaa;margin-top:4px;}}

.page{{max-width:1400px;margin:0 auto;padding:18px 16px;
       display:grid;grid-template-columns:repeat(auto-fill,minmax(600px,1fr));gap:16px;}}

.card{{background:#fff;border:1px solid #ddd;border-radius:8px;overflow:hidden;
       box-shadow:0 1px 5px rgba(0,0,0,.07);}}

/* 카드 헤더 */
.chdr{{display:flex;justify-content:space-between;align-items:center;
       padding:12px 18px;background:#fafafa;border-bottom:1px solid #eee;}}
.chdr-l{{display:flex;align-items:baseline;gap:8px;}}
.ctick{{font-size:21px;font-weight:800;color:#1a1a2e;}}
.cname{{font-size:12px;color:#999;}}
.chdr-r{{text-align:right;}}
.cprice{{font-size:18px;font-weight:700;color:#1a5fa8;display:block;}}
.cpos{{font-size:10px;color:#aaa;}}

/* 카드 바디 */
.cbody{{display:flex;}}
.svg-col{{padding:14px 12px 12px 10px;border-right:1px solid #f0f0f0;flex-shrink:0;}}
.col-title{{font-size:10px;font-weight:600;color:#aaa;text-transform:uppercase;
            letter-spacing:.4px;margin-bottom:8px;}}
.legend{{display:flex;gap:10px;font-size:10px;margin-top:8px;flex-wrap:wrap;}}

/* 수치 패널 */
.detail-col{{flex:1;padding:12px 16px;display:flex;flex-direction:column;gap:8px;}}
.sec-block{{}}
.sec-hdr{{font-size:11px;font-weight:700;padding:5px 8px;border-radius:4px;margin-bottom:4px;}}
.rh{{background:#fff0ef;color:#c62828;}}
.sh{{background:#edf9f6;color:#1a7a6a;}}

/* 레벨 테이블 */
.lv-tbl{{width:100%;border-collapse:collapse;font-size:12px;}}
.lv-tbl th{{color:#bbb;font-weight:500;padding:3px 8px;border-bottom:1px solid #f0f0f0;font-size:10px;}}
.lv-tbl th:last-child{{width:70px;}}
.lv-tbl td{{padding:4px 8px;border-bottom:1px solid #f8f8f8;vertical-align:middle;}}
.lv-tbl td.lv-price{{font-family:monospace;font-size:12px;font-weight:600;}}
.lv-tbl td.lv-pct{{font-weight:700;width:64px;font-size:12px;}}
.lv-tbl td.lv-bar{{width:70px;padding:6px 8px;}}
.bar-r{{height:6px;background:#ef5350;border-radius:3px;min-width:2px;}}
.bar-s{{height:6px;background:#26a69a;border-radius:3px;min-width:2px;}}
.lv-tbl td.empty{{color:#bbb;font-style:italic;font-size:11px;}}

.rc{{color:#ef5350;}}.sc{{color:#26a69a;}}.blue{{color:#1a5fa8;}}

/* 현재가 구분선 */
.curr-band{{text-align:center;padding:6px 8px;background:#eef4ff;
            border-radius:4px;font-size:12px;color:#1a5fa8;font-weight:600;}}

/* 52주 통계 */
.w52{{display:flex;gap:8px;background:#f8f8f8;border-radius:6px;padding:10px;margin-top:4px;}}
.w52-item{{flex:1;text-align:center;}}
.w52-lbl{{font-size:9px;color:#aaa;text-transform:uppercase;margin-bottom:3px;}}
.w52-val{{font-size:13px;font-weight:700;}}
.w52-sub{{font-size:10px;font-weight:600;margin-top:1px;}}
.w52-track{{height:5px;background:#ddd;border-radius:3px;position:relative;margin-top:6px;}}
.w52-dot{{position:absolute;top:-3px;width:11px;height:11px;background:#1a5fa8;
           border-radius:50%;transform:translateX(-50%);border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.2);}}
</style>
</head>
<body>
<div class="top-hdr">
  <h1>Jason Market — 지지/저항 레벨 분석</h1>
  <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 6개월 피봇 레벨 · 52주 고/저점 범위</div>
</div>
<div class="page">{cards}</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""


def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*60}")
    print(f"  Jason 지지/저항 레벨   {timestamp}")
    print(f"{'━'*60}")
    print("  데이터 수집 중 (약 10-20초)...\n")

    all_results = []
    for name, (ticker, asset_type) in ASSETS.items():
        r = analyze_sr(name, ticker, asset_type)
        if not r:
            continue
        all_results.append(r)

        curr = r['curr']
        print(f"  {r['name']}  현재가: {fmt_level(curr, asset_type)}")
        print(f"  {'─'*50}")
        print(f"    [저항 레벨]")
        if r['resistances']:
            for lv in reversed(r['resistances']):
                pct = nearest_pct(curr, lv)
                print(f"    {fmt_level(lv, asset_type)}  → +{pct:.1f}%")
        else:
            print(f"    저항 레벨 없음 (52주 신고점 부근)")
        print(f"  {'─'*50}")
        print(f"    ▶ 현재가  {fmt_level(curr, asset_type)}")
        print(f"  {'─'*50}")
        print(f"    [지지 레벨]")
        if r['supports']:
            for lv in reversed(r['supports']):
                pct = nearest_pct(curr, lv)
                print(f"    {fmt_level(lv, asset_type)}  → {pct:.1f}%")
        else:
            print(f"    지지 레벨 없음 (52주 신저점 부근)")

        h52 = r['high_52w']
        l52 = r['low_52w']
        high_pct = nearest_pct(curr, h52)
        low_pct  = nearest_pct(curr, l52)
        print(f"\n  52주 고점: {fmt_level(h52, asset_type)}  ({high_pct:+.1f}%)")
        print(f"  52주 저점: {fmt_level(l52, asset_type)}  ({low_pct:+.1f}%)")

        if (h52 != l52 and not np.isnan(h52) and not np.isnan(l52)
                and not np.isnan(curr)):
            pos_pct = (curr - l52) / (h52 - l52) * 100
            pos_pct = max(0.0, min(100.0, pos_pct))
            bar_len = 30
            filled  = int(pos_pct / 100 * bar_len)
            bar = '[' + '█' * filled + '░' * (bar_len - filled) + ']'
            print(f"  52주 위치: {bar} {pos_pct:.0f}%")
        print()

    # HTML 저장 및 브라우저 오픈
    html = generate_html(all_results, timestamp)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='support_resistance_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")

if __name__ == '__main__':
    main()
