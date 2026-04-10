#!/usr/bin/env python3
"""
Jason Market — 종합 AI 분석 (11번)
기술적 + 거시경제 + 리스크 멀티관점 분석
무료 Groq API (Llama-3.3-70B) 사용 / 키 없으면 알고리즘 분석
"""

import os, requests, webbrowser, tempfile
import yfinance as yf
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from xlsx_sync import load_portfolio

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

CYAN  = '\033[36m'
AMBER = '\033[38;5;214m'
ALERT = '\033[38;5;203m'
RESET = '\033[0m'

# ── 포트폴리오 기반 ASSETS 동적 빌드 ─────────────────────────────
PROXY_MAP = {
    'KODEX 나스닥100':  'QQQ',
    'KODEX S&P500':    'SPY',
    'KODEX 미국반도체': 'SOXX',
}

def _atype(ticker):
    if ticker == 'BTC-USD':                         return 'crypto'
    if ticker in ('GC=F', 'BZ=F', 'CL=F'):         return 'commodity'
    if ticker in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'): return 'futures'
    if ticker == 'USDKRW=X':                        return 'fx'
    if ticker in ('^KS11',):                        return 'krindex'
    if ticker.startswith('^'):                      return 'index'
    if ticker.endswith('.KS'):                      return 'krstock'
    return 'etf'

def _build_assets():
    assets, seen = {}, set()
    try:
        for h in load_portfolio():
            if h.get('is_cash') or h.get('ticker') == 'CASH': continue
            t = h['ticker']
            n = h['name']
            if t == 'XLSX_PRICE': t = PROXY_MAP.get(n, 'SPY')
            elif t == 'GOLD_KRX': t = 'GC=F'
            if t and t not in seen:
                seen.add(t); assets[n] = (t, _atype(t))
    except Exception: pass
    # 시장 지표 추가 (포트폴리오에 없는 것만)
    for n, (t, at) in {
        'Bitcoin'   : ('BTC-USD',  'crypto'),
        'Gold'      : ('GC=F',     'commodity'),
        'WTI원유'   : ('CL=F',     'commodity'),
        'S&P선물'   : ('ES=F',     'futures'),
        '나스닥선물' : ('NQ=F',     'futures'),
        '달러/원'   : ('USDKRW=X', 'fx'),
        '미국10년물' : ('^TNX',     'index'),
        'VIX'       : ('^VIX',     'index'),
        '코스피'    : ('^KS11',    'krindex'),
    }.items():
        if t not in seen:
            seen.add(t); assets[n] = (t, at)
    return assets

ASSETS = _build_assets()

MACRO_TICKERS = {
    'VIX': '^VIX', 'DXY': 'DX-Y.NYB',
    'US10Y': '^TNX', 'USDKRW': 'USDKRW=X',
}

# ── 지표 계산 ─────────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else None

def calc_macd(close):
    e12  = close.ewm(span=12, adjust=False).mean()
    e26  = close.ewm(span=26, adjust=False).mean()
    macd = e12 - e26
    sig  = macd.ewm(span=9, adjust=False).mean()
    return float(macd.iloc[-1]), float(sig.iloc[-1])

def calc_bb_pctb(close, period=20):
    ma  = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = float(ma.iloc[-1] + 2*std.iloc[-1])
    lower = float(ma.iloc[-1] - 2*std.iloc[-1])
    curr  = float(close.iloc[-1])
    return (curr - lower) / (upper - lower) * 100 if upper != lower else 50

# ── 데이터 수집 ───────────────────────────────────────────

def get_snapshot(name, ticker, atype):
    try:
        hist = yf.Ticker(ticker).history(period='6mo')
        if hist.empty or len(hist) < 10:
            return None
        close = hist['Close']
        curr  = float(close.iloc[-1])
        prev  = float(close.iloc[-2])
        w1    = float(close.iloc[-5])  if len(close) >= 5  else None
        m1    = float(close.iloc[-21]) if len(close) >= 21 else None

        rsi      = calc_rsi(close)
        macd_v, sig_v = calc_macd(close)
        pct_b    = calc_bb_pctb(close)
        ma20     = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
        ma50     = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        hist_1y = yf.Ticker(ticker).history(period='1y')
        h52 = float(hist_1y['High'].max()) if not hist_1y.empty else None
        l52 = float(hist_1y['Low'].min())  if not hist_1y.empty else None
        pos52 = (curr - l52) / (h52 - l52) * 100 if h52 and l52 and h52 != l52 else None

        return {
            'name': name, 'ticker': ticker, 'type': atype,
            'curr': curr,
            'pct_1d': (curr - prev) / prev * 100,
            'pct_1w': (curr - w1) / w1 * 100  if w1 else None,
            'pct_1m': (curr - m1) / m1 * 100  if m1 else None,
            'rsi': rsi, 'macd_v': macd_v, 'sig_v': sig_v,
            'macd_bull': macd_v > sig_v,
            'pct_b': pct_b, 'ma20': ma20, 'ma50': ma50,
            'pos52': pos52, 'h52': h52, 'l52': l52,
        }
    except Exception as e:
        print(f"  ⚠ {name} 수집 실패: {e}")
        return None

def get_macro():
    macro = {}
    for name, ticker in MACRO_TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period='5d')
            if not hist.empty:
                c = float(hist['Close'].iloc[-1])
                p = float(hist['Close'].iloc[-2])
                macro[name] = {'val': round(c, 3), 'chg': round((c-p)/p*100, 2)}
        except Exception:
            pass
    return macro

def get_portfolio_text():
    try:
        holdings = load_portfolio()
        if not holdings:
            return ""
        lines = []
        for h in holdings:
            if h.get('is_cash'):
                sym = '₩' if h.get('currency','KRW') == 'KRW' else '$'
                lines.append(f"{h['name']} {sym}{h['avg_price']:,.0f} 현금")
            else:
                sym = '$' if h.get('currency','KRW') == 'USD' else '₩'
                lines.append(f"{h['name']} {h.get('qty',0)}주@{sym}{h.get('avg_price',0):,.2f}")
        return "Jason 보유: " + ", ".join(lines)
    except Exception:
        return ""

# ── Groq 무료 API ─────────────────────────────────────────

def call_groq(system_prompt, user_prompt, max_tokens=500):
    api_key = os.getenv('GROQ_API_KEY', '').strip()
    if not api_key:
        return None
    try:
        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user',   'content': user_prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': 0.3,
            },
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"  ⚠ Groq 오류 {resp.status_code}: {resp.text[:100]}")
            return None
    except Exception as e:
        print(f"  ⚠ Groq 연결 실패: {e}")
        return None

# ── 알고리즘 분석 (폴백) ──────────────────────────────────

def algo_signal(r):
    score = 0
    reasons = []
    if r['rsi']:
        if r['rsi'] < 30:  score += 2; reasons.append(f"RSI {r['rsi']:.0f} 과매도")
        elif r['rsi'] > 70: score -= 2; reasons.append(f"RSI {r['rsi']:.0f} 과매수")
        else: reasons.append(f"RSI {r['rsi']:.0f} 중립")
    if r['macd_bull']:  score += 1; reasons.append("MACD 양전환")
    else:               score -= 1; reasons.append("MACD 음전환")
    if r['pct_b'] < 20:  score += 1; reasons.append("볼린저 하단 근접")
    elif r['pct_b'] > 80: score -= 1; reasons.append("볼린저 상단 근접")
    if r['ma20'] and r['curr'] > r['ma20']: score += 1
    if r['ma50'] and r['curr'] > r['ma50']: score += 1

    if score >= 3:   verdict = "매수"
    elif score >= 1: verdict = "관망(긍정)"
    elif score >= -1: verdict = "관망(중립)"
    elif score >= -3: verdict = "관망(부정)"
    else:             verdict = "매도"
    return verdict, ", ".join(reasons[:3])

def algo_analysis(results, macro):
    lines = ["[알고리즘 기술 분석]\n"]
    for r in results:
        if r['type'] in ('index', 'fx', 'krindex'):
            continue
        verdict, reason = algo_signal(r)
        lines.append(f"  {r['name']:<12}: {verdict:8}  ({reason})")

    lines.append("\n[거시환경]")
    if 'VIX' in macro:
        v = macro['VIX']['val']
        env = "극도공포" if v > 40 else "공포" if v > 25 else "중립" if v > 18 else "탐욕"
        lines.append(f"  VIX {v:.1f} → 시장심리 {env}")
    if 'US10Y' in macro:
        lines.append(f"  미국10년물 {macro['US10Y']['val']:.2f}%  변화 {macro['US10Y']['chg']:+.2f}%")
    if 'USDKRW' in macro:
        lines.append(f"  달러/원 {macro['USDKRW']['val']:,.1f}  변화 {macro['USDKRW']['chg']:+.2f}%")

    lines.append("\n※ Groq API 키 없음 → 알고리즘 분석 (GROQ_API_KEY를 .env에 추가하면 AI 분석 활성화)")
    return "\n".join(lines)

# ── AI 분석 실행 ──────────────────────────────────────────

SYS_TECH = """당신은 기술적 분석 전문가입니다. (차트 분석 15년 경력)
Jason의 포트폴리오 데이터를 보고 한국어로 간결하게 분석하세요.
마크다운/이모지 금지. 각 항목은 한 줄.
형식:
[기술적 분석]
시그널: 전체 시장 방향 (강세/약세/혼조) — 핵심 근거 한 문장
과매수 주의: RSI 70 이상 자산 나열 (없으면 "없음")
과매도 기회: RSI 30 이하 자산 나열 (없으면 "없음")
MACD 긍정: 양전환 자산 나열
핵심 레벨: 가장 중요한 지지/저항 레벨 2가지"""

SYS_MACRO = """당신은 거시경제 및 시장심리 분석 전문가입니다. (전 FED 이코노미스트)
Jason의 시장 데이터를 보고 한국어로 간결하게 분석하세요.
마크다운/이모지 금지.
형식:
[거시 분석]
환경: 위험선호/중립/위험회피 — VIX·금리·달러 수치 근거
금리영향: 현재 금리 수준이 포트폴리오에 미치는 영향 한 문장
달러영향: 달러 강약이 한국 자산·원화에 미치는 영향 한 문장
단기전망: 향후 2-4주 시장 방향 한 문장"""

SYS_SYNTH = """당신은 Jason의 수석 투자 어드바이저입니다.
Jason 프로필: 한국 개인투자자. QQQM/SPY/GOOGL/BTC/금/원유 등 보유.
기술분석과 거시분석을 종합하여 구체적인 포트폴리오 액션을 제시하세요.
애매한 표현 금지. 한국어로. 마크다운/이모지 금지.
형식:
[종합 판단]
결론: 핵심 한 문장

즉시 행동:
Bitcoin : 매수/매도/유지 — 이유
Gold    : 매수/매도/유지 — 이유
Google  : 매수/매도/유지 — 이유
QQQM    : 매수/매도/유지 — 이유
SPY     : 매수/매도/유지 — 이유
원유    : 매수/매도/유지 — 이유

리스크 요인:
1. 첫 번째 위험 요소
2. 두 번째 위험 요소

신뢰도: 0-100% — 이유 한 문장"""

def build_data_text(results, macro):
    lines = ["[시장 데이터]"]
    for r in results:
        rsi_s  = f"RSI={r['rsi']:.0f}" if r['rsi'] else "RSI=N/A"
        macd_s = "MACD=양" if r['macd_bull'] else "MACD=음"
        bb_s   = f"BB%B={r['pct_b']:.0f}"
        pos_s  = f"52주={r['pos52']:.0f}%" if r['pos52'] else ""
        pct1d  = f"{r['pct_1d']:+.1f}%"
        pct1m  = f"{r['pct_1m']:+.1f}%" if r['pct_1m'] else "N/A"
        lines.append(
            f"  {r['name']:<12} {pct1d:>6} (1달{pct1m}) | {rsi_s} {macd_s} {bb_s} {pos_s}"
        )

    lines.append("\n[거시지표]")
    for k, v in macro.items():
        lines.append(f"  {k}: {v['val']} ({v['chg']:+.2f}%)")
    return "\n".join(lines)

def run_ai_analysis(results, macro, portfolio_text):
    has_groq = bool(os.getenv('GROQ_API_KEY', '').strip())

    if not has_groq:
        print(f"  {AMBER}Groq API 키 없음 → 알고리즘 분석 실행{RESET}")
        analysis_text = algo_analysis(results, macro)
        return None, None, analysis_text, False

    data_text = build_data_text(results, macro)
    full_prompt = f"{data_text}\n\n{portfolio_text}" if portfolio_text else data_text

    print(f"  {CYAN}[1/3] 기술적 분석 중...{RESET}")
    tech = call_groq(SYS_TECH, full_prompt, max_tokens=400)

    print(f"  {CYAN}[2/3] 거시경제 분석 중...{RESET}")
    macro_analysis = call_groq(SYS_MACRO, full_prompt, max_tokens=400)

    print(f"  {CYAN}[3/3] 종합 판단 중...{RESET}")
    synth_prompt = ""
    if tech:          synth_prompt += tech + "\n\n"
    if macro_analysis: synth_prompt += macro_analysis + "\n\n"
    synth_prompt += full_prompt
    final = call_groq(SYS_SYNTH, synth_prompt, max_tokens=600)

    if not (tech or macro_analysis or final):
        print(f"  {AMBER}Groq 분석 실패 → 알고리즘 분석으로 전환{RESET}")
        return None, None, algo_analysis(results, macro), False

    return tech, macro_analysis, final, True

# ── 출력 헬퍼 ─────────────────────────────────────────────

def fmt_price(r):
    c = r['curr']
    t = r['type']
    if t == 'crypto':              return f"${c:,.0f}"
    if t == 'commodity':           return f"${c:,.1f}"
    if t == 'futures':             return f"{c:,.1f}"
    if t == 'fx':                  return f"₩{c:,.1f}"
    if t in ('index', 'krindex'):  return f"{c:,.2f}"
    if t == 'krstock':             return f"₩{c:,.0f}"
    return f"${c:,.2f}"

def fmt_pct(v):
    return f"{v:+.2f}%" if v is not None else "N/A"

# ── HTML 생성 ─────────────────────────────────────────────

def generate_html(results, macro, tech_text, macro_text, final_text, is_ai, timestamp):

    def pct_color(v):
        if v is None: return '#888'
        return '#00838f' if v >= 0 else '#c62828'

    def rsi_color(v):
        if v is None: return '#888'
        if v >= 70: return '#c62828'
        if v <= 30: return '#00838f'
        return '#555'

    def rsi_label(v):
        if v is None: return 'N/A'
        if v >= 70: return f'{v:.0f} 과매수'
        if v <= 30: return f'{v:.0f} 과매도'
        return f'{v:.0f}'

    price_rows = ''
    for r in results:
        p1d = r['pct_1d'];  p1w = r['pct_1w'];  p1m = r['pct_1m']
        price_rows += f"""
        <tr>
          <td class="name-col">{r['name']}</td>
          <td class="num-col">{fmt_price(r)}</td>
          <td class="num-col" style="color:{pct_color(p1d)};font-weight:600">{fmt_pct(p1d)}</td>
          <td class="num-col" style="color:{pct_color(p1w)};font-weight:600">{fmt_pct(p1w)}</td>
          <td class="num-col" style="color:{pct_color(p1m)};font-weight:600">{fmt_pct(p1m)}</td>
        </tr>"""

    tech_rows = ''
    for r in results:
        macd_s = '<span style="color:#00838f;font-weight:600">▲양</span>' if r['macd_bull'] else '<span style="color:#c62828;font-weight:600">▼음</span>'
        pb = r['pct_b']
        if pb > 80:   pb_s = f'<span style="color:#c62828;font-weight:600">{pb:.0f}% 과열</span>'
        elif pb < 20: pb_s = f'<span style="color:#00838f;font-weight:600">{pb:.0f}% 침체</span>'
        else:         pb_s = f'<span style="color:#555">{pb:.0f}%</span>'
        pos = f"{r['pos52']:.0f}%" if r['pos52'] is not None else 'N/A'
        tech_rows += f"""
        <tr>
          <td class="name-col">{r['name']}</td>
          <td class="num-col" style="color:{rsi_color(r['rsi'])};font-weight:600">{rsi_label(r['rsi'])}</td>
          <td class="num-col">{macd_s}</td>
          <td class="num-col">{pb_s}</td>
          <td class="num-col">{pos}</td>
        </tr>"""

    macro_rows = ''
    for k, v in macro.items():
        mc = '#00838f' if v['chg'] >= 0 else '#c62828'
        macro_rows += f"""
        <tr>
          <td class="name-col">{k}</td>
          <td class="num-col">{v['val']}</td>
          <td class="num-col" style="color:{mc};font-weight:600">{v['chg']:+.2f}%</td>
        </tr>"""

    def render_section(title, subtitle, text, border_color):
        if not text:
            return ''
        escaped = text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        return f"""
    <div class="ai-card" style="border-left-color:{border_color}">
      <div class="ai-title">{title} <span class="ai-sub">{subtitle}</span></div>
      <pre class="ai-body">{escaped}</pre>
    </div>"""

    ai_label = "Groq Llama-3.3-70B (무료)" if is_ai else "알고리즘 분석 (무료)"

    if is_ai:
        analysis_html  = render_section("기술적 분석", "Llama-3.3-70B", tech_text or '', '#00838f')
        analysis_html += render_section("거시경제 분석", "Llama-3.3-70B", macro_text or '', '#e65100')
        analysis_html += render_section("종합 판단 & 액션", "Llama-3.3-70B", final_text or '', '#1a237e')
    else:
        analysis_html = render_section("알고리즘 분석", "무료 (API 불필요)", final_text or '', '#555')

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Jason 종합 AI 분석</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f6f8;color:#222;font-family:'Segoe UI',Arial,sans-serif;padding:20px}}
h1{{font-size:19px;font-weight:700;color:#1a237e;margin-bottom:3px}}
.ts{{font-size:12px;color:#888;margin-bottom:16px}}
.badge{{display:inline-block;background:#e8f5e9;color:#2e7d32;font-size:11px;
  font-weight:600;padding:2px 8px;border-radius:4px;margin-left:8px;vertical-align:middle}}
.section{{background:#fff;border-radius:10px;padding:16px 20px;
  border:1px solid #dde3f0;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:16px}}
.section-title{{font-size:13px;font-weight:700;color:#1a237e;margin-bottom:12px;
  text-transform:uppercase;letter-spacing:0.4px}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:11px;color:#888;text-align:right;padding:5px 10px;
  border-bottom:1px solid #eee;font-weight:600;text-transform:uppercase}}
th.name-col{{text-align:left}}
td{{font-size:13px;padding:6px 10px;border-bottom:1px solid #f0f2f8;text-align:right}}
td.name-col{{text-align:left;color:#333;font-weight:600}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#fafbff}}
.ai-card{{background:#fff;border-radius:10px;padding:18px 20px;
  border:1px solid #dde3f0;border-left:4px solid #00838f;
  box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:14px}}
.ai-title{{font-size:14px;font-weight:700;color:#1a237e;margin-bottom:10px}}
.ai-sub{{font-size:11px;font-weight:400;color:#888;margin-left:6px}}
.ai-body{{font-size:13px;line-height:1.8;color:#333;
  white-space:pre-wrap;word-break:break-word;
  background:#f8f9fc;border-radius:6px;padding:14px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:700px){{.grid2{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<h1>📊 Jason 종합 AI 분석<span class="badge">🆓 {ai_label}</span></h1>
<div class="ts">{timestamp}</div>

<div class="grid2">
  <div class="section">
    <div class="section-title">시세 요약</div>
    <table>
      <thead><tr>
        <th class="name-col">자산</th><th>현재가</th>
        <th>일간%</th><th>1주%</th><th>1달%</th>
      </tr></thead>
      <tbody>{price_rows}</tbody>
    </table>
  </div>
  <div>
    <div class="section">
      <div class="section-title">기술지표</div>
      <table>
        <thead><tr>
          <th class="name-col">자산</th><th>RSI</th>
          <th>MACD</th><th>볼린저%B</th><th>52주위치</th>
        </tr></thead>
        <tbody>{tech_rows}</tbody>
      </table>
    </div>
    <div class="section">
      <div class="section-title">거시지표</div>
      <table>
        <thead><tr>
          <th class="name-col">지표</th><th>현재값</th><th>변화%</th>
        </tr></thead>
        <tbody>{macro_rows}</tbody>
      </table>
    </div>
  </div>
</div>

{analysis_html}
</body>
</html>"""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(base_dir, 'auto_analysis.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    webbrowser.open(f'file://{out_path}')
    print(f"  {CYAN}브라우저 열림: {out_path}{RESET}\n")

# ── 메인 ─────────────────────────────────────────────────

def main():
    ts = datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')
    print(f"\n{'━'*62}")
    print(f"  Jason 종합 AI 분석  {ts}")
    print(f"{'━'*62}")

    has_groq = bool(os.getenv('GROQ_API_KEY', '').strip())
    mode = f"{CYAN}Groq Llama-3.3-70B (무료 AI){RESET}" if has_groq else f"{AMBER}알고리즘 분석 (API 불필요){RESET}"
    print(f"  모드: {mode}")
    if not has_groq:
        print(f"  {AMBER}→ .env 에 GROQ_API_KEY 추가 시 AI 분석 활성화 (groq.com 무료){RESET}")
    print()

    # 데이터 수집
    print("  데이터 수집 중 (약 20초)...")
    results = []
    for name, (ticker, atype) in ASSETS.items():
        r = get_snapshot(name, ticker, atype)
        if r:
            results.append(r)
            print(f"  ✓ {name:<14} {fmt_price(r):>12}  {r['pct_1d']:+.2f}%")

    macro = get_macro()
    portfolio_text = get_portfolio_text()

    if not results:
        print(f"  {ALERT}⚠ 데이터 수집 실패. 네트워크 확인.{RESET}")
        return

    # 기술지표 요약 터미널 출력
    print(f"\n  {'─'*56}")
    print(f"  {'자산':<14} {'RSI':>5} {'MACD':>6} {'BB%B':>6} {'52주%':>6}")
    print(f"  {'─'*56}")
    for r in results:
        rsi_s  = f"{r['rsi']:.0f}" if r['rsi'] else 'N/A'
        macd_s = '▲양' if r['macd_bull'] else '▼음'
        print(f"  {r['name']:<14} {rsi_s:>5} {macd_s:>6} {r['pct_b']:>5.0f}% "
              f"{r['pos52']:>5.0f}%" if r['pos52'] else f"  {r['name']:<14} {rsi_s:>5} {macd_s:>6} {r['pct_b']:>5.0f}%")

    print(f"\n  AI 분석 실행 중...")
    tech_t, macro_t, final_t, is_ai = run_ai_analysis(results, macro, portfolio_text)

    # 터미널 결과 출력
    print(f"\n{'━'*62}")
    if tech_t:  print(tech_t)
    if macro_t: print(f"\n{macro_t}")
    if final_t: print(f"\n{final_t}")
    print(f"{'━'*62}\n")

    generate_html(results, macro, tech_t, macro_t, final_t, is_ai, ts)

if __name__ == '__main__':
    main()
