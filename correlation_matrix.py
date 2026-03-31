#!/usr/bin/env python3
"""자산 상관관계 분석 - Jason Market
- KRW 기준 수익률 일원화 (USD 자산 환율 수익률 합산) ← 유지
- [A] 계좌 체감 상관관계: 시차 미보정 (당일 체감 리스크)
- [B] 매크로 실질 상관관계: 미국 자산 1일 시차 보정 (글로벌 자본 흐름)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from xlsx_sync import load_portfolio as _load_pf
import os
import webbrowser

ALERT = '\033[38;5;203m'
WARN  = '\033[38;5;220m'   # 노란색 (경고)
OK    = '\033[38;5;82m'    # 초록색 (검증 통과)
RESET = '\033[0m'

EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

# ══════════════════════════════════════════════════════════════
# [1단계] 자산 3그룹 엄격 분류 상수
# ══════════════════════════════════════════════════════════════
# 그룹 1: 미국 투자 자산 → shift(1) + 환율 합산
US_INVEST = ['QQQM', 'GOOGL', 'Bitcoin']

# 그룹 2: 미국 거시 지표 → shift(1)만 적용, 환율 합산 금지
#         (금리·변동성 지수는 USD 가격 개념 없음)
US_MACRO  = ['Brent', 'WTI', 'Dow선물', 'S&P선물', 'NQ선물', 'Russell', '10년물', 'VIX']

# 그룹 3: 한국 자산 → 원본 수익률 그대로
KR_ASSETS = [
    '삼성전자', 'KODEX 나스닥100', 'KODEX S&P500', 'KODEX 미국반도체',
    'TIGER CD금리(합성)', '금현물(KRX)', 'KOSPI', '달러원',
]

# backward-compat: 기존 코드가 참조하는 집합 유지
US_ASSETS     = US_INVEST + US_MACRO
US_ASSETS_SET = set(US_ASSETS)
KR_ASSETS_SET = set(KR_ASSETS)
US_INVEST_SET = set(US_INVEST)
US_MACRO_SET  = set(US_MACRO)

# ── 보조 상수 ──────────────────────────────────────────────────
PROXY_MAP = {
    'KODEX 나스닥100':  'QQQ',
    'KODEX S&P500':    'SPY',
    'KODEX 미국반도체': 'SOXX',
}
# KRW 기준 수익률 전환 불필요 티커 (원화 자산 or FX·금리 지수)
KRW_NATIVE_TICKERS = {'^KS11', 'USDKRW=X', '^TNX', '^VIX'}

# ── 자산 목록 빌드 ─────────────────────────────────────────────
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
                assets[f'{name:<8}'] = ticker
    except Exception:
        pass

    market = {
        'Bitcoin ': 'BTC-USD',
        'Gold    ': 'GC=F',
        'Brent   ': 'BZ=F',
        'WTI     ': 'CL=F',
        'Dow선물 ': 'YM=F',
        'S&P선물 ': 'ES=F',
        'NQ선물  ': 'NQ=F',
        'Russell ': 'RTY=F',
        'KOSPI   ': '^KS11',
        '달러원  ': 'USDKRW=X',
        '10년물  ': '^TNX',
        'VIX     ': '^VIX',
    }
    for k, v in market.items():
        if v not in seen:
            seen.add(v)
            assets[k] = v
    return assets

ASSETS = _build_assets()

PERIODS = [
    ('1개월', '1mo'),
    ('3개월', '3mo'),
    ('6개월', '6mo'),
]

# ══════════════════════════════════════════════════════════════
# 유틸리티 함수
# ══════════════════════════════════════════════════════════════
def get_close_series(ticker, period):
    """종가 시계열 반환 (날짜만 인덱스로 정규화, tz-naive)"""
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty or len(hist) < 5:
            return None
        close = hist['Close'].copy()
        close.index = pd.to_datetime(close.index).normalize().tz_localize(None)
        close.name = ticker
        return close
    except Exception:
        return None

def fmt_corr(val):
    return f"{val:+.2f}"

def find_notable_pairs(corr_df):
    """상관계수 |r| ≥ 0.6 주목 쌍 추출"""
    col_names = list(corr_df.columns)
    pairs = []
    for i in range(len(col_names)):
        for j in range(i + 1, len(col_names)):
            val = corr_df.iloc[i, j]
            n1  = col_names[i].strip()
            n2  = col_names[j].strip()
            if abs(val) >= 0.6:
                rel = "강한 동조" if val > 0 else "강한 역상관"
                pairs.append(f"{n1} ↔ {n2}: {rel} ({val:+.2f})")
    return pairs

def show_matrix_terminal(title, names, corr_df):
    """터미널 매트릭스 출력"""
    print(f"\n  {title}")
    print(f"  {'':>9}", end='')
    for name in names:
        print(f"  {name.strip()[:6]:>6}", end='')
    print()
    print(f"  {'─'*(9 + len(names)*8)}")
    for i, ni in enumerate(names):
        print(f"  {ni.strip()[:7]:>7}  ", end='')
        for j in range(len(names)):
            val = corr_df.iloc[i, j]
            if i == j:
                print(f"  {'━━━━':>6}", end='')
            else:
                print(f"  {fmt_corr(val):>6}", end='')
        print()

# ══════════════════════════════════════════════════════════════
# [4단계] 검증 함수
# ══════════════════════════════════════════════════════════════
def check_validation(corr_df):
    """시차 보정 후 QQQM ↔ KODEX 나스닥100 상관계수 검증
    0.75 이상 → 정상 동조화 / 미만 → 재확인 필요"""
    stripped_map = {c.strip(): c for c in corr_df.columns}
    qqqm_col  = stripped_map.get('QQQM')
    kodex_col = stripped_map.get('KODEX 나스닥100')
    if qqqm_col is None or kodex_col is None:
        return ''
    val = corr_df.loc[qqqm_col, kodex_col]
    if val >= 0.75:
        return f"{OK}✅ 시차 보정 검증 완료 (QQQM ↔ KODEX NQ: {val:+.2f}, 정상 동조화){RESET}"
    else:
        return f"{WARN}⚠ 환율/시차 보정 재확인 필요 (QQQM ↔ KODEX NQ: {val:+.2f}, 기준 미달){RESET}"

def check_validation_plain(corr_df):
    """HTML용 (ANSI 없는) 검증 결과 반환"""
    stripped_map = {c.strip(): c for c in corr_df.columns}
    qqqm_col  = stripped_map.get('QQQM')
    kodex_col = stripped_map.get('KODEX 나스닥100')
    if qqqm_col is None or kodex_col is None:
        return '', True
    val  = corr_df.loc[qqqm_col, kodex_col]
    ok   = val >= 0.75
    text = (f"✅ 시차 보정 검증 완료 (QQQM ↔ KODEX NQ: {val:+.2f}, 정상 동조화)"
            if ok
            else f"⚠ 환율/시차 보정 재확인 필요 (QQQM ↔ KODEX NQ: {val:+.2f}, 기준 미달)")
    return text, ok

# ══════════════════════════════════════════════════════════════
# HTML 생성
# ══════════════════════════════════════════════════════════════
def generate_html(corr_periods, timestamp):
    def cell_style(val, is_diag):
        if is_diag:
            return 'background:#0f3460;color:#90caf9;font-weight:700;'
        if val > 0.7:    bg = '#1b5e20'
        elif val > 0.3:  bg = '#388e3c'
        elif val > -0.3: bg = '#2a2a3e'
        elif val > -0.7: bg = '#c62828'
        else:            bg = '#b71c1c'
        text_color = '#e0e0e0' if abs(val) < 0.7 else '#ffffff'
        return f'background:{bg};color:{text_color};font-weight:{"700" if abs(val)>=0.7 else "400"};'

    def make_table(corr_df):
        col_names    = list(corr_df.columns)
        header_cells = "".join(f'<th>{n.strip()}</th>' for n in col_names)
        rows_html    = ""
        for i, ni in enumerate(col_names):
            row_cells = (f'<td style="text-align:left;padding-left:8px;'
                         f'color:#90caf9;font-weight:600;white-space:nowrap;">'
                         f'{ni.strip()}</td>')
            for j in range(len(col_names)):
                is_diag = (i == j)
                val     = corr_df.iloc[i, j]
                style   = cell_style(val, is_diag)
                text    = "━━━" if is_diag else f"{val:+.2f}"
                row_cells += f'<td style="{style}text-align:center;padding:7px 10px;">{text}</td>'
            rows_html += f'<tr>{row_cells}</tr>\n'
        return (f'<div style="overflow-x:auto;">'
                f'<table><thead><tr><th></th>{header_cells}</tr></thead>'
                f'<tbody>{rows_html}</tbody></table></div>')

    def make_pairs_html(pairs):
        if not pairs:
            return ''
        items = "".join(f'<div style="margin:4px 0;">{p.strip()}</div>' for p in pairs)
        return (f'<div style="background:#16213e;border-left:3px solid #f9a825;'
                f'border-radius:6px;padding:12px 16px;margin-top:12px;'
                f'font-size:0.86em;">{items}</div>')

    periods_html = ""
    for idx, p in enumerate(corr_periods):
        label      = p['label']
        days_a     = p['days_a']
        days_b     = p['days_b']
        corr_a     = p['corr_a']
        corr_b     = p['corr_b']
        pairs_a    = p['pairs_a']
        pairs_b    = p['pairs_b']
        warning    = p.get('warning', '')
        valid_text = p.get('validation_plain', '')
        valid_ok   = p.get('validation_ok', True)
        pid        = f"p{idx}"

        warn_html = (f'<div class="warn-box">⚠ {warning}</div>' if warning else '')

        valid_html = ''
        if valid_text:
            vc = '#2e7d32' if valid_ok else '#e65100'
            valid_html = (f'<div style="background:{vc};color:#fff;border-radius:6px;'
                          f'padding:8px 14px;font-size:0.84em;font-weight:700;'
                          f'margin-bottom:10px;">{valid_text}</div>')

        table_a      = make_table(corr_a)
        table_b      = make_table(corr_b)
        pairs_a_html = make_pairs_html(pairs_a)
        pairs_b_html = make_pairs_html(pairs_b)

        periods_html += f"""
<div class="period-block">
  <div class="section-title">{label} 상관관계
    <span style="color:#757575;font-size:0.8em;font-weight:400;"> · KRW 기준</span>
  </div>
  {warn_html}
  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('{pid}','A',this)">
      [A] 계좌 체감
      <span class="tab-sub">시차 미보정 · {days_a}거래일</span>
    </button>
    <button class="tab-btn" onclick="switchTab('{pid}','B',this)">
      [B] 매크로 실질
      <span class="tab-sub">미국 시차 보정 · {days_b}거래일</span>
    </button>
  </div>
  <div id="{pid}-A" class="tab-content">
    {table_a}
    {pairs_a_html}
  </div>
  <div id="{pid}-B" class="tab-content" style="display:none;">
    {valid_html}
    {table_b}
    {pairs_b_html}
  </div>
</div>
"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason 자산 상관관계 분석</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Segoe UI',sans-serif; margin:0; padding:20px 30px; }}
  .page {{ max-width:1200px; margin:0 auto; }}
  h1 {{ color:#90caf9; font-size:1.6em; margin-bottom:4px; }}
  .ts {{ color:#757575; font-size:0.85em; margin-bottom:18px; line-height:1.8; }}
  table {{ border-collapse:collapse; background:#16213e; border-radius:8px; overflow:hidden; margin-bottom:8px; width:100%; }}
  th {{ background:#0f3460; color:#90caf9; padding:8px 12px; text-align:center; font-size:0.82em; white-space:nowrap; }}
  th:first-child {{ text-align:left; }}
  td {{ padding:7px 10px; font-size:0.83em; border-bottom:1px solid #1e2a45; }}
  tr:last-child td {{ border-bottom:none; }}
  .section-title {{ color:#90caf9; font-size:1.05em; font-weight:700; margin-bottom:10px;
                    border-left:3px solid #1a5fa8; padding-left:10px; }}
  .period-block {{ margin-bottom:44px; }}
  .legend {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:28px; font-size:0.82em; }}
  .legend-item {{ padding:4px 12px; border-radius:4px; font-weight:600; }}

  /* 탭 버튼 */
  .tab-bar {{ display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap; }}
  .tab-btn {{ background:#16213e; color:#90caf9; border:1px solid #1a5fa8; border-radius:8px;
              padding:8px 18px; cursor:pointer; font-size:0.86em; font-weight:700;
              transition:all .15s; display:flex; flex-direction:column; align-items:flex-start; gap:2px; }}
  .tab-btn.active {{ background:#1a5fa8; color:#fff; border-color:#2979ff; }}
  .tab-btn:hover:not(.active) {{ background:#0f3460; }}
  .tab-sub {{ font-size:0.78em; font-weight:400; opacity:.75; }}

  /* 경고 박스 */
  .warn-box {{ background:#4e2a00; color:#ffcc80; border-left:3px solid #f9a825;
               border-radius:6px; padding:9px 14px; font-size:0.84em;
               font-weight:700; margin-bottom:10px; }}
</style>
</head>
<body>
<div class="page">
  <h1>Jason 자산 상관관계 분석</h1>
  <div class="ts">
    {timestamp}
    &nbsp;·&nbsp; <span style="color:#f9a825;font-weight:600;">※ KRW 기준 수익률 (USD 자산 환율 수익률 합산)</span><br>
    <span style="color:#80cbc4;">
      [A] 계좌 체감 = 시차 미보정 (당일 계좌 체감 리스크 파악용)
      &nbsp;&nbsp;|&nbsp;&nbsp;
      [B] 매크로 실질 = 미국 자산 shift(1) 시차 보정 (글로벌 자본 흐름 파악용)
    </span>
  </div>

  <div class="legend">
    <span class="legend-item" style="background:#1b5e20;">+0.7 이상: 강한 동조</span>
    <span class="legend-item" style="background:#388e3c;">+0.3~0.7: 중간 동조</span>
    <span class="legend-item" style="background:#2a2a3e;border:1px solid #444;">-0.3~0.3: 중립</span>
    <span class="legend-item" style="background:#c62828;">-0.3~-0.7: 중간 역상관</span>
    <span class="legend-item" style="background:#b71c1c;">-0.7 이하: 강한 역상관</span>
  </div>

{periods_html}
</div>

<button id="copy-btn" onclick="copyReport()"
  style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;
         background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;
         font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function switchTab(pid, tab, btn) {{
  document.getElementById(pid+'-A').style.display = (tab==='A') ? '' : 'none';
  document.getElementById(pid+'-B').style.display = (tab==='B') ? '' : 'none';
  btn.closest('.period-block').querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}
function copyReport() {{
  var el = document.querySelector('.page') || document.body;
  navigator.clipboard.writeText(el.innerText)
    .then(function() {{
      var b = document.getElementById('copy-btn');
      b.textContent = '✅ 복사 완료!'; b.style.background = '#2e7d32';
      setTimeout(function() {{ b.textContent = '📋 전체 복사'; b.style.background = '#1a5fa8'; }}, 2500);
    }})
    .catch(function() {{
      var t = document.createElement('textarea');
      t.value = el.innerText;
      document.body.appendChild(t); t.select(); document.execCommand('copy'); document.body.removeChild(t);
    }});
}}
</script>
</body>
</html>"""
    return html


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════
def main():
    print(f"\n{'━'*62}")
    print(f"  Jason 자산 상관관계 분석   {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  [A] 계좌 체감 (시차 미보정)  |  [B] 매크로 실질 (시차 보정)")
    print(f"{'━'*62}")
    print("  데이터 수집 중 (약 10-20초)...")

    names          = list(ASSETS.keys())
    tickers        = list(ASSETS.values())
    name_to_ticker = dict(zip(names, tickers))

    # ══════════════════════════════════════════════════════════════
    # [1단계] 전체 기간(1년) 자산 종가 & FX 일괄 수집
    # ══════════════════════════════════════════════════════════════
    FULL_PERIOD = '1y'

    # USDKRW 종가 수집 (FX 수익률 + '달러원' 자산 겸용)
    _fx_close = get_close_series('USDKRW=X', FULL_PERIOD)
    if _fx_close is None:
        print("  ⚠ USDKRW 데이터 수집 실패 — 종료")
        return

    # 전체 자산 종가 수집
    series_dict = {}
    for name, ticker in zip(names, tickers):
        if ticker == 'USDKRW=X':
            series_dict[name] = _fx_close.copy()   # 이미 수집한 데이터 재활용
            continue
        s = get_close_series(ticker, FULL_PERIOD)
        if s is not None:
            series_dict[name] = s

    if len(series_dict) < 2:
        print("  ⚠ 데이터 부족 — 종료")
        return

    # ══════════════════════════════════════════════════════════════
    # [2단계] 전체 기간 순수 수익률 계산 (dropna 없이 원본 유지)
    # ══════════════════════════════════════════════════════════════
    df_prices = pd.concat(series_dict.values(), axis=1, join='inner')
    df_prices.columns = list(series_dict.keys())

    # 인덱스 정규화 (tz-naive 날짜)
    def _normalize_idx(df):
        df.index = (pd.to_datetime(df.index).normalize().tz_localize(None)
                    if df.index.tzinfo
                    else pd.to_datetime(df.index).normalize())
        return df

    df_prices  = _normalize_idx(df_prices)
    _fx_close  = _normalize_idx(_fx_close.to_frame()).iloc[:, 0]

    df_returns = df_prices.pct_change()             # 자산별 순수 수익률 (행 0 = NaN)
    fx_returns = _fx_close.pct_change()             # 달러/원 환율 수익률  (행 0 = NaN)

    # 공통 날짜 교집합 (tz 정규화 후 정렬)
    common_dates = df_returns.index.intersection(fx_returns.index)
    if len(common_dates) < 30:
        print(f"  ⚠ 공통 데이터 부족 ({len(common_dates)}일) — 종료")
        return

    df_returns = df_returns.loc[common_dates]
    fx_returns = fx_returns.loc[common_dates]

    # ── 3그룹 컬럼 목록 추출 ─────────────────────────────────────
    invest_cols = [c for c in df_returns.columns if c.strip() in US_INVEST_SET]  # shift+FX
    macro_cols  = [c for c in df_returns.columns if c.strip() in US_MACRO_SET]   # shift only
    # KR_ASSETS 컬럼은 원본 그대로 → 별도 조작 없음

    print(f"  수익률: {len(df_returns)}거래일 | "
          f"US투자: {len(invest_cols)}개 | 거시지표: {len(macro_cols)}개")

    # ══════════════════════════════════════════════════════════════
    # [3단계] 전체 마스터 데이터프레임 생성
    #
    #   df_A : [A] 계좌 체감 (시차 미보정)
    #          - US_INVEST : 당일 수익률[T] + 환율[T]
    #          - US_MACRO  : 원본 그대로  ← 환율 더하지 않음
    #          - KR_ASSETS : 원본 그대로
    #          - 전체 기간 dropna()
    #
    #   df_B : [B] 매크로 실질 (시차 보정)
    #          - US_INVEST : shift(1) → 전일[T-1] + 환율[T]
    #          - US_MACRO  : shift(1)만 → 전일[T-1]  ← 환율 절대 더하지 않음
    #          - KR_ASSETS : 원본 그대로
    #          - 전체 기간 dropna()
    #
    # ※ 슬라이싱(tail)은 [4단계] 루프에서만 수행
    # ══════════════════════════════════════════════════════════════

    # [A] 마스터
    df_A = df_returns.copy()
    if invest_cols:
        df_A[invest_cols] = df_A[invest_cols].add(fx_returns, axis=0)  # 투자자산만 FX
    df_A = df_A.dropna()

    # [B] 마스터
    df_B = df_returns.copy()
    if invest_cols:
        df_B[invest_cols] = df_B[invest_cols].shift(1).add(fx_returns, axis=0)  # shift+FX
    if macro_cols:
        df_B[macro_cols]  = df_B[macro_cols].shift(1)                           # shift only
    df_B = df_B.dropna()

    print(f"  마스터 완성: df_A={len(df_A)}거래일 | df_B={len(df_B)}거래일")

    # ══════════════════════════════════════════════════════════════
    # [4단계] 기간별 슬라이싱 → tail(days) → corr (루프)
    # ══════════════════════════════════════════════════════════════
    SLICE_DAYS = {'1개월': 20, '3개월': 60, '6개월': 120}

    corr_periods = []

    for period_label, _ in PERIODS:
        n = SLICE_DAYS[period_label]

        # dropna는 마스터 생성 시 완료 → tail만으로 슬라이싱
        slice_a = df_A.tail(n)
        slice_b = df_B.tail(n)

        days_a = len(slice_a)
        days_b = len(slice_b)

        if days_a < 5 or days_b < 5:
            print(f"\n  ⚠ {period_label}: 슬라이싱 후 데이터 부족 (A:{days_a} B:{days_b})")
            continue

        warning = ''
        if min(days_a, days_b) < 30:
            warning = "소표본 경고: 데이터가 30일 미만이므로 상관계수의 신뢰도가 낮을 수 있습니다."

        corr_a  = slice_a.corr()
        corr_b  = slice_b.corr()
        pairs_a = find_notable_pairs(corr_a)
        pairs_b = find_notable_pairs(corr_b)

        validation_terminal        = check_validation(corr_b)
        validation_plain, valid_ok = check_validation_plain(corr_b)

        valid_names_a = list(corr_a.columns)
        valid_names_b = list(corr_b.columns)

        # [A] 터미널 출력
        print(f"\n  {'─'*60}")
        show_matrix_terminal(
            f"[ {period_label} · A ] 계좌 체감 상관관계"
            f"  |  공통 {days_a}거래일  |  KRW 기준",
            valid_names_a, corr_a
        )
        if warning:
            print(f"\n  {WARN}⚠ {warning}{RESET}")
        if pairs_a:
            print(f"\n  주목 (A):")
            for p in pairs_a:
                print(f"    {p}")

        # [B] 터미널 출력
        print()
        show_matrix_terminal(
            f"[ {period_label} · B ] 매크로 실질 상관관계"
            f"  |  공통 {days_b}거래일  |  미국 시차 보정",
            valid_names_b, corr_b
        )
        if validation_terminal:
            print(f"\n  {validation_terminal}")
        if pairs_b:
            print(f"\n  주목 (B):")
            for p in pairs_b:
                print(f"    {p}")

        corr_periods.append({
            'label':            period_label,
            'days_a':           days_a,
            'days_b':           days_b,
            'corr_a':           corr_a,
            'corr_b':           corr_b,
            'pairs_a':          pairs_a,
            'pairs_b':          pairs_b,
            'warning':          warning,
            'validation_plain': validation_plain,
            'validation_ok':    valid_ok,
        })

    print(f"\n  {'─'*60}")
    print(f"  색상 가이드")
    print(f"  +0.7이상: 강한 동조  |  +0.3~0.7: 중간 동조")
    print(f"  -0.7이하: 강한 역상관 |  -0.3~-0.7: 중간 역상관")
    print()

    # ── HTML 저장 및 브라우저 열기 ────────────────────────────────
    if corr_periods:
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html_content  = generate_html(corr_periods, timestamp_str)
        html_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'correlation_matrix.html'
        )
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  HTML 저장: {html_path}")
        webbrowser.open(f'file://{html_path}')

if __name__ == '__main__':
    main()
