#!/usr/bin/env python3
"""
Jason Market — 종합 AI 분석 (9번)
기술적 + 거시경제 + 리스크 멀티관점 분석
Ollama 로컬 LLM A/B 분석 / Groq 무료 API / 알고리즘 fallback
"""

from jm_lib.colors import ALERT, AMBER, CYAN, RESET, GREEN, RED, WARN

import os, re, requests, webbrowser, tempfile
import yfinance as yf
import numpy as np
from datetime import datetime
from xlsx_sync import load_portfolio

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

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

# ══════════════════════════════════════════════════════════
# ── Ollama 로컬 LLM A/B 분석 (신규) ──────────────────────
# ══════════════════════════════════════════════════════════

_OLLAMA_MODELS = ["gemma4:26b", "gemma4:31b"]

_OLLAMA_SYSTEM = """너는 Jason의 "9. 종합 AI 분석"을 해석하는 로컬 AI 분석 보조자다.
매수/매도 추천자가 아니다. 아래 금지 표현은 절대 사용하지 않는다:
강력 매수, 강력 매도, 지금 사야, 지금 팔아야, 확정 상승, 확정 하락, 폭락 확정, 수익 보장, 투자 추천.

분석 기준:
- 시세 요약의 일간/1주/1달 흐름을 비교한다.
- 기술지표는 과열/침체/주의 관점으로만 해석한다. 매수/매도 신호로 단정하지 않는다.
- RSI 과매수는 바로 매도 신호가 아니다. MACD 양전환은 바로 매수 신호가 아니다.
- 볼린저 상단 근접은 과열 또는 변동성 확대 신호로만 본다.
- 52주 위치가 높으면 장기 강세와 과열 가능성을 함께 본다.
- VIX, DXY, US10Y, USDKRW는 거시 부담/완충 요인으로 해석한다.
- CD금리 상품은 현금성 자산으로 분류한다.
- 숫자는 DATA FACTS 기준만 사용한다. 새 숫자를 만들지 않는다.

다음 형식대로 한국어로 분석하라:

# Jason 종합 AI 분석

## 1. 데이터 기준
- 분석 시각: (DATA FACTS 첫 줄에서 가져올 것)
- 데이터 출처: 기존 9번 시세요약/기술지표/거시지표
- 로컬 모델명: (아래 전달되는 {model} 값 사용)

## 2. 시세 흐름 요약
- 일간 약세/강세
- 1주 흐름
- 1달 흐름
- 단기 하락과 1달 상승이 충돌하는 자산 구분

## 3. 기술지표 해석
- 과열권 자산
- 중립권 자산
- 침체권 자산
- MACD 양/음 전환 해석
- 볼린저%B와 52주 위치를 위험도 관점으로 해석

## 4. 거시지표 해석
- VIX
- DXY
- US10Y
- USDKRW
- 자산군에 줄 수 있는 부담/완충 요인

## 5. 리스크 체크
- 나스닥/반도체 중복 노출
- 금리/환율 부담
- 과열 지표가 많은 자산
- 단기 하락이 큰 자산

## 6. 하지 말아야 할 것
- RSI/MACD만 보고 매수/매도 판단하지 않기
- 하루 등락만 보고 방향성 단정하지 않기
- 1달 상승률만 보고 리스크를 무시하지 않기
- 거시지표를 개별 종목처럼 해석하지 않기

## 7. 한 줄 판정
- 주의 / 중립 / 양호 중 하나
- 이유를 한 문장으로 설명"""


def _fmt_nan(v, fmt="{:.2f}"):
    """None/NaN → '데이터 없음', 그 외 형식 지정."""
    if v is None:
        return "데이터 없음"
    try:
        if v != v:   # NaN check
            return "데이터 없음"
        return fmt.format(v)
    except Exception:
        return "데이터 없음"


def build_data_facts(results, macro) -> str:
    """
    기존 9번의 3개 표를 문자열로 조립 (Ollama A/B 공통 DATA FACTS).
    nan 값은 '데이터 없음'으로 변환.
    새 숫자나 새 항목을 추가하지 않는다.
    """
    from datetime import datetime as _dt
    ts = _dt.now().strftime('%Y-%m-%d %H:%M KST')
    lines = [f"분석 시각: {ts}", ""]

    # ── 표 1: 시세 요약 ───────────────────────────────────
    lines += [
        "[시세 요약]",
        f"{'자산':<16} {'현재가':>14} {'일간%':>8} {'1주%':>8} {'1달%':>8}",
        "─" * 58,
    ]
    for r in results:
        price = fmt_price(r)
        d1 = _fmt_nan(r.get('pct_1d'), "{:+.2f}%")
        w1 = _fmt_nan(r.get('pct_1w'), "{:+.2f}%")
        m1 = _fmt_nan(r.get('pct_1m'), "{:+.2f}%")
        lines.append(f"{r['name']:<16} {price:>14} {d1:>8} {w1:>8} {m1:>8}")

    # ── 표 2: 기술지표 ────────────────────────────────────
    lines += [
        "",
        "[기술지표]",
        f"{'자산':<16} {'RSI':>7} {'MACD':>8} {'볼린저%B':>10} {'52주위치':>9}",
        "─" * 54,
    ]
    for r in results:
        rsi_s  = _fmt_nan(r.get('rsi'), "{:.1f}")
        macd_s = "양전환" if r.get('macd_bull') else "음전환"
        pctb_s = _fmt_nan(r.get('pct_b'), "{:.1f}%")
        pos52  = _fmt_nan(r.get('pos52'), "{:.1f}%")
        lines.append(
            f"{r['name']:<16} {rsi_s:>7} {macd_s:>8} {pctb_s:>10} {pos52:>9}"
        )

    # ── 표 3: 거시지표 ────────────────────────────────────
    lines += [
        "",
        "[거시지표]",
        f"{'지표':<12} {'현재값':>12} {'변화%':>8}",
        "─" * 36,
    ]
    for k, v in macro.items():
        val_s = str(v.get('val', '데이터 없음'))
        chg_s = _fmt_nan(v.get('chg'), "{:+.2f}%")
        lines.append(f"{k:<12} {val_s:>12} {chg_s:>8}")

    return "\n".join(lines)


def _build_ollama_prompt(data_facts: str, model: str) -> str:
    """DATA FACTS + 시스템 역할 합성 → 최종 Ollama 프롬프트."""
    system = _OLLAMA_SYSTEM.replace("{model}", model)
    return (
        f"{system}\n\n"
        f"DATA FACTS (아래 숫자 이외의 수치는 사용하지 말 것):\n"
        f"{'─'*60}\n"
        f"{data_facts}\n"
        f"{'─'*60}\n\n"
        f"위 DATA FACTS를 기반으로 분석하라. 모델명은 '{model}'을 사용하라."
    )


# ── 출력 저장 헬퍼 ─────────────────────────────────────────

def _outputs_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    os.makedirs(d, exist_ok=True)
    return d


def _md_to_html_body(text: str) -> str:
    """간단 Markdown → HTML 변환 (h1/h2/li/p/strong)."""
    out = []
    in_ul = False
    for raw in text.split('\n'):
        line = raw.rstrip()
        if line.startswith('# ') and not line.startswith('## '):
            if in_ul: out.append('</ul>'); in_ul = False
            out.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            if in_ul: out.append('</ul>'); in_ul = False
            out.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('- ') or line.startswith('* '):
            if not in_ul: out.append('<ul>'); in_ul = True
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:])
            out.append(f'  <li>{content}</li>')
        elif line == '':
            if in_ul: out.append('</ul>'); in_ul = False
            out.append('')
        else:
            if in_ul: out.append('</ul>'); in_ul = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            out.append(f'<p>{content}</p>')
    if in_ul:
        out.append('</ul>')
    return '\n'.join(out)


_HTML_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f5f6f8;color:#222;font-family:'Segoe UI',Arial,sans-serif;padding:24px;max-width:900px;margin:auto}
h1{font-size:20px;font-weight:700;color:#1a237e;margin:20px 0 6px}
h2{font-size:15px;font-weight:700;color:#00838f;margin:18px 0 6px;padding-left:8px;border-left:3px solid #00838f}
p{font-size:13px;line-height:1.8;color:#333;margin:4px 0}
ul{padding-left:22px;margin:4px 0}
li{font-size:13px;line-height:1.9;color:#333}
strong{color:#1a237e}
.meta{font-size:12px;color:#888;margin-bottom:20px}
.badge{display:inline-block;background:#e8f5e9;color:#2e7d32;font-size:11px;
  font-weight:600;padding:2px 8px;border-radius:4px;margin-left:8px}
pre.facts{background:#f0f2f8;border-radius:8px;padding:14px;font-size:12px;
  font-family:monospace;white-space:pre-wrap;color:#333;margin:16px 0}
"""


def _save_result_md(text: str, label: str) -> str:
    """outputs/ai_analysis_{label}.md 저장 → 경로 반환."""
    path = os.path.join(_outputs_dir(), f"ai_analysis_{label}.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def _save_result_html(text: str, label: str, model: str, ts: str,
                      data_facts: str) -> str:
    """outputs/ai_analysis_{label}.html 저장 → 경로 반환."""
    body  = _md_to_html_body(text)
    facts_esc = data_facts.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Jason AI 분석 — {model}</title>
<style>{_HTML_CSS}</style>
</head>
<body>
<h1 style="margin-top:0">📊 Jason AI 분석 <span class="badge">🏠 {model}</span></h1>
<div class="meta">{ts}</div>
{body}
<h2 style="margin-top:32px">📋 DATA FACTS (분석 기준)</h2>
<pre class="facts">{facts_esc}</pre>
</body>
</html>"""
    path = os.path.join(_outputs_dir(), f"ai_analysis_{label}.html")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


def _save_compare(res_a: dict, res_b: dict,
                  data_facts: str, ts: str) -> tuple:
    """비교 리포트 MD + HTML 저장 → (md_path, html_path)."""
    import ollama_client as _oc

    def _row(key, va, vb):
        return f"| {key} | {va} | {vb} |"

    # ── MD 비교 리포트 ─────────────────────────────────
    lines = [
        "# Jason AI 분석 — A/B 비교 리포트",
        f"생성 시각: {ts}",
        "",
        "## 실행 결과",
        "",
        f"| 항목 | {res_a['model']} | {res_b['model']} |",
        "|------|------------|------------|",
    ]

    for res, label in [(res_a, 'A'), (res_b, 'B')]:
        pass  # 아래에서 행 단위로 처리

    ok_a = "✅ 성공" if res_a['success'] else f"❌ 실패 ({res_a.get('error','?')[:40]})"
    ok_b = "✅ 성공" if res_b['success'] else f"❌ 실패 ({res_b.get('error','?')[:40]})"
    lines.append(_row("성공 여부", ok_a, ok_b))

    t_a = f"{res_a.get('elapsed',0):.1f}s"
    t_b = f"{res_b.get('elapsed',0):.1f}s"
    lines.append(_row("실행 시간", t_a, t_b))

    len_a = len(res_a.get('text',''))
    len_b = len(res_b.get('text',''))
    lines.append(_row("출력 길이(자)", str(len_a), str(len_b)))

    _, forb_a = _oc.validate_output(res_a.get('text',''))
    _, forb_b = _oc.validate_output(res_b.get('text',''))
    lines.append(_row("금지 표현",
                       "없음" if not forb_a else f"⚠ {', '.join(forb_a)}",
                       "없음" if not forb_b else f"⚠ {', '.join(forb_b)}"))

    susp_a, nums_a = _oc.check_number_distortion(data_facts, res_a.get('text',''))
    susp_b, nums_b = _oc.check_number_distortion(data_facts, res_b.get('text',''))
    lines.append(_row("숫자 왜곡 의심",
                       f"⚠ {nums_a[:2]}" if susp_a else "정상",
                       f"⚠ {nums_b[:2]}" if susp_b else "정상"))

    verdict_a = _oc.extract_verdict(res_a.get('text','')) or "—"
    verdict_b = _oc.extract_verdict(res_b.get('text','')) or "—"
    lines.append(_row("최종 판정", verdict_a[:60], verdict_b[:60]))

    lines += [
        "",
        "## 저장 파일",
        f"- 26b MD : `outputs/ai_analysis_26b.md`",
        f"- 26b HTML: `outputs/ai_analysis_26b.html`",
        f"- 31b MD : `outputs/ai_analysis_31b.md`",
        f"- 31b HTML: `outputs/ai_analysis_31b.html`",
        "",
        "## 동일 DATA FACTS 확인",
        "26b와 31b는 완전히 동일한 DATA FACTS를 사용했습니다.",
        "",
        "---",
        "*비교 리포트는 Ollama 없이 Python 코드로 생성 (deterministic)*",
    ]
    md_text = "\n".join(lines)
    md_path = os.path.join(_outputs_dir(), "ai_analysis_compare.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_text)

    # ── HTML 비교 리포트 ────────────────────────────────
    def _cell(v):
        return f"<td>{v}</td>"

    def _hrow(key, va, vb):
        return f"<tr><td class='lbl'>{key}</td>{_cell(va)}{_cell(vb)}</tr>"

    compare_css = _HTML_CSS + """
table.cmp{width:100%;border-collapse:collapse;margin:12px 0}
table.cmp th{background:#1a237e;color:#fff;padding:8px 12px;font-size:12px;text-align:left}
table.cmp td{padding:8px 12px;border-bottom:1px solid #eee;font-size:13px}
table.cmp td.lbl{font-weight:600;color:#444;width:160px}
.ok{color:#2e7d32;font-weight:600}
.err{color:#c62828;font-weight:600}
.warn{color:#e65100;font-weight:600}
.col-a{background:#f0f8ff}
.col-b{background:#fff8f0}
.box{background:#fff;border-radius:10px;padding:16px 20px;border:1px solid #dde3f0;
     box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:16px}
.section-title{font-size:12px;font-weight:700;color:#1a237e;text-transform:uppercase;
               letter-spacing:.4px;margin-bottom:10px}
"""

    def _styled(v):
        if v.startswith("✅"): return f'<span class="ok">{v}</span>'
        if v.startswith("❌"): return f'<span class="err">{v}</span>'
        if v.startswith("⚠"):  return f'<span class="warn">{v}</span>'
        return v

    def _crow(key, va, vb):
        return (f'<tr><td class="lbl">{key}</td>'
                f'<td class="col-a">{_styled(va)}</td>'
                f'<td class="col-b">{_styled(vb)}</td></tr>')

    facts_esc = data_facts.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Jason AI 분석 — A/B 비교</title>
<style>{compare_css}</style>
</head>
<body>
<h1 style="margin-top:0">📊 Jason AI A/B 비교 리포트</h1>
<div class="meta">{ts} — 동일 DATA FACTS 기반</div>

<div class="box">
<div class="section-title">실행 결과 비교</div>
<table class="cmp">
<thead>
  <tr>
    <th>항목</th>
    <th class="col-a">{res_a['model']}</th>
    <th class="col-b">{res_b['model']}</th>
  </tr>
</thead>
<tbody>
  {_crow("성공 여부", ok_a, ok_b)}
  {_crow("실행 시간", t_a, t_b)}
  {_crow("출력 길이(자)", str(len_a), str(len_b))}
  {_crow("금지 표현", "없음" if not forb_a else f"⚠ {', '.join(forb_a)}",
                      "없음" if not forb_b else f"⚠ {', '.join(forb_b)}")}
  {_crow("숫자 왜곡 의심", f"⚠ {nums_a[:2]}" if susp_a else "정상",
                            f"⚠ {nums_b[:2]}" if susp_b else "정상")}
  {_crow("최종 판정", verdict_a[:80], verdict_b[:80])}
</tbody>
</table>
</div>

<div class="box">
<div class="section-title">저장 파일</div>
<ul>
  <li>26b MD: outputs/ai_analysis_26b.md</li>
  <li>26b HTML: <a href="ai_analysis_26b.html">outputs/ai_analysis_26b.html</a></li>
  <li>31b MD: outputs/ai_analysis_31b.md</li>
  <li>31b HTML: <a href="ai_analysis_31b.html">outputs/ai_analysis_31b.html</a></li>
</ul>
</div>

<div class="box">
<div class="section-title">DATA FACTS (동일 기준)</div>
<pre class="facts">{facts_esc}</pre>
</div>
<p style="color:#888;font-size:11px;margin-top:16px">
  *비교 리포트는 Ollama 없이 Python 코드로 생성 (deterministic)*
</p>
</body>
</html>"""

    html_path = os.path.join(_outputs_dir(), "ai_analysis_compare.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return md_path, html_path


def run_ollama_ab_test(results: list, macro: dict, ts: str) -> dict:
    """
    Ollama gemma4:26b / gemma4:31b A/B 분석 실행.

    - 동일 DATA FACTS 사용
    - 각 모델 결과 저장
    - 비교 리포트 생성
    - 31b 실패해도 26b 결과 유지, 프로그램 종료 안 함
    - 반환: {'26b': res_a, '31b': res_b, 'data_facts': str}
    """
    import ollama_client as _oc

    print(f"\n{'━'*62}")
    print(f"  모드: {CYAN}로컬 LLM A/B 분석{RESET}")
    print(f"  모델 A: {_OLLAMA_MODELS[0]}")
    print(f"  모델 B: {_OLLAMA_MODELS[1]}")
    print(f"  keep_alive: {_oc.KEEP_ALIVE}")
    print(f"  API 비용 없음")
    print(f"{'━'*62}")

    # ── DATA FACTS 공통 생성 ──────────────────────────────
    data_facts = build_data_facts(results, macro)
    print(f"\n  DATA FACTS 구성 완료 ({len(data_facts)}자)")

    results_ab = {}
    for model, label in [(_OLLAMA_MODELS[0], "26b"), (_OLLAMA_MODELS[1], "31b")]:
        tag = "[A]" if label == "26b" else "[B]"
        print(f"\n  {tag} {model} 분석 중 (최대 {_oc.OLLAMA_TIMEOUT}s)...", flush=True)

        prompt = _build_ollama_prompt(data_facts, model)
        res    = _oc.generate(prompt, model)
        results_ab[label] = res

        if res['success']:
            _, forb = _oc.validate_output(res['text'])
            warn_s = f"  {AMBER}⚠ 금지 표현 감지: {forb}{RESET}" if forb else ""
            print(f"  {tag} {model} 완료 ({res['elapsed']}s, {len(res['text'])}자){warn_s}")
            # 저장
            md_path   = _save_result_md(res['text'], label)
            html_path = _save_result_html(res['text'], label, model, ts, data_facts)
            print(f"       MD  : {md_path}")
            print(f"       HTML: {html_path}")
        else:
            print(f"  {tag} {ALERT}{model} 실패: {res['error']}{RESET}")
            print(f"       → 기존 알고리즘 분석 fallback 유지")
            # 빈 파일 저장 (오류 기록)
            err_text = f"# {model} 분석 실패\n\n오류: {res['error']}\n실행 시간: {res['elapsed']}s"
            _save_result_md(err_text, label)

    # ── 비교 리포트 ──────────────────────────────────────
    res_a = results_ab.get("26b", {"success": False, "text": "", "error": "실행 안 됨",
                                    "elapsed": 0, "model": _OLLAMA_MODELS[0]})
    res_b = results_ab.get("31b", {"success": False, "text": "", "error": "실행 안 됨",
                                    "elapsed": 0, "model": _OLLAMA_MODELS[1]})

    md_cmp, html_cmp = _save_compare(res_a, res_b, data_facts, ts)
    print(f"\n  비교 리포트 MD  : {md_cmp}")
    print(f"  비교 리포트 HTML: {html_cmp}")
    webbrowser.open(f"file://{html_cmp}")

    return {"26b": res_a, "31b": res_b, "data_facts": data_facts}


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

    # ── 분석 모드 감지 ────────────────────────────────────
    try:
        import ollama_client as _oc
        _ollama_ok = _oc.is_available()
    except ImportError:
        _ollama_ok = False

    has_groq = bool(os.getenv('GROQ_API_KEY', '').strip())

    if not _ollama_ok:
        # Ollama 없을 때 기존 모드 표시
        mode = (f"{CYAN}Groq Llama-3.3-70B (무료 AI){RESET}" if has_groq
                else f"{AMBER}알고리즘 분석 (API 불필요){RESET}")
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

    # ── Ollama A/B 테스트 (가능할 때) ────────────────────────
    if _ollama_ok:
        run_ollama_ab_test(results, macro, ts)

    # ── 기존 Groq / 알고리즘 분석 (항상 실행, fallback 역할) ─
    print(f"\n  {'─'*56}")
    print(f"  기존 분석 실행 중 ({'Groq AI' if has_groq else '알고리즘 fallback'})...")
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
