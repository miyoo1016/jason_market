#!/usr/bin/env python3
"""종합 자동 분석 (AI) - Jason Market
인베스팅닷컴 스타일의 종합 마켓 리포트"""

import os
import webbrowser
import yfinance as yf
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from xlsx_sync import load_portfolio

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

ALERT = '\033[38;5;203m'  # 연한 빨간색 (극단 경고에만)
RESET = '\033[0m'

EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

ASSETS = {
    'Bitcoin    ': ('BTC-USD',   'crypto'),
    'Gold       ': ('GC=F',      'commodity'),
    'Brent유    ': ('BZ=F',      'commodity'),
    'WTI원유    ': ('CL=F',      'commodity'),
    '다우선물    ': ('YM=F',      'futures'),
    'S&P선물    ': ('ES=F',      'futures'),
    '나스닥선물  ': ('NQ=F',      'futures'),
    'Russell    ': ('RTY=F',     'futures'),
    'Google     ': ('GOOGL',     'stock'),
    'Nasdaq QQQM': ('QQQM',      'etf'),
    'S&P500 SPY ': ('SPY',       'etf'),
    'Samsung    ': ('005930.KS', 'krstock'),
    '달러/원    ': ('USDKRW=X',  'fx'),
    '미국10년물  ': ('^TNX',      'index'),
    'VIX        ': ('^VIX',      'index'),
    '코스피      ': ('^KS11',    'krindex'),
}

# ── 데이터 수집 ──────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else None

def get_asset_snapshot(name, ticker, asset_type):
    try:
        hist = yf.Ticker(ticker).history(period='6mo')
        if hist.empty or len(hist) < 10:
            return None

        close = hist['Close']
        curr  = float(close.iloc[-1])
        prev  = float(close.iloc[-2])
        pct_1d = (curr - prev) / prev * 100

        # 1주/1달 수익률
        w1  = float(close.iloc[-5])  if len(close) >= 5  else None
        m1  = float(close.iloc[-21]) if len(close) >= 21 else None
        pct_1w = (curr - w1) / w1 * 100  if w1  else None
        pct_1m = (curr - m1) / m1 * 100  if m1  else None

        # MA
        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        # RSI
        rsi = calc_rsi(close)

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_val = float((ema12 - ema26).iloc[-1])
        sig_val  = float((ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1])
        macd_dir = "양" if macd_val > sig_val else "음"

        # 볼린저 위치
        ma20_ser = close.rolling(20).mean()
        std_ser  = close.rolling(20).std()
        bb_u = ma20_ser.iloc[-1] + 2 * std_ser.iloc[-1]
        bb_l = ma20_ser.iloc[-1] - 2 * std_ser.iloc[-1]
        bb_w = bb_u - bb_l
        pct_b = (curr - float(bb_l)) / float(bb_w) * 100 if bb_w > 0 else 50

        # 52주 고저
        hist_1y = yf.Ticker(ticker).history(period='1y')
        if not hist_1y.empty:
            h52 = float(hist_1y['High'].max())
            l52 = float(hist_1y['Low'].min())
            pos52 = (curr - l52) / (h52 - l52) * 100 if h52 != l52 else 50
        else:
            h52 = l52 = pos52 = None

        return {
            'name': name.strip(),
            'ticker': ticker,
            'type': asset_type,
            'curr': curr,
            'pct_1d': pct_1d,
            'pct_1w': pct_1w,
            'pct_1m': pct_1m,
            'ma20': ma20,
            'ma50': ma50,
            'rsi': rsi,
            'macd_dir': macd_dir,
            'pct_b': pct_b,
            'pos52': pos52,
            'h52': h52,
            'l52': l52,
        }
    except Exception as e:
        print(f"  ⚠ {name.strip()} 수집 실패: {e}")
        return None

def fmt_price(r):
    if r['type'] == 'crypto':
        return f"${r['curr']:,.0f}"
    elif r['type'] == 'commodity':
        return f"${r['curr']:,.1f}"
    elif r['type'] == 'futures':
        return f"{r['curr']:,.1f}"
    elif r['type'] == 'krstock':
        return f"₩{r['curr']:,.0f}"
    elif r['type'] == 'fx':
        return f"₩{r['curr']:,.1f}"
    elif r['type'] == 'index':
        return f"{r['curr']:,.2f}"
    elif r['type'] == 'krindex':
        return f"{r['curr']:,.2f}"
    else:
        return f"${r['curr']:,.2f}"

def fmt_pct(val):
    if val is None:
        return 'N/A'
    return f"{val:+.2f}%"

# ── AI 분석 ──────────────────────────────────────────────

def get_portfolio_text():
    try:
        holdings = load_portfolio()
        if not holdings:
            return ""
        lines = []
        for h in holdings:
            if h.get('is_cash'):
                cur = h.get('currency', 'KRW')
                sym = '₩' if cur == 'KRW' else '$'
                lines.append(f"{h['name']}({h.get('account','')}) {sym}{h['avg_price']:,.0f} 현금")
            else:
                qty = h.get('qty', 0)
                avg = h.get('avg_price', 0)
                cur = h.get('currency', 'KRW')
                sym = '$' if cur == 'USD' else '₩'
                lines.append(f"{h['name']}({h.get('account','')}) {qty}주@{sym}{avg:,.2f}")
        return "Jason 실제 보유: " + ", ".join(lines)
    except Exception:
        return ""

def call_ai(data_text):
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("\n⚠ ANTHROPIC_API_KEY 없음 → AI 분석 생략")
        return None

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key.strip())
    except Exception as e:
        print(f"\n⚠ Claude 초기화 실패: {e}")
        return None

    portfolio_ctx = get_portfolio_text()
    system = f"""당신은 월가 경력 30년의 퀀트 펀드매니저입니다.
Jason은 한국 개인투자자입니다.
{portfolio_ctx}
팩트 기반으로 간결하게, 한국어로 분석하세요."""

    prompt = f"""[Jason 포트폴리오 일일 리포트 - {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}]

{data_text}

다음 순서로 분석해주세요:

## 1. 오늘의 시장 요약 (3줄)
전체 시장 분위기와 핵심 이슈를 3줄로 요약

## 2. 자산별 진단
각 자산의 현재 상태를 한 줄씩 (매수/매도/관망 + 이유)

## 3. 리스크 체크
현재 가장 주의해야 할 위험 요소 2가지

## 4. 단기 전략 (2-4주)
구체적인 대응 방향 제시

## 5. 핵심 레벨
각 자산의 단기 지지/저항 핵심 레벨 1개씩

전체 500자 이내로 간결하게."""

    try:
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1200,
            system=system,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return resp.content[0].text
    except Exception as e:
        print(f"\n⚠ AI 분석 오류: {e}")
        return None

# ── HTML 생성 ────────────────────────────────────────────

def generate_html(results, ai_text, timestamp):
    """종합 자동 분석 결과를 다크 테마 HTML 파일로 저장하고 브라우저로 연다."""
    if not results:
        return

    def c_pct(val):
        if val is None:
            return '#888888'
        return '#2ecc71' if val >= 0 else '#e74c3c'

    def fmt_pct_html(val):
        if val is None:
            return '<span style="color:#888">N/A</span>'
        color = c_pct(val)
        return f'<span style="color:{color};font-weight:600">{val:+.2f}%</span>'

    def c_rsi(val):
        if val is None:
            return '#888888'
        if val >= 70:
            return '#e74c3c'
        if val <= 30:
            return '#2ecc71'
        return '#3498db'

    def fmt_rsi(val):
        if val is None:
            return '<span style="color:#888">N/A</span>'
        color = c_rsi(val)
        label = '과매수' if val >= 70 else '과매도' if val <= 30 else '중립'
        return f'<span style="color:{color};font-weight:600">{val:.1f} <small>({label})</small></span>'

    # Price summary table rows
    price_rows = ''
    for r in results:
        price_rows += f'''
        <tr>
          <td class="name-col">{r['name']}</td>
          <td class="num-col">{fmt_price(r)}</td>
          <td class="num-col">{fmt_pct_html(r['pct_1d'])}</td>
          <td class="num-col">{fmt_pct_html(r['pct_1w'])}</td>
          <td class="num-col">{fmt_pct_html(r['pct_1m'])}</td>
        </tr>'''

    # Technical summary table rows
    tech_rows = ''
    for r in results:
        macd_str = '<span style="color:#2ecc71">▲ 양전환</span>' if r['macd_dir'] == '양' else '<span style="color:#e74c3c">▼ 음전환</span>'
        pctb_val = r['pct_b']
        if pctb_val > 80:
            pctb_str = f'<span style="color:#e74c3c;font-weight:600">{pctb_val:.0f}% 과열</span>'
        elif pctb_val < 20:
            pctb_str = f'<span style="color:#2ecc71;font-weight:600">{pctb_val:.0f}% 침체</span>'
        else:
            pctb_str = f'<span style="color:#3498db">{pctb_val:.0f}%</span>'
        pos52_str = f'{r["pos52"]:.0f}%' if r['pos52'] is not None else 'N/A'
        tech_rows += f'''
        <tr>
          <td class="name-col">{r['name']}</td>
          <td class="num-col">{fmt_rsi(r['rsi'])}</td>
          <td class="num-col">{macd_str}</td>
          <td class="num-col">{pctb_str}</td>
          <td class="num-col">{pos52_str}</td>
        </tr>'''

    ai_section = ''
    if ai_text:
        escaped = ai_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        ai_section = f'''
    <div class="ai-box">
      <div class="ai-title">Claude AI 종합 분석 <span class="ai-sub">(Claude Haiku)</span></div>
      <pre class="ai-body">{escaped}</pre>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Jason 종합 자동 분석</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #1a1a2e; color: #dde; font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; }}
h1 {{ font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 4px; }}
.ts {{ font-size: 12px; color: #556; margin-bottom: 24px; }}
.section {{ background: #141722; border-radius: 10px; padding: 20px; border: 1px solid #252838; margin-bottom: 20px; }}
.section-title {{ font-size: 14px; font-weight: 700; color: #9aa; margin-bottom: 14px; text-transform: uppercase; letter-spacing: 0.5px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ font-size: 11px; color: #667; text-align: right; padding: 6px 10px; border-bottom: 1px solid #252838; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }}
th.name-col {{ text-align: left; }}
td {{ font-size: 13px; padding: 7px 10px; border-bottom: 1px solid #1c1f2e; text-align: right; }}
td.name-col {{ text-align: left; color: #ccd; font-weight: 600; }}
td.num-col {{ font-variant-numeric: tabular-nums; }}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: #1c1f2e; }}
.ai-box {{ background: #141722; border-radius: 10px; padding: 20px; border-left: 3px solid #3498db; margin-bottom: 20px; }}
.ai-title {{ font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 12px; }}
.ai-sub {{ font-size: 12px; font-weight: 400; color: #667; margin-left: 8px; }}
.ai-body {{ font-size: 13px; line-height: 1.9; color: #ccd; white-space: pre-wrap; word-break: break-word; background: #0d0f18; border-radius: 6px; padding: 16px; }}
.copy-btn {{ position: fixed; bottom: 24px; right: 24px; background: #3498db; color: #fff; border: none; border-radius: 8px; padding: 10px 18px; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.4); transition: background 0.15s; z-index: 100; }}
.copy-btn:hover {{ background: #2980b9; }}
.copy-btn.done {{ background: #2ecc71; }}
</style>
</head>
<body>
<h1>Jason 종합 자동 분석</h1>
<div class="ts">{timestamp}</div>

<div class="section">
  <div class="section-title">시세 요약</div>
  <table>
    <thead>
      <tr>
        <th class="name-col">자산</th>
        <th>현재가</th>
        <th>1일%</th>
        <th>1주%</th>
        <th>1달%</th>
      </tr>
    </thead>
    <tbody>{price_rows}
    </tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">기술지표 요약</div>
  <table>
    <thead>
      <tr>
        <th class="name-col">자산</th>
        <th>RSI</th>
        <th>MACD방향</th>
        <th>볼린저%B</th>
        <th>52주위치%</th>
      </tr>
    </thead>
    <tbody>{tech_rows}
    </tbody>
  </table>
</div>
{ai_section}

<button class="copy-btn" id="copyBtn" onclick="copyText()">📋 AI 분석 복사</button>
<script>
const AI_TEXT = {repr(ai_text if ai_text else '')};
function copyText() {{
  if (!AI_TEXT) {{ alert('AI 분석 결과가 없습니다.'); return; }}
  navigator.clipboard.writeText(AI_TEXT).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✅ 복사 완료!';
    btn.classList.add('done');
    setTimeout(() => {{
      btn.textContent = '📋 AI 분석 복사';
      btn.classList.remove('done');
    }}, 2500);
  }}).catch(() => alert('복사 실패 — AI 분석 텍스트를 직접 선택하세요.'));
}}
</script>
</body>
</html>'''

    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(base_dir, 'auto_analysis.html')
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"\n  HTML 저장: {out_path}")
        webbrowser.open(f'file://{out_path}')
        print(f"  브라우저 열림\n")
    except Exception as e:
        print(f"\n  ⚠ HTML 저장 실패: {e}\n")


# ── 메인 ─────────────────────────────────────────────────

def main():
    print(f"\n{'━'*62}")
    print(f"  Jason 종합 자동 분석 리포트")
    print(f"  {datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}")
    print(f"{'━'*62}")
    print("  데이터 수집 중 (약 20-30초)...\n")

    results = []
    for name, (ticker, asset_type) in ASSETS.items():
        r = get_asset_snapshot(name, ticker, asset_type)
        if r:
            results.append(r)

    if not results:
        print("⚠ 데이터 수집 실패. 인터넷 연결을 확인하세요.")
        return

    # ── 시세 요약 테이블 ──────────────────────────
    print(f"  {'─'*58}")
    print(f"  {'자산':<14} {'현재가':>12} {'일간':>8} {'1주':>8} {'1달':>8}")
    print(f"  {'─'*58}")

    data_lines = []
    for r in results:
        print(f"  {r['name']:<14} {fmt_price(r):>12} "
              f"{fmt_pct(r['pct_1d']):>8} "
              f"{fmt_pct(r['pct_1w']):>8} "
              f"{fmt_pct(r['pct_1m']):>8}")

        # AI 분석용 텍스트
        rsi_str  = f"{r['rsi']:.1f}" if r['rsi'] else 'N/A'
        ma_status = []
        if r['ma20'] and r['curr'] > r['ma20']: ma_status.append('MA20위')
        if r['ma50'] and r['curr'] > r['ma50']: ma_status.append('MA50위')
        pos52_str = f"{r['pos52']:.0f}%" if r['pos52'] else 'N/A'
        data_lines.append(
            f"- {r['name']}: {fmt_price(r)} | 1일{r['pct_1d']:+.1f}% 1주{r['pct_1w']:+.1f}% 1달{r['pct_1m']:+.1f}% | "
            f"RSI={rsi_str} MACD={r['macd_dir']}전환 | "
            f"MA상태=[{' '.join(ma_status) or '모두하위'}] | 52주위치={pos52_str}"
        )

    print(f"  {'─'*58}")

    # ── 기술지표 요약 ──────────────────────────────
    print(f"\n  기술지표 요약")
    print(f"  {'─'*58}")
    print(f"  {'자산':<14} {'RSI':>6} {'MACD':>8} {'볼린저':>8} {'52주위치':>8}")
    print(f"  {'─'*58}")
    for r in results:
        rsi_str = f"{r['rsi']:.0f}" if r['rsi'] else 'N/A'
        macd_str = '양전환' if r['macd_dir'] == '양' else '음전환'
        pctb_str = f"{r['pct_b']:>7.0f}%"
        pos_str = f"{r['pos52']:>7.0f}%" if r['pos52'] else ''

        print(f"  {r['name']:<14} "
              f"{rsi_str:>6} "
              f"{macd_str:>8} "
              f"{pctb_str} "
              f"{pos_str}")

    # ── AI 분석 ────────────────────────────────────
    data_text = '\n'.join(data_lines)
    analysis = call_ai(data_text)

    timestamp = datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')

    if analysis:
        print(f"\n{'━'*62}")
        print(f"  Claude AI 종합 분석")
        print(f"{'━'*62}")
        print(analysis)
        print(f"{'━'*62}")

        # 텍스트 파일 저장
        today = datetime.now().strftime('%Y%m%d_%H%M')
        fname = f"analysis_{today}.txt"
        try:
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(f"Jason 마켓 분석 리포트 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write("="*60 + "\n\n")
                f.write("[시세 데이터]\n")
                f.write(data_text.replace('\n', '\n') + "\n\n")
                f.write("[AI 분석]\n")
                f.write(analysis)
            print(f"\n  분석 결과 저장: {fname}\n")
        except Exception:
            pass
    else:
        print()

    # HTML 저장 및 브라우저 열기
    generate_html(results, analysis or '', timestamp)

if __name__ == '__main__':
    main()
