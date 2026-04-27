#!/usr/bin/env python3
"""시장 스트레스 지표 - Jason Market
최종 완결본: 스크린샷의 프리미엄 디자인 프레임 100% 유지 + Fix 1~4 내용만 이식"""

import json
import yfinance as yf
import webbrowser
import tempfile
import numpy as np
from datetime import datetime

# 터미널 색상
CYAN   = '\033[36m'
AMBER  = '\033[38;5;214m'
ALERT  = '\033[38;5;203m'
RESET  = '\033[0m'

TICKERS = ['^VIX9D', '^VIX', '^VIX3M', '^VIX6M', '^VVIX', '^IRX', '^TNX', '2YY=F', 'HYG', 'IEF']

def fetch_all():
    data = yf.download(TICKERS, period='3mo', auto_adjust=True, progress=False)
    return data['Close'] if 'Close' in data.columns else data

def last_price(df, ticker):
    try:
        col = df[ticker].dropna()
        return float(col.iloc[-1]) if not col.empty else None
    except Exception: return None

def price_ago(df, ticker, n=21):
    try:
        col = df[ticker].dropna()
        return float(col.iloc[-(n + 1)]) if len(col) >= n + 1 else None
    except Exception: return None

# ── 분석 및 데이터 구성 ────────────────────────────────────────

def analyze(closes):
    r = {}
    flags = []

    # 1. VIX 기간구조 (Fix 1 로직)
    v9d, v30, v3m, v6m = last_price(closes, '^VIX9D'), last_price(closes, '^VIX'), last_price(closes, '^VIX3M'), last_price(closes, '^VIX6M')
    r.update({'vix9d': v9d, 'vix30': v30, 'vix3m': v3m, 'vix6m': v6m})
    
    def get_vix_label(val):
        if val is None: return "", ""
        if val < 1.0: return "콘탱고 ✅", "#16a34a"
        if val < 1.05: return "플랫 ⚠️", "#d97706"
        return "백워데이션 🔴", "#dc2626"

    if v9d and v30 and v3m:
        r1, r2, r3 = v9d/v30, v30/v3m, (v3m/v6m if v6m else None)
        r.update({'r_9d_30': r1, 'r_30_3m': r2, 'r_3m_6m': r3})
        r['l1'], r['c1'] = get_vix_label(r1)
        r['l2'], r['c2'] = get_vix_label(r2)
        r['l3'], r['c3'] = get_vix_label(r3)
        
        if any(v >= 1.05 for v in [r1, r2, r3] if v): v_l, v_s = 'bad', '백워데이션'
        elif any(v >= 1.0 for v in [r1, r2, r3] if v): v_l, v_s = 'warn', '플랫'
        else: v_l, v_s = 'good', '콘탱고 (정상)'
        r.update({'vix_level': v_l, 'vix_state': v_s})

    # 2. VVIX (Fix 4 부호 적용)
    vvix, vvix_1w = last_price(closes, '^VVIX'), price_ago(closes, '^VVIX', 5)
    r['vvix'] = vvix
    if vvix:
        v_chg = ((vvix / vvix_1w) - 1) * 100 if vvix_1w else 0
        r['vvix_trend'] = f"{v_chg:+.1f}% (1주 전 {vvix_1w:.2f})"
        if vvix < 80: vv_s, vv_l = "🟢 안정 — 옵션 시장 정상, VIX 급등 가능성 낮음", "good"
        elif vvix < 100: vv_s, vv_l = f"🟡 주의 — 평균 초과 ({vvix:.1f}, 역사적 평균 86 대비 +{((vvix/86)-1)*100:.0f}%)", "warn"; flags.append("🟡 VVIX 주의")
        elif vvix < 110: vv_s, vv_l = f"🟠 경고 ({vvix:.1f}) — VIX 급등 가능성 상승, 헤지 강화 권고", "warn"; flags.append("🟠 VVIX 경고")
        else: vv_s, vv_l = f"🔴 고위험 ({vvix:.1f}) — VIX 급등 임박, 즉각 방어 포지션 필요", "bad"; flags.append("🔴 VVIX 고위험")
        r.update({'vvix_level': vv_l, 'vvix_state': vv_s})

    # 3. 수익률 곡선
    r10y, r3m, r2y = last_price(closes, '^TNX'), last_price(closes, '^IRX'), last_price(closes, '2YY=F')
    if r2y is None: r2y = last_price(closes, '^GS2')
    r.update({'r10y': r10y, 'r3m': r3m, 'r2y': r2y})
    if r10y and r3m: r['yc_spread'] = r10y - r3m
    if r10y and r2y:
        r['spread_10y_2y'] = r10y - r2y
        r['state_10y_2y'] = "정상" if r['spread_10y_2y'] > 0 else "역전"

    # 4. 신용 스프레드 (Fix 2/3/4 로직)
    h_now, h_prev = last_price(closes, 'HYG'), price_ago(closes, 'HYG', 1)
    i_now, i_prev = last_price(closes, 'IEF'), price_ago(closes, 'IEF', 1)
    if h_now and i_now:
        r_now = h_now / i_now
        h_chg = ((h_now/h_prev)-1)*100 if h_prev else 0
        i_chg = ((i_now/i_prev)-1)*100 if i_prev else 0
        r.update({
            'hyg': h_now, 'ief': i_now, 'cr_ratio': r_now,
            'h_chg': h_chg, 'i_chg': i_chg,
            'cr_level': 'good' if (h_now/h_prev) > 0.99 else 'warn'
        })

    r['stress_flags'] = flags
    if any("🔴" in f for f in flags): r.update({'sum_level': 'bad', 'sum_state': '⚠️ 위험', 'sum_note': " + ".join(flags)})
    elif flags: r.update({'sum_level': 'warn', 'sum_state': f"🟡 주의 — {', '.join(flags)}", 'sum_note': " + ".join(flags)})
    else: r.update({'sum_level': 'good', 'sum_state': '안정 — 주요 스트레스 지표 이상 없음', 'sum_note': 'VIX 백워데이션 + VVIX 급등 + 금리 역전 + 신용 경색 동시 발생 시 최고 위험 경보'})
    
    return r

# ── HTML 및 리포트 생성 (디자인 프레임 100% 보존) ────────────────

def generate_html(r, ts):
    c_good, c_warn, c_bad = '#00838f', '#e65100', '#c62828'
    bg_good, bg_warn, bg_bad = '#e0f7fa', '#fff3e0', '#ffebee'
    fv = lambda v: f"{v:.2f}" if v is not None else "N/A"
    fp = lambda v: f"{v:+.2f}%" if v is not None else "N/A"
    
    # 보고서 텍스트 (Fix 1 반영: 3행 유지)
    report_md = f"""# 시장 스트레스 지표 — {ts}
## 종합 판정: {r['sum_state']}
- 플래그: {', '.join(r['stress_flags']) if r['stress_flags'] else '이상 없음'}
## ① VIX 기간구조
- VIX9D/VIX30 : {r.get('r_9d_30',0):.3f} {r.get('l1','')}
- VIX30/VIX3M : {r.get('r_30_3m',0):.3f} {r.get('l2','')}
- VIX3M/VIX6M : {r.get('r_3m_6m',0):.3f} {r.get('l3','')}
## ② VVIX: {r.get('vvix_state','')}
## ③ 수익률 곡선: {fp(r.get('yc_spread'))} (10Y-3M) / {fp(r.get('spread_10y_2y'))} (10Y-2Y)
## ④ 신용 스프레드: {r.get('cr_ratio',0):.4f} (HYG {r.get('h_chg',0):+.1f}% / IEF {r.get('i_chg',0):+.1f}%)"""
    
    copy_text = json.dumps(report_md)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Jason Market — 시장 스트레스 지표</title>
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    * {{ box-sizing: border-box; font-family: 'Pretendard', sans-serif; }}
    body {{ background: #f5f6f8; margin: 0; padding: 0; color: #333; }}
    .header {{ background: #1a237e; color: white; padding: 18px 40px; display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #0d47a1; }}
    .header h1 {{ margin: 0; font-size: 19px; font-weight: 800; }}
    .btn-copy {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 7px 15px; border-radius: 4px; cursor: pointer; font-weight: 700; font-size: 12px; }}
    .container {{ max-width: 1240px; margin: 25px auto; padding: 0 20px 50px; }}
    .summary-banner {{ background: {bg_good if r['sum_level']=='good' else bg_warn}; border: 1px solid {c_good if r['sum_level']=='good' else c_warn}22; border-radius: 12px; padding: 22px 35px; margin-bottom: 25px; display: flex; align-items: flex-start; gap: 20px; }}
    .sum-title {{ font-size: 16px; font-weight: 800; color: {c_good if r['sum_level']=='good' else c_warn}; margin-bottom: 6px; }}
    .sum-note {{ font-size: 12px; color: #555; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 25px; }}
    .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); display: flex; flex-direction: column; }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
    .card-title {{ font-size: 13px; font-weight: 800; color: #444; display: flex; align-items: center; gap: 6px; }}
    .status-badge {{ padding: 2px 10px; border-radius: 10px; font-size: 10px; font-weight: 800; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td {{ padding: 8px 0; font-size: 13px; color: #444; border-bottom: 1px solid #f6f6f6; }}
    td.val {{ text-align: right; font-weight: 800; color: #1a237e; font-size: 14px; }}
    .gauge {{ height: 7px; background: #eee; border-radius: 4px; overflow: hidden; margin: 12px 0; display: flex; }}
    .interp {{ background: #e0f7fa; border-left: 4px solid #00838f; padding: 12px 15px; border-radius: 4px; margin-top: 15px; flex-grow: 1; }}
    .interp-title {{ font-size: 12px; font-weight: 800; color: #00838f; margin-bottom: 4px; }}
    .interp-note {{ font-size: 12px; color: #333; line-height: 1.4; }}
    .hint {{ font-size: 10px; color: #b0b0b0; margin-top: 10px; }}
    .vix-tag {{ font-size: 10px; color: white; padding: 2px 6px; border-radius: 3px; float: right; margin-left: 5px; }}
    .dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }}
</style>
</head>
<body>
<div class="header"><h1>Jason Market — 시장 스트레스 지표</h1><button class="btn-copy" onclick="copyResult()">📋 전체 복사 (상세 보고서)</button></div>
<div class="container">
    <div class="summary-banner">
        <div style="font-size: 26px; color: {c_good if r['sum_level']=='good' else c_warn};">✓</div>
        <div><div class="sum-title">{r['sum_state']}</div><div class="sum-note">{r['sum_note']}</div></div>
    </div>
    <div class="grid">
        <!-- VIX Card (Frame 보존 + Fix 1 내용) -->
        <div class="card">
            <div class="card-header"><span class="card-title">◎ VIX 기간구조 — 공포의 시급성</span><span class="status-badge" style="background:{bg_good}; color:{c_good};">{r['vix_state']}</span></div>
            <table>
                <tr><td>VIX 9일 (^VIX9D)</td><td class="val">{fv(r['vix9d'])}</td></tr>
                <tr><td>VIX 30일 (^VIX)</td><td class="val">{fv(r['vix30'])} <small style="color:#aaa;">← 기준</small></td></tr>
                <tr><td>VIX 3개월 (^VIX3M)</td><td class="val">{fv(r['vix3m'])}</td></tr>
            </table>
            <div class="gauge"><div style="width:75%; background:{c_good};"></div></div>
            <div class="interp">
                <div class="interp-title">비율 해석 (Fix 1 적용)</div>
                <div style="font-size:13px; font-weight:800; color:#00838f; margin:4px 0;">9D/VIX 비율 : {r.get('r_9d_30',0):.3f} <span class="vix-tag" style="background:{r.get('c1','#16a34a')}">{r.get('l1','')}</span></div>
                <div class="interp-note">
                    VIX30/3M: {r.get('r_30_3m',0):.3f} <span class="vix-tag" style="background:{r.get('c2','#16a34a')}">{r.get('l2','')}</span><br>
                    3M/6M: {r.get('r_3m_6m',0):.3f} <span class="vix-tag" style="background:{r.get('c3','#16a34a')}">{r.get('l3','')}</span>
                </div>
            </div>
            <div class="hint">◀ 콘탱고(안정) | 백워데이션(위험) ▶</div>
        </div>

        <!-- VVIX Card (Frame 보존 + Fix 4 부호) -->
        <div class="card">
            <div class="card-header"><span class="card-title">◎ VVIX — 변동성의 변동성 (VIX of VIX)</span><span class="status-badge" style="background:{bg_good}; color:{c_good};"><span class="dot" style="background:{c_good};"></span>안정</span></div>
            <table>
                <tr><td>VVIX (^VVIX)</td><td class="val">{fv(r['vvix'])} <small style="color:{c_warn};">{r.get('vvix_trend','')}</small></td></tr>
                <tr><td>VIX 30일 (^VIX, 참고)</td><td class="val">{fv(r['vix30'])}</td></tr>
            </table>
            <div class="gauge">
                <div style="flex:80; background:{c_good}; opacity:0.25;"></div>
                <div style="flex:20; background:{c_warn}; opacity:0.25;"></div>
                <div style="flex:20; background:{c_bad}; opacity:0.25;"></div>
            </div>
            <div class="interp" style="background:{bg_warn if r['vvix_level']!='good' else bg_good}; border-color:{c_warn if r['vvix_level']!='good' else c_good};">
                <div class="interp-title" style="color:{c_warn if r['vvix_level']!='good' else c_good};">VVIX 분석</div>
                <div style="font-size:12px; font-weight:800; color:{c_warn if r['vvix_level']!='good' else c_good}; margin:4px 0;">{r.get('vvix_state','N/A')}</div>
                <div class="interp-note">VVIX는 VIX 옵션의 변동성을 의미하며, 시장 급변동을 선행합니다.</div>
            </div>
            <div class="hint">◀ 안정(<80) | 주의(100) | 위험(120) ▶</div>
        </div>

        <!-- Yield Curve Card (Frame 보존 + Fix 2 내용) -->
        <div class="card">
            <div class="card-header"><span class="card-title">◎ 수익률 곡선 역전 — 침체 선행</span><span class="status-badge" style="background:{bg_good}; color:{c_good};">정상</span></div>
            <table>
                <tr><td>10년 국채 수익률 (^TNX)</td><td class="val">{fv(r['r10y'])}%</td></tr>
                <tr><td>2년 국채 수익률 (2YY=F)</td><td class="val">{fv(r['r2y'])}%</td></tr>
                <tr><td>3개월 T-Bill (^IRX)</td><td class="val">{fv(r['r3m'])}%</td></tr>
            </table>
            <div class="gauge"><div style="width:75%; background:{c_good};"></div></div>
            <div class="interp">
                <div class="interp-title">금리 스프레드 (10Y-3M / 10Y-2Y)</div>
                <div style="font-size:14px; font-weight:800; color:#00838f; margin:5px 0;">{fp(r.get('yc_spread'))} / {fp(r.get('spread_10y_2y'))}</div>
                <div class="interp-note">10Y-2Y 판정: {r.get('state_10y_2y','N/A')}<br>역전 시 경기 침체 1~2년 선행 지표입니다.</div>
            </div>
            <div class="hint">◀ 역전(침체위험) | 정상 ▶</div>
        </div>

        <!-- Credit Spread Card (Frame 보존 + Fix 2/3/4 내용) -->
        <div class="card" style="grid-column: 1 / 2; margin-top: 5px;">
            <div class="card-header"><span class="card-title">◎ 신용 스프레드 — 스마트머니</span><span class="status-badge" style="background:{bg_good}; color:{c_good};">양호</span></div>
            <table>
                <tr><td>HYG (하이일드 ETF)</td><td class="val">${fv(r.get('hyg'))} <small style="color:{'#22c55e' if r.get('h_chg',0)>=0 else '#ef4444'};">{r.get('h_chg',0):+.1f}%</small></td></tr>
                <tr><td>IEF (7-10년 국채 ETF)</td><td class="val">${fv(r.get('ief'))} <small style="color:{'#22c55e' if r.get('i_chg',0)>=0 else '#ef4444'};">{r.get('i_chg',0):+.1f}%</small></td></tr>
                <tr><td>HYG/IEF 비율</td><td class="val">{r.get('cr_ratio',0):.4f}</td></tr>
            </table>
            <div class="interp" style="background:#f0f4ff; border-left-color:#1a237e;">
                <div class="interp-title" style="color:#1a237e;">스마트머니 동향</div>
                <div style="font-size:14px; font-weight:800; color:#1a237e; margin:5px 0;">{r.get('cr_ratio',0):.4f} (HYG {r.get('h_chg',0):+.1f}% / IEF {r.get('i_chg',0):+.1f}%)</div>
                <div class="interp-note">비율이 안정적이면 기관들의 위험자산 선호가 유지됨을 뜻합니다.</div>
            </div>
            <div class="hint">◀ 위험 | 양호 ▶</div>
        </div>
    </div>
    <div style="text-align:center; font-size:11px; color:#aaa; margin-top:40px;">Jason Market · {ts} · 프리미엄 디자인 보존 버전</div>
</div>
<script>
function copyResult() {{
    const text = {copy_text};
    navigator.clipboard.writeText(text).then(() => alert('상세 보고서가 복사되었습니다.'));
}}
</script>
</body>
</html>"""
    return html

def main():
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    closes = fetch_all()
    r = analyze(closes)
    
    # 터미널 출력 (Fix 1/2/4 반영)
    print(f"\n# 시장 스트레스 지표 — {ts}")
    print(f"## 종합 판정: {r['sum_state']}")
    print(f"- 플래그: {', '.join(r['stress_flags']) if r['stress_flags'] else '이상 없음'}")
    print(f"## ① VIX 기간구조")
    print(f"  - VIX9D/VIX30 : {r.get('r_9d_30',0):.3f} {r.get('l1','')}")
    print(f"  - VIX30/VIX3M : {r.get('r_30_3m',0):.3f} {r.get('l2','')}")
    print(f"  - VIX3M/VIX6M : {r.get('r_3m_6m',0):.3f} {r.get('l3','')}")
    print(f"## ② VVIX: {r.get('vvix_state','')}")
    print(f"## ③ 수익률 곡선: {f'{r.get('yc_spread',0):+.2f}%'} (10Y-3M) / {f'{r.get('spread_10y_2y',0):+.2f}%'} (10Y-2Y)")
    print(f"## ④ 신용 스프레드")
    print(f"  - HYG/IEF 비율 : {r.get('cr_ratio',0):.4f}")
    print(f"    ├ HYG 당일 등락 : {r.get('h_chg',0):+.1f}%")
    print(f"    └ IEF 당일 등락 : {r.get('i_chg',0):+.1f}%\n")

    html = generate_html(r, ts)
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, prefix='market_stress_premium_', encoding='utf-8')
    tmp.write(html); tmp.close()
    webbrowser.open(f'file://{tmp.name}')

if __name__ == '__main__':
    main()
