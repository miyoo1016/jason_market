#!/usr/bin/env python3
"""시장 스트레스 지표 - Jason Market
VIX 기간구조 / 수익률 곡선 역전 / 신용 스프레드
API 키 불필요, 완전 무료 (Yahoo Finance 데이터)"""

import yfinance as yf
import webbrowser
import tempfile
from datetime import datetime

# 터미널 색상 — 원색 초록/노랑 제외 (눈 피로 / 가독성 낮음)
CYAN   = '\033[36m'       # 양호 (청록)
AMBER  = '\033[38;5;214m' # 주의 (주황/앰버)
ALERT  = '\033[38;5;203m' # 위험 (연한 빨강)
RESET  = '\033[0m'

TICKERS = ['^VIX9D', '^VIX', '^VIX3M', '^IRX', '^TNX', 'HYG', 'IEF']


# ── 데이터 조회 ───────────────────────────────────────────────

def fetch_all():
    data = yf.download(TICKERS, period='2mo', auto_adjust=True, progress=False)
    return data['Close'] if 'Close' in data.columns else data


def last_price(df, ticker):
    try:
        col = df[ticker].dropna()
        return float(col.iloc[-1]) if not col.empty else None
    except Exception:
        return None


def price_ago(df, ticker, n=21):
    try:
        col = df[ticker].dropna()
        return float(col.iloc[-(n + 1)]) if len(col) >= n + 1 else None
    except Exception:
        return None


# ── 신호 헬퍼 ────────────────────────────────────────────────

def dot_term(green_ok, yellow_ok):
    """터미널용 점 신호"""
    if green_ok:   return CYAN  + '●' + RESET
    if yellow_ok:  return AMBER + '●' + RESET
    return ALERT + '●' + RESET


def dot_html(level):
    """level: 'good' | 'warn' | 'bad'"""
    colors = {'good': '#4dd0e1', 'warn': '#ffb74d', 'bad': '#ef9a9a'}
    labels = {'good': '●', 'warn': '●', 'bad': '●'}
    c = colors.get(level, '#aaa')
    return f'<span style="color:{c};font-size:18px">●</span>'


def level_from_bool(green_ok, yellow_ok):
    if green_ok:   return 'good'
    if yellow_ok:  return 'warn'
    return 'bad'


# ── 분석 로직 ────────────────────────────────────────────────

def analyze(closes):
    """모든 계산 결과를 dict로 반환"""
    result = {}
    stress_flags = []

    # 1. VIX 기간구조
    vix9d = last_price(closes, '^VIX9D')
    vix30 = last_price(closes, '^VIX')
    vix3m = last_price(closes, '^VIX3M')
    result['vix9d'] = vix9d
    result['vix30'] = vix30
    result['vix3m'] = vix3m

    if vix9d and vix3m and vix3m > 0:
        ratio = vix9d / vix3m
        result['vix_ratio'] = ratio
        result['vix_source'] = '9D/3M'
        if ratio < 0.9:
            result['vix_level'] = 'good'
            result['vix_state'] = '콘탱고 (정상)'
            result['vix_note']  = '근기물 < 원기물 → 단기 공포 없음'
        elif ratio < 1.0:
            result['vix_level'] = 'warn'
            result['vix_state'] = '콘탱고 약화 (주의)'
            result['vix_note']  = '변동성 확대 가능성'
        elif ratio < 1.1:
            result['vix_level'] = 'warn'
            result['vix_state'] = '백워데이션 진입'
            result['vix_note']  = '투매 징후 → V자 반등 탐색 구간'
            stress_flags.append('VIX 백워데이션')
        else:
            result['vix_level'] = 'bad'
            result['vix_state'] = '백워데이션 심화'
            result['vix_note']  = '패닉 바닥 구간 → 역발상 매수 힌트'
            stress_flags.append('VIX 백워데이션')
    elif vix30 and vix3m and vix3m > 0:
        ratio = vix30 / vix3m
        result['vix_ratio']  = ratio
        result['vix_source'] = '30D/3M (^VIX9D 없음)'
        result['vix_level']  = 'good' if ratio < 1.0 else 'warn'
        result['vix_state']  = '콘탱고' if ratio < 1.0 else '백워데이션'
        result['vix_note']   = '^VIX9D 조회 불가 — 30일/3개월 비율 사용'
        if ratio >= 1.0:
            stress_flags.append('VIX 백워데이션')
    else:
        result['vix_ratio'] = None

    # 2. 수익률 곡선
    r3m  = last_price(closes, '^IRX')
    r10y = last_price(closes, '^TNX')
    result['r3m']  = r3m
    result['r10y'] = r10y

    if r3m and r10y:
        spread = r10y - r3m
        result['yc_spread'] = spread
        if spread > 0.3:
            result['yc_level'] = 'good'
            result['yc_state'] = '정상'
            result['yc_note']  = '침체 위험 낮음'
        elif spread > 0.0:
            result['yc_level'] = 'warn'
            result['yc_state'] = '평탄화'
            result['yc_note']  = '경기 둔화 가능성'
        elif spread > -0.5:
            result['yc_level'] = 'warn'
            result['yc_state'] = '역전 (경계)'
            result['yc_note']  = '역사적 침체 선행 신호'
            stress_flags.append('금리 역전')
        else:
            result['yc_level'] = 'bad'
            result['yc_state'] = '깊은 역전'
            result['yc_note']  = '침체 진입 가능성 높음'
            stress_flags.append('금리 역전')
    else:
        result['yc_spread'] = None

    # 3. 신용 스프레드
    hyg_now = last_price(closes, 'HYG')
    ief_now = last_price(closes, 'IEF')
    hyg_1m  = price_ago(closes, 'HYG', 21)
    ief_1m  = price_ago(closes, 'IEF', 21)
    result['hyg_now'] = hyg_now
    result['ief_now'] = ief_now
    result['hyg_pct'] = (hyg_now - hyg_1m) / hyg_1m * 100 if (hyg_now and hyg_1m) else None
    result['ief_pct'] = (ief_now - ief_1m) / ief_1m * 100 if (ief_now and ief_1m) else None

    if hyg_now and ief_now and ief_now > 0:
        ratio_now = hyg_now / ief_now
        ratio_1m  = (hyg_1m / ief_1m) if (hyg_1m and ief_1m and ief_1m > 0) else None
        ratio_chg = (ratio_now - ratio_1m) / ratio_1m * 100 if ratio_1m else None
        result['cr_ratio_now'] = ratio_now
        result['cr_ratio_1m']  = ratio_1m
        result['cr_ratio_chg'] = ratio_chg

        if ratio_chg is None or ratio_chg > -0.5:
            result['cr_level'] = 'good'
            result['cr_state'] = '양호'
            result['cr_note']  = '기관 위험선호 유지'
        elif ratio_chg > -1.5:
            result['cr_level'] = 'warn'
            result['cr_state'] = '주의'
            result['cr_note']  = '위험자산 이탈 시작 가능'
        else:
            result['cr_level'] = 'bad'
            result['cr_state'] = '경계 — 신용 경색 징후'
            result['cr_note']  = '스마트머니 위험 회피 중'
            stress_flags.append('신용 경색')
    else:
        result['cr_ratio_now'] = None
        result['cr_ratio_chg'] = None

    result['stress_flags'] = stress_flags

    # 종합 레벨
    n = len(stress_flags)
    if n >= 3:
        result['summary_level'] = 'bad'
        result['summary_state'] = '최고 경보'
        result['summary_note']  = '3개 지표 동시 발생 — 포트폴리오 리스크 축소 강력 검토'
    elif n == 2:
        result['summary_level'] = 'bad'
        result['summary_state'] = '주의'
        result['summary_note']  = '신규 매수 자제, 기존 보유 모니터링'
    elif n == 1:
        result['summary_level'] = 'warn'
        result['summary_state'] = '관찰'
        result['summary_note']  = f'{stress_flags[0]} 추이 지속 주시'
    else:
        result['summary_level'] = 'good'
        result['summary_state'] = '안정'
        result['summary_note']  = '주요 스트레스 지표 이상 없음'

    return result


# ── 터미널 출력 ───────────────────────────────────────────────

def print_terminal(r, ts):
    fv  = lambda v: f"{v:.2f}" if v is not None else "N/A"
    fr  = lambda v: f"{v:.2f}%" if v is not None else "N/A"
    fp  = lambda v: f"{v:>+.1f}%" if v is not None else "N/A"


    # 1. VIX 기간구조
    print(f"  ┌─ 1. VIX 기간구조 — 공포의 시급성")
    print(f"  │")
    print(f"  │   VIX  9일  (^VIX9D) : {fv(r['vix9d']):>6}")
    print(f"  │   VIX 30일  (^VIX)   : {fv(r['vix30']):>6}  ← 일반적으로 사용하는 공포지수")
    print(f"  │   VIX  3개월(^VIX3M) : {fv(r['vix3m']):>6}")
    print(f"  │")
    if r.get('vix_ratio') is not None:
        d = dot_term(r['vix_level'] == 'good', r['vix_level'] == 'warn')
        print(f"  │   {r['vix_source']} 비율 : {r['vix_ratio']:.3f}  {d}  {r['vix_state']}")
        print(f"  │   해석 : {r['vix_note']}")
    else:
        print(f"  │   ⚠ VIX 기간구조 데이터 없음")
    print(f"  └{'─'*56}\n")

    # 2. 수익률 곡선
    print(f"  ┌─ 2. 수익률 곡선 역전 — 침체 선행 지표")
    print(f"  │")
    print(f"  │   3개월 T-Bill  (^IRX) : {fr(r['r3m']):>7}")
    print(f"  │   10년 국채     (^TNX) : {fr(r['r10y']):>7}")
    print(f"  │")
    if r.get('yc_spread') is not None:
        d = dot_term(r['yc_level'] == 'good', r['yc_level'] == 'warn')
        print(f"  │   3M/10Y 스프레드: {r['yc_spread']:>+.2f}%  {d}  {r['yc_state']}  ({r['yc_note']})")
        print(f"  │   참고 : 역전→정상화 시점이 역사적으로 실제 침체 시작")
    else:
        print(f"  │   ⚠ 금리 데이터 조회 실패")
    print(f"  └{'─'*56}\n")

    # 3. 신용 스프레드
    print(f"  ┌─ 3. 신용 스프레드 — 스마트머니 위험 감지")
    print(f"  │   (HYG: 하이일드 회사채 ETF  /  IEF: 7-10년 국채 ETF)")
    print(f"  │")
    print(f"  │   HYG : ${r['hyg_now']:.2f}  (1개월 {fp(r['hyg_pct'])})" if r['hyg_now'] else "  │   HYG : N/A")
    print(f"  │   IEF : ${r['ief_now']:.2f}  (1개월 {fp(r['ief_pct'])})" if r['ief_now'] else "  │   IEF : N/A")
    print(f"  │")
    if r.get('cr_ratio_now') is not None:
        d = dot_term(r['cr_level'] == 'good', r['cr_level'] == 'warn')
        chg_str = f"  (1개월 전: {r['cr_ratio_1m']:.4f}  {fp(r['cr_ratio_chg'])})" if r['cr_ratio_1m'] else ""
        print(f"  │   HYG/IEF 비율 : {r['cr_ratio_now']:.4f}{chg_str}")
        print(f"  │   신용 환경 : {d}  {r['cr_state']}  ({r['cr_note']})")
        print(f"  │   해석 : 비율 하락 = 기관이 국채로 이동 = 주식 선행 매도")
    else:
        print(f"  │   ⚠ ETF 데이터 조회 실패")
    print(f"  └{'─'*56}\n")

    # 종합
    flags = r['stress_flags']
    print(f"  ┌─ 종합 신호")
    print(f"  │")
    d = dot_term(r['summary_level'] == 'good', r['summary_level'] == 'warn')
    flags_str = ' + '.join(flags) if flags else '이상 없음'
    print(f"  │   {d}  [{r['summary_state']}] {flags_str}")
    print(f"  │   → {r['summary_note']}")
    print(f"  └{'─'*56}")
    print(f"\n  ※ HYG/IEF 비율은 신용 스프레드 프록시 (FRED BAMLH0A0HYM2 기준 아님)\n")


# ── HTML 생성 ─────────────────────────────────────────────────

def generate_html(r, ts):
    # 흰색 배경 기준 색상
    level_color  = {'good': '#00838f', 'warn': '#e65100', 'bad': '#c62828'}
    level_bg     = {'good': '#e0f7fa', 'warn': '#fff3e0', 'bad': '#ffebee'}
    level_border = {'good': '#80deea', 'warn': '#ffcc80', 'bad': '#ef9a9a'}

    def badge(level, state):
        c  = level_color.get(level, '#555')
        bg = level_bg.get(level, '#f5f5f5')
        bd = level_border.get(level, '#ccc')
        return (f'<span style="background:{bg};color:{c};border:1px solid {bd};'
                f'padding:3px 12px;border-radius:12px;font-weight:700;font-size:13px">'
                f'{state}</span>')

    def meter(val, lo, hi, reverse=False):
        pct = max(0, min(100, (val - lo) / (hi - lo) * 100))
        if reverse:
            pct = 100 - pct
        color = '#00838f' if pct < 40 else ('#e65100' if pct < 70 else '#c62828')
        return (f'<div style="background:#e0e0e0;border-radius:6px;height:10px;overflow:hidden">'
                f'<div style="width:{pct:.0f}%;height:100%;background:{color};border-radius:6px"></div></div>')

    def fv(v, dp=2): return f"{v:.{dp}f}" if v is not None else "N/A"
    def fr(v):       return f"{v:.2f}%" if v is not None else "N/A"
    def fp(v):       return f"{v:+.1f}%" if v is not None else ""

    # VIX 섹션
    vix_ratio_str = (f"<b>{r['vix_source']} 비율 : {r['vix_ratio']:.3f}</b>"
                     if r.get('vix_ratio') is not None else "<span style='color:#999'>데이터 없음</span>")
    vix_meter = meter(r['vix_ratio'] if r.get('vix_ratio') else 0.8, 0.7, 1.3) if r.get('vix_ratio') else ""
    vix_rows = f"""
      <tr><td>VIX 9일 (^VIX9D)</td><td>{fv(r['vix9d'])}</td></tr>
      <tr><td>VIX 30일 (^VIX)</td><td>{fv(r['vix30'])} <small style="color:#999">← 기준</small></td></tr>
      <tr><td>VIX 3개월 (^VIX3M)</td><td>{fv(r['vix3m'])}</td></tr>"""

    # 수익률 곡선
    yc_spread_str = f"{r['yc_spread']:+.2f}%" if r.get('yc_spread') is not None else "N/A"
    yc_meter = meter(r['yc_spread'], -2, 2) if r.get('yc_spread') is not None else ""
    yc_spread_color = level_color.get(r.get('yc_level', 'warn'), '#333')

    # 신용 스프레드
    cr_ratio_str = ""
    cr_meter = ""
    if r.get('cr_ratio_now') is not None:
        chg_str = (f"  <small style='color:#888'>(1개월 전 {r['cr_ratio_1m']:.4f} &nbsp; {fp(r['cr_ratio_chg'])})</small>"
                   if r['cr_ratio_1m'] else "")
        cr_ratio_str = f"{r['cr_ratio_now']:.4f}{chg_str}"
        cr_meter = meter(r.get('cr_ratio_chg') or 0, -3, 1, reverse=True)
    cr_ratio_color = level_color.get(r.get('cr_level', 'warn'), '#333')

    # 종합 배너
    flags    = r['stress_flags']
    sl       = r['summary_level']
    sc       = level_color.get(sl, '#555')
    sb_bg    = level_bg.get(sl, '#f5f5f5')
    sb_bd    = level_border.get(sl, '#ccc')
    sum_icon = '⚠' if sl == 'bad' else ('◎' if sl == 'warn' else '✓')
    flags_html = ''.join(
        f'<span style="background:#fff;border:1px solid #ccc;color:#555;'
        f'padding:2px 10px;border-radius:8px;margin-right:6px;font-size:12px">{f}</span>'
        for f in flags
    ) if flags else f'<span style="color:{level_color["good"]}">이상 없음</span>'

    def interp_box(level, label, val, note):
        c  = level_color.get(level, '#555')
        bg = level_bg.get(level, '#f9f9f9')
        return (f'<div style="margin-top:14px;padding:12px 14px;background:{bg};'
                f'border-radius:8px;border-left:4px solid {c}">'
                f'<div style="font-size:11px;color:#888;margin-bottom:4px">{label}</div>'
                f'<div style="font-size:13px;font-weight:700;color:{c}">{val}</div>'
                f'<div style="font-size:12px;color:#666;margin-top:3px">{note}</div></div>')

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — 시장 스트레스 지표</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f6f8;color:#222;font-size:14px}}
.header{{background:#1a237e;color:#fff;padding:20px 28px}}
.header h1{{font-size:20px;font-weight:700}}
.header .sub{{font-size:12px;color:#c5cae9;margin-top:4px}}
.container{{max-width:1100px;margin:0 auto;padding:24px 16px 60px}}
.summary-banner{{background:{sb_bg};border:1px solid {sb_bd};border-radius:12px;
  padding:18px 22px;margin-bottom:24px;display:flex;align-items:flex-start;gap:16px}}
.sum-icon{{font-size:30px;color:{sc};line-height:1}}
.sum-title{{font-size:16px;font-weight:700;color:{sc}}}
.sum-detail{{font-size:13px;color:#555;margin-top:4px}}
.flags{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}}
.card{{background:#fff;border-radius:12px;overflow:hidden;
       box-shadow:0 1px 6px rgba(0,0,0,.1)}}
.card-header{{padding:14px 18px;border-bottom:1px solid #eeeeee;
  display:flex;align-items:center;justify-content:space-between;background:#fafafa}}
.card-title{{font-size:14px;font-weight:700;color:#333}}
.card-body{{padding:18px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:9px 0;font-size:13px;border-bottom:1px solid #f0f0f0;color:#444}}
td:last-child{{text-align:right;font-weight:600;color:#1a237e;
               font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:none}}
.gauge-wrap{{margin-top:12px}}
.gauge-label{{display:flex;justify-content:space-between;
              font-size:11px;color:#999;margin-bottom:4px}}
.hint{{margin-top:10px;font-size:11px;color:#999}}
.footer{{text-align:center;font-size:11px;color:#aaa;margin-top:30px}}
</style>
</head>
<body>
<div class="header">
  <h1>Jason Market — 시장 스트레스 지표</h1>
  <div class="sub">업데이트: {ts} &nbsp;|&nbsp; 완전 무료 (Yahoo Finance) &nbsp;|&nbsp; API 키 불필요</div>
</div>
<div class="container">

  <!-- 종합 배너 -->
  <div class="summary-banner">
    <div class="sum-icon">{sum_icon}</div>
    <div>
      <div class="sum-title">{r['summary_state']} — {r['summary_note']}</div>
      <div class="sum-detail">VIX 백워데이션 + 금리 역전 + 신용 경색 동시 발생 시 최고 위험 경보</div>
      <div class="flags">{flags_html}</div>
    </div>
  </div>

  <div class="grid">

    <!-- 카드 1: VIX 기간구조 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">① VIX 기간구조 — 공포의 시급성</span>
        {badge(r.get('vix_level','warn'), r.get('vix_state','N/A'))}
      </div>
      <div class="card-body">
        <table>{vix_rows}</table>
        {'<div class="gauge-wrap"><div class="gauge-label"><span>◀ 콘탱고(안정)</span><span>백워데이션(위험) ▶</span></div>' + vix_meter + '</div>' if vix_meter else ''}
        {interp_box(r.get('vix_level','warn'), '비율 해석', vix_ratio_str, r.get('vix_note',''))}
        <div class="hint">&lt;1.0 콘탱고(정상) &nbsp;|&nbsp; ≥1.0 백워데이션(패닉 바닥 신호)</div>
      </div>
    </div>

    <!-- 카드 2: 수익률 곡선 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">② 수익률 곡선 역전 — 침체 선행</span>
        {badge(r.get('yc_level','warn'), r.get('yc_state','N/A'))}
      </div>
      <div class="card-body">
        <table>
          <tr><td>3개월 T-Bill (^IRX)</td><td>{fr(r['r3m'])}</td></tr>
          <tr><td>10년 국채 (^TNX)</td><td>{fr(r['r10y'])}</td></tr>
          <tr><td>3M/10Y 스프레드</td>
              <td style="color:{yc_spread_color}">{yc_spread_str}</td></tr>
        </table>
        {'<div class="gauge-wrap"><div class="gauge-label"><span>◀ 역전(침체위험)</span><span>정상 ▶</span></div>' + yc_meter + '</div>' if yc_meter else ''}
        {interp_box(r.get('yc_level','warn'), '침체 선행 지표', r.get('yc_note','N/A'), '역전→정상화 시점이 역사적으로 실제 침체 시작점')}
        <div class="hint">스프레드 음수(역전) → 경기 침체 1~2년 선행</div>
      </div>
    </div>

    <!-- 카드 3: 신용 스프레드 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">③ 신용 스프레드 — 스마트머니</span>
        {badge(r.get('cr_level','warn'), r.get('cr_state','N/A'))}
      </div>
      <div class="card-body">
        <table>
          <tr><td>HYG (하이일드 회사채 ETF)</td>
              <td>${fv(r['hyg_now'])} <small style="color:#999">{fp(r['hyg_pct'])}</small></td></tr>
          <tr><td>IEF (7-10년 국채 ETF)</td>
              <td>${fv(r['ief_now'])} <small style="color:#999">{fp(r['ief_pct'])}</small></td></tr>
          <tr><td>HYG/IEF 비율</td>
              <td style="color:{cr_ratio_color}">{fv(r.get('cr_ratio_now') or 0, 4)}</td></tr>
        </table>
        {'<div class="gauge-wrap"><div class="gauge-label"><span>◀ 신용경색(위험)</span><span>양호 ▶</span></div>' + cr_meter + '</div>' if cr_meter else ''}
        {interp_box(r.get('cr_level','warn'), '1개월 비율 변화', cr_ratio_str if cr_ratio_str else 'N/A', r.get('cr_note','') + '  |  비율 하락 = 기관 위험자산 이탈')}
        <div class="hint">비율 하락세 = 스마트머니가 주식 매도 후 국채로 이동</div>
      </div>
    </div>

  </div>

  <div class="footer">
    Jason Market &nbsp;·&nbsp; {ts}<br>
    HYG/IEF 비율은 신용 스프레드 프록시 (실제 OAS: FRED BAMLH0A0HYM2 참조)
  </div>
</div>
</body>
</html>"""
    return html


# ── 메인 ─────────────────────────────────────────────────────

def main():
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*62}")
    print(f"  Jason 시장 스트레스 지표   {ts}")
    print(f"{'━'*62}")
    print("  데이터 수집 중...\n")

    closes = fetch_all()
    r = analyze(closes)

    print_terminal(r, ts)

    html = generate_html(r, ts)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='market_stress_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")


if __name__ == '__main__':
    main()
