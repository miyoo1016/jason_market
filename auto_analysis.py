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

# 삼파전 비교 모델 (A / B / C)
_OLLAMA_MODELS = ["gemma4:26b", "gemma4:31b", "qwen3.6:latest"]
_OLLAMA_LABELS = {"gemma4:26b": "26b", "gemma4:31b": "31b", "qwen3.6:latest": "qwen36"}
_OLLAMA_TAGS   = {"gemma4:26b": "[A]", "gemma4:31b": "[B]", "qwen3.6:latest": "[C]"}

_OLLAMA_SYSTEM = """너는 Jason의 기존 9번 표를 해석하는 로컬 AI 분석 보조자다.
매수/매도 추천자가 아니다.

분석 기준:
- 시세 요약의 일간/1주/1달 흐름을 비교한다.
- 기술지표는 과열/침체/주의 관점으로만 해석한다. 매수/매도 신호로 단정하지 않는다.
- RSI 과매수는 바로 매도 신호가 아니다. MACD 양전환은 바로 매수 신호가 아니다.
- 볼린저 상단 근접은 과열 또는 변동성 확대 신호로만 본다.
- 52주 위치가 높으면 장기 강세와 과열 가능성을 함께 본다.
- VIX, DXY, US10Y, USDKRW는 거시 부담/완충 요인으로 해석한다.
- CD금리 상품은 현금성 자산으로 분류한다.
- 숫자는 DATA FACTS 기준만 사용한다. 새 숫자를 만들지 않는다.
- 금지 표현: 강력 매수, 강력 매도, 지금 사야, 지금 팔아야, 확정 상승, 확정 하락, 폭락 확정, 수익 보장, 투자 추천.

다음 형식으로 한국어로 분석하라. 각 섹션은 지정된 줄 수를 넘지 않는다.

# Jason 종합 AI 분석

## 1. 시세 흐름 요약
(5줄 이내: 일간/1주/1달 흐름, 충돌 자산)

## 2. 기술지표 해석
(5줄 이내: 과열/중립/침체권, MACD, 볼린저%B·52주 위험도)

## 3. 거시지표 해석
(5줄 이내: VIX/DXY/US10Y/USDKRW의 부담·완충 요인)

## 4. 리스크 체크
(5개 bullet 이내)

## 5. 하지 말아야 할 것
(4개 bullet 이내, 매수/매도 판단하지 않기 포함)

## 6. 한 줄 판정
주의 / 중립 / 양호 중 하나를 선택하고 이유를 한 문장으로 설명."""


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
    """DATA FACTS + 시스템 역할 합성 → 최종 Ollama 프롬프트.
    세 모델 모두 동일한 DATA FACTS와 동일한 프롬프트 구조를 사용한다."""
    return (
        f"{_OLLAMA_SYSTEM}\n\n"
        f"DATA FACTS (아래 숫자 이외의 수치는 사용하지 말 것):\n"
        f"{'─'*60}\n"
        f"{data_facts}\n"
        f"{'─'*60}\n\n"
        f"위 DATA FACTS를 기반으로 분석하라."
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


def _save_compare(res_a: dict, res_b: dict, res_c: dict,
                  data_facts: str, ts: str) -> tuple:
    """비교 리포트 MD + HTML 저장 → (md_path, html_path)."""
    import ollama_client as _oc

    # ── 3모델 데이터 준비 ────────────────────────────────
    all_res   = [res_a, res_b, res_c]
    ok_strs   = []
    t_strs    = []
    len_strs  = []
    forb_strs = []
    susp_strs = []
    verd_strs = []
    pros_list = []
    cons_list = []

    for res in all_res:
        ok_strs.append("✅ 성공" if res['success']
                        else f"❌ 실패 ({res.get('error','?')[:35]})")
        t_strs.append(f"{res.get('elapsed',0):.1f}s")
        len_strs.append(str(len(res.get('text',''))))
        _, forb = _oc.validate_output(res.get('text',''))
        forb_strs.append("없음" if not forb else f"⚠ {', '.join(forb)}")
        susp, nums = _oc.check_number_distortion(data_facts, res.get('text',''))
        susp_strs.append(f"⚠ {nums[:2]}" if susp else "정상")
        verd_strs.append((_oc.extract_verdict(res.get('text','')) or "—")[:55])
        pros, cons = _oc.memo_quality(res)
        pros_list.append(pros); cons_list.append(cons)

    # ── MD 비교 리포트 ─────────────────────────────────
    hdr = " | ".join(r['model'] for r in all_res)
    sep = "|".join(["----------"] * 3)
    def _row3(key, *vals):
        return f"| {key} | " + " | ".join(v[:50] for v in vals) + " |"

    lines = [
        "# Jason AI 분석 — 삼파전 비교 리포트",
        f"생성 시각: {ts}",
        "",
        "## 실행 결과",
        "",
        f"| 항목 | {hdr} |",
        f"|------|{sep}|",
        _row3("성공 여부",    *ok_strs),
        _row3("실행 시간",    *t_strs),
        _row3("출력 길이(자)", *len_strs),
        _row3("금지 표현",    *forb_strs),
        _row3("숫자 왜곡 의심", *susp_strs),
        _row3("한 줄 판정",   *verd_strs),
        _row3("장점",         *pros_list),
        _row3("단점",         *cons_list),
        "",
        "## 저장 파일",
        "- 26b MD : `outputs/ai_analysis_26b.md`",
        "- 26b HTML: `outputs/ai_analysis_26b.html`",
        "- 31b MD : `outputs/ai_analysis_31b.md`",
        "- 31b HTML: `outputs/ai_analysis_31b.html`",
        "- qwen36 MD : `outputs/ai_analysis_qwen36.md`",
        "- qwen36 HTML: `outputs/ai_analysis_qwen36.html`",
        "",
        "## 동일 DATA FACTS 확인",
        "세 모델 모두 완전히 동일한 DATA FACTS와 동일한 프롬프트를 사용했습니다.",
        "",
        "---",
        "*비교 리포트는 Ollama 없이 Python 코드로 생성 (deterministic)*",
    ]
    md_text = "\n".join(lines)
    md_path = os.path.join(_outputs_dir(), "ai_analysis_compare.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_text)

    # ── HTML 비교 리포트 ────────────────────────────────
    compare_css = _HTML_CSS + """
table.cmp{width:100%;border-collapse:collapse;margin:12px 0}
table.cmp th{background:#1a237e;color:#fff;padding:8px 12px;font-size:12px;text-align:left}
table.cmp td{padding:8px 12px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}
table.cmp td.lbl{font-weight:600;color:#444;width:140px;white-space:nowrap}
.ok{color:#2e7d32;font-weight:600}
.err{color:#c62828;font-weight:600}
.warn{color:#e65100;font-weight:600}
.col-a{background:#f0f8ff}
.col-b{background:#fff8f0}
.col-c{background:#f8f0ff}
.box{background:#fff;border-radius:10px;padding:16px 20px;border:1px solid #dde3f0;
     box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:16px}
.section-title{font-size:12px;font-weight:700;color:#1a237e;text-transform:uppercase;
               letter-spacing:.4px;margin-bottom:10px}
"""

    def _styled(v: str) -> str:
        if v.startswith("✅"): return f'<span class="ok">{v}</span>'
        if v.startswith("❌"): return f'<span class="err">{v}</span>'
        if v.startswith("⚠"):  return f'<span class="warn">{v}</span>'
        return v

    def _crow3(key, va, vb, vc):
        return (f'<tr><td class="lbl">{key}</td>'
                f'<td class="col-a">{_styled(va)}</td>'
                f'<td class="col-b">{_styled(vb)}</td>'
                f'<td class="col-c">{_styled(vc)}</td></tr>')

    facts_esc = data_facts.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    ma, mb, mc = all_res[0]['model'], all_res[1]['model'], all_res[2]['model']

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Jason AI 삼파전 비교</title>
<style>{compare_css}</style>
</head>
<body>
<h1 style="margin-top:0">📊 Jason AI 삼파전 비교 리포트</h1>
<div class="meta">{ts} — 동일 DATA FACTS 기반 | API 비용 없음</div>

<div class="box">
<div class="section-title">실행 결과 비교</div>
<table class="cmp">
<thead>
  <tr>
    <th>항목</th>
    <th class="col-a">{ma}</th>
    <th class="col-b">{mb}</th>
    <th class="col-c">{mc}</th>
  </tr>
</thead>
<tbody>
  {_crow3("성공 여부",    *ok_strs)}
  {_crow3("실행 시간",    *t_strs)}
  {_crow3("출력 길이(자)", *len_strs)}
  {_crow3("금지 표현",    *forb_strs)}
  {_crow3("숫자 왜곡",   *susp_strs)}
  {_crow3("한 줄 판정",   *verd_strs)}
  {_crow3("장점",         *pros_list)}
  {_crow3("단점",         *cons_list)}
</tbody>
</table>
</div>

<div class="box">
<div class="section-title">저장 파일</div>
<ul>
  <li>26b: <a href="ai_analysis_26b.html">ai_analysis_26b.html</a> /
           <a href="ai_analysis_26b.md">ai_analysis_26b.md</a></li>
  <li>31b: <a href="ai_analysis_31b.html">ai_analysis_31b.html</a> /
           <a href="ai_analysis_31b.md">ai_analysis_31b.md</a></li>
  <li>qwen36: <a href="ai_analysis_qwen36.html">ai_analysis_qwen36.html</a> /
              <a href="ai_analysis_qwen36.md">ai_analysis_qwen36.md</a></li>
</ul>
</div>

<div class="box">
<div class="section-title">DATA FACTS (세 모델 공통 입력)</div>
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


def run_ollama_triple_test(results: list, macro: dict, ts: str) -> dict:
    """
    Ollama 삼파전: gemma4:26b / gemma4:31b / qwen3.6:latest 동시 비교.

    - 세 모델 모두 동일한 DATA FACTS + 동일한 프롬프트 사용
    - 한 모델 실패해도 나머지 계속 실행
    - 결과 파일 + 비교 리포트 저장
    - 반환: {'26b': res, '31b': res, 'qwen36': res, 'data_facts': str}
    """
    import ollama_client as _oc

    print(f"\n{'━'*62}")
    print(f"  모드: {CYAN}로컬 LLM 삼파전 비교{RESET}")
    for i, m in enumerate(_OLLAMA_MODELS):
        tag = chr(65 + i)  # A, B, C
        print(f"  모델 {tag}: {m}  (timeout={_oc.MODEL_TIMEOUTS.get(m, _oc.DEFAULT_TIMEOUT)}s)")
    print(f"  keep_alive: {_oc.KEEP_ALIVE}")
    print(f"  temperature: {_oc.DEFAULT_OPTIONS.get('temperature', 0.2)}")
    print(f"  출력 길이: 프롬프트 지시로 제어 (thinking 토큰 호환)")
    print(f"  API 비용 없음")
    print(f"{'━'*62}")

    # ── DATA FACTS 공통 생성 (세 모델 동일) ──────────────
    data_facts = build_data_facts(results, macro)
    prompt     = _build_ollama_prompt(data_facts, "")   # 모델명 대입 없음
    print(f"\n  DATA FACTS 구성 완료 ({len(data_facts)}자)")
    print(f"  프롬프트 총 길이: {len(prompt)}자")
    print(f"  (세 모델 모두 동일한 DATA FACTS + 프롬프트 사용)")

    results_map = {}
    for model in _OLLAMA_MODELS:
        label = _OLLAMA_LABELS[model]
        tag   = _OLLAMA_TAGS[model]
        _timeout = _oc.MODEL_TIMEOUTS.get(model, _oc.DEFAULT_TIMEOUT)

        print(f"\n  {tag} {model} 분석 중 (최대 {_timeout}s)...", flush=True)

        res = _oc.generate(prompt, model)
        results_map[label] = res

        if res['success']:
            _, forb = _oc.validate_output(res['text'])
            verdict = _oc.extract_verdict(res['text'])
            warn_s  = f"  {AMBER}⚠ 금지 표현: {forb}{RESET}" if forb else ""
            print(f"  {tag} 완료  {res['elapsed']}s  {len(res['text'])}자  판정: {verdict}{warn_s}")
            md_path   = _save_result_md(res['text'], label)
            html_path = _save_result_html(res['text'], label, model, ts, data_facts)
            print(f"       MD  : {md_path}")
            print(f"       HTML: {html_path}")
        else:
            print(f"  {tag} {ALERT}{model} 실패: {res['error']}{RESET}")
            print(f"       → 결과 파일에 실패 사유 기록, 다음 모델 계속 실행")
            err_text = (f"# {model} 분석 실패\n\n"
                        f"오류: {res['error']}\n"
                        f"실행 시간: {res['elapsed']}s\n"
                        f"keep_alive: {_oc.KEEP_ALIVE}\n"
                        f"timeout 설정: {_timeout}s\n")
            _save_result_md(err_text, label)
            # 빈 HTML도 생성
            _save_result_html(err_text, label, model, ts, data_facts)

    # ── 비교 리포트 ──────────────────────────────────────
    _empty = lambda m: {"success": False, "text": "", "error": "실행 안 됨",
                         "elapsed": 0, "model": m}
    res_a = results_map.get("26b",    _empty(_OLLAMA_MODELS[0]))
    res_b = results_map.get("31b",    _empty(_OLLAMA_MODELS[1]))
    res_c = results_map.get("qwen36", _empty(_OLLAMA_MODELS[2]))

    md_cmp, html_cmp = _save_compare(res_a, res_b, res_c, data_facts, ts)
    print(f"\n  비교 리포트 MD  : {md_cmp}")
    print(f"  비교 리포트 HTML: {html_cmp}")
    webbrowser.open(f"file://{html_cmp}")

    return {"26b": res_a, "31b": res_b, "qwen36": res_c, "data_facts": data_facts}


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

    # ── Ollama 삼파전 비교 (가능할 때) ───────────────────────
    if _ollama_ok:
        run_ollama_triple_test(results, macro, ts)

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
