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
from jm_lib.colors import ALERT, AMBER, CYAN, RESET, GREEN, RED, WARN


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
        return '<td style="color:#bbb;">–</td>'
    color = "#00838f" if ret >= 0 else "#c62828"
    bold  = "font-weight:800;" if highlight else "font-weight:600;"
    border = "border-left:2px solid #00838f;" if highlight else ""
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
        if avg > 10:   row_bg = "rgba(0,131,143,0.10)"
        elif avg > 3:  row_bg = "rgba(0,131,143,0.05)"
        elif avg < -10:row_bg = "rgba(198,40,40,0.10)"
        elif avg < -3: row_bg = "rgba(198,40,40,0.05)"
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
            color = "#00838f" if v >= 0 else "#c62828"
            items += f'<span style="margin-right:18px;">{medals[i]} <b>{n}</b> <span style="color:{color};">{v:+.1f}%</span></span>'
        rankings_html += (f'<div style="margin-bottom:10px;">'
                          f'<span style="color:#00838f;font-weight:700;min-width:40px;display:inline-block;">{label}</span>'
                          f' {items}</div>\n')

    since_th = '<th style="color:#00838f;border-left:2px solid #00838f;">매입후</th>' if has_since else ''
    header_cells = "".join(f'<th>{lbl}</th>' for lbl in period_labels) + since_th

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jason 수익률 비교</title>
<style>
  body {{ background:#f5f6f8; color:#2c2c2c; font-family:'Segoe UI',sans-serif; margin:0; padding:20px 30px; }}
  .page {{ max-width:1100px; margin:0 auto; }}
  h1 {{ color:#1a1a1a; font-size:1.6em; margin-bottom:4px; }}
  .ts {{ color:#888; font-size:0.85em; margin-bottom:24px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden;
           margin-bottom:32px; box-shadow:0 1px 6px rgba(0,0,0,.07); }}
  th {{ background:#f0f2f5; color:#444; padding:10px 14px; text-align:right; font-size:0.9em;
        font-weight:700; border-bottom:2px solid #e0e3e8; }}
  th:first-child {{ text-align:left; padding-left:14px; }}
  td {{ padding:9px 14px; text-align:right; font-size:0.88em; border-bottom:1px solid #f0f2f5; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover {{ background:#fafbfc !important; }}
  .section-title {{ color:#1a1a1a; font-size:1.05em; font-weight:700; margin-bottom:14px;
                    border-left:3px solid #00838f; padding-left:10px; }}
  .rankings {{ background:#fff; border-radius:10px; padding:18px 22px; margin-bottom:32px;
               box-shadow:0 1px 6px rgba(0,0,0,.07); }}
  .note {{ color:#999; font-size:0.8em; margin-top:8px; }}
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

<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#00838f;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 2px 10px rgba(0,0,0,.15)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#00838f';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
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
        # ※ portfolio_tracker와 동일하게 순수 주가수익률로 계산 (USD는 현재환율로 통일)
        avg_krw = AVG_PRICES.get(ticker)
        if avg_krw and avg_krw > 0:
            try:
                hist = yf.Ticker(ticker).history(period='2d')
                if not hist.empty:
                    curr = float(hist['Close'].dropna().iloc[-1])
                    is_krw = ticker.endswith('.KS') or ticker in ('^KS11', 'USDKRW=X')

                    if ticker == 'GC=F':
                        # ── 금현물(KRX) 특수처리: grams vs troy oz 단위 통일 ──
                        # avg_krw = KRX 금 가격 (원/그램), GC=F (달러/트로이온스)
                        # 1 troy oz = 31.1035 grams → GC=F를 그램당으로 변환
                        gram_per_troy_oz = 31.1035
                        curr_krw = curr * usdkrw_now / gram_per_troy_oz  # KRW/gram
                    elif is_krw:
                        # ── 한국 주식/지수 ──
                        curr_krw = curr
                    else:
                        # ── USD 자산: 매입환율이 아닌 현재환율로 통일 (portfolio_tracker 동일) ──
                        # 순수 주가 수익률만 계산, FX 효과 제외
                        curr_krw = curr * usdkrw_now
                        # avg_krw를 현재 환율로 재계산 (구매 당시 환율 아님)
                        avg_krw = (avg_krw / (h.get('base_usdkrw', 1350) or 1350)) * usdkrw_now

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

    # ── 예금계좌 현금 (cash_tracker.json 기준) ──────────────
    _ct_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cash_tracker.json')
    try:
        with open(_ct_path, encoding='utf-8') as _f:
            _ct = json.load(_f)
        for acc_name, entries in _ct.items():
            total_cost = sum(e.get('cost_basis', 0) for e in entries)
            total_curr = sum(e.get('prev_balance', 0) for e in entries)
            if total_cost <= 0:
                continue
            cash_ret = (total_curr - total_cost) / total_cost * 100
            lbl = f"현금({acc_name[:6]})"
            # 기간별 수익률은 N/A (현금은 가격 이력 없음), 매입후만 표시
            all_returns[lbl] = [None] * len(PERIODS)
            since_avg[lbl]   = cash_ret
            line = f"  {lbl:<14}" + "".join(f"  {'–':>8}" for _ in PERIODS) + f"  {fmt_ret(cash_ret):>8}"
            print(line)
    except FileNotFoundError:
        print("  ※ 현금 기준값 없음 (2번 포트폴리오 조회 후 자동 생성)")
    except Exception:
        pass

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
