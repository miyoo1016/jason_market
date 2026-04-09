#!/usr/bin/env python3
"""
Jason Market 멀티에이전트 투자 분석 시스템
6개의 AI 에이전트가 서로 토론하며 최적의 투자 판단을 도출합니다.

사용법:
  python3 multi_agent_analyst.py "BTC 지금 매수해야 해?"
  python3 multi_agent_analyst.py   (대화형 모드)
"""

import os, sys, threading, webbrowser
import html as html_lib
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv
from xlsx_sync import load_portfolio

_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env, override=True)

try:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', '').strip())
except Exception as e:
    print(f"오류: Anthropic 초기화 실패 - {e}")
    sys.exit(1)

ALERT = '\033[38;5;203m'  # 연한 빨간색 (극단 경고에만)
RESET = '\033[0m'

EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

FAST  = 'claude-haiku-4-5-20251001'
SMART = 'claude-sonnet-4-6'

PORTFOLIO = {
    'Bitcoin':  'BTC-USD',  '금(COMEX)': 'GC=F',
    'Google':   'GOOGL',    'Nasdaq':  'QQQM',
    'S&P500':   'SPY',      'Samsung': '005930.KS',
    '브렌트유(ICE)': 'BZ=F', 'WTI원유(NYMEX)': 'CL=F',
    '다우지수(CME)': 'YM=F', 'S&P500(CME)': 'ES=F',
    '나스닥100(CME)':'NQ=F', '러셀2000(CME)': 'RTY=F',
    '코스피': '^KS11',
}

EXTREME_KEYWORDS = ['강력매도', '즉시청산', '매우높음', '극도공포', '극도탐욕', '강력매수']

# ── 지표 계산 ──────────────────────────────────────────────

def calc_rsi(prices, period=14):
    delta = prices.diff()
    gain  = delta.where(delta > 0, 0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0

def calc_macd(prices):
    e12 = prices.ewm(span=12).mean()
    e26 = prices.ewm(span=26).mean()
    macd = e12 - e26
    signal = macd.ewm(span=9).mean()
    return float(macd.iloc[-1]), float(signal.iloc[-1]), float((macd - signal).iloc[-1])

def calc_bb(prices, period=20):
    ma  = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    upper = (ma + 2*std).iloc[-1]
    lower = (ma - 2*std).iloc[-1]
    curr  = float(prices.iloc[-1])
    pct_b = (curr - float(lower)) / (float(upper) - float(lower)) if float(upper) != float(lower) else 0.5
    return float(upper), float(ma.iloc[-1]), float(lower), round(pct_b, 3)

def get_news_titles(ticker, n=3):
    try:
        news = yf.Ticker(ticker).news or []
        out  = []
        for item in news[:n]:
            c = item.get('content', item)
            t = (c.get('title') or item.get('title') or '').strip()
            if t:
                out.append(t)
        return out
    except Exception:
        return []

# ── 데이터 수집 ───────────────────────────────────────────

def build_portfolio_summary():
    """xlsx에서 실제 보유 현황 텍스트 생성 (AI 프롬프트용)"""
    try:
        holdings = load_portfolio()
        if not holdings:
            return ""
        lines = []
        for h in holdings:
            if h.get('is_cash'):
                cur = h.get('currency', 'KRW')
                sym = '₩' if cur == 'KRW' else '$'
                lines.append(f"  {h['name']}({h.get('account','')}) : {sym}{h['avg_price']:,.0f} [{cur} 현금]")
            else:
                qty = h.get('qty', 0)
                avg = h.get('avg_price', 0)
                cur = h.get('currency', 'KRW')
                sym = '$' if cur == 'USD' else '₩'
                lines.append(f"  {h['name']}({h.get('account','')}) : {qty}주 @ {sym}{avg:,.2f}")
        return "[Jason 실제 보유 포트폴리오]\n" + "\n".join(lines)
    except Exception:
        return ""

def collect_data():
    print("  데이터 수집 중...", end='\r')
    data = {'prices': {}, 'technicals': {}, 'macro': {}, 'news': {}}

    for name, ticker in PORTFOLIO.items():
        try:
            hist = yf.Ticker(ticker).history(period='3mo')
            if hist.empty:
                continue
            curr = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2])
            pct  = (curr - prev) / prev * 100
            data['prices'][name] = {'price': curr, 'change_pct': round(pct, 2)}
            if name in ('Bitcoin', 'S&P500', 'Google', 'Nasdaq'):
                close = hist['Close']
                rsi   = calc_rsi(close)
                _, _, hist_val = calc_macd(close)
                _, _, _, pct_b = calc_bb(close)
                ma50  = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
                data['technicals'][name] = {
                    'rsi': round(rsi, 1), 'macd_hist': round(hist_val, 4),
                    'bb_pct_b': pct_b, 'price': curr,
                    'ma50': round(ma50, 2) if ma50 else None,
                }
        except Exception:
            pass

    for name, ticker in {'VIX': '^VIX', 'DXY': 'DX-Y.NYB', 'US10Y': '^TNX', 'USDKRW': 'USDKRW=X', 'Brent': 'BZ=F', 'WTI': 'CL=F'}.items():
        try:
            hist = yf.Ticker(ticker).history(period='5d')
            if not hist.empty:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                data['macro'][name] = {'value': round(curr, 3), 'change_pct': round((curr - prev) / prev * 100, 2)}
        except Exception:
            pass

    for name, ticker in [('Bitcoin', 'BTC-USD'), ('S&P500', 'SPY'), ('Google', 'GOOGL')]:
        titles = get_news_titles(ticker)
        if titles:
            data['news'][name] = titles

    print("  데이터 수집 완료.                  ")
    return data

# ── Claude 호출 ───────────────────────────────────────────

def call_agent(system, user, model=FAST, max_tokens=300):
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{'role': 'user', 'content': user}]
    )
    return resp.content[0].text.strip()

def colorize_signal(text):
    for kw in EXTREME_KEYWORDS:
        if kw in text:
            return ALERT + text + RESET
    return text

def risk_color_term(level_text):
    if '매우높음' in level_text:
        return ALERT + level_text + RESET
    return level_text

# ── 시스템 프롬프트 ───────────────────────────────────────

SYS_ORCH = """Jason의 투자 분석 오케스트레이터입니다.
포트폴리오: Bitcoin, Gold, Brent/WTI유, Google, Nasdaq(QQQM), S&P500(SPY), Samsung, 미국선물(다우/S&P/나스닥/러셀)
Jason의 질문과 데이터를 보고 딱 2줄로만 답하세요. 마크다운/이모지/표 금지.
형식:
분석초점: [자산명] - 질문 핵심 한 문장
주요고려: 각 에이전트가 특히 봐야 할 포인트 한 문장"""

SYS_TECH = """기술적 분석 전문가 에이전트입니다. (차트분석 15년)
명확한 입장만 제시하세요. 딱 3줄로만 답하세요. 마크다운/이모지/표 금지.
형식:
시그널: [강력매수/매수/관망/매도/강력매도] - 핵심 수치 근거 한 문장
목표가: 매수 목표가 또는 손절 레벨
신뢰도: [높음/보통/낮음] - 이유 한 문장"""

SYS_MACRO = """거시경제 분석 전문가 에이전트입니다. (전 FED 이코노미스트)
딱 3줄로만 답하세요. 마크다운/이모지/표 금지.
형식:
환경: [위험선호/중립/위험회피] - VIX/DXY/금리 수치 인용 한 문장
기술분석검토: [동의/부분동의/반박] - 이유 한 문장
전망: 1-3개월 시장 전망 한 문장"""

SYS_SENT = """시장 심리 및 뉴스 분석 전문가 에이전트입니다. (행동경제학 박사)
딱 3줄로만 답하세요. 마크다운/이모지/표 금지.
형식:
심리: [극도탐욕/탐욕/중립/공포/극도공포] - 핵심 뉴스 한 줄
타에이전트검토: [동의/부분동의/반박] - 이유 한 문장
내러티브: 현재 시장 스토리와 가격 영향 한 문장"""

SYS_DEBATE = """토론 참여 에이전트입니다.
다른 에이전트들의 의견을 보고 2줄로만 답하세요. 마크다운/이모지 금지.
형식:
동의/반박: [동의/부분동의/반박] 한 문장
보완의견: 다른 에이전트가 놓친 중요 포인트 한 문장"""

SYS_RISK = """포트폴리오 리스크 관리 전문가 에이전트입니다. (헤지펀드 리스크매니저)
포트폴리오: Bitcoin, Gold, Brent/WTI유, Google, Nasdaq(QQQM), S&P500(SPY), Samsung, 미국선물
딱 4줄로만 답하세요. 마크다운/이모지/표 금지.
형식:
리스크레벨: [낮음/보통/높음/매우높음]
주요위험: 핵심 리스크 요인 2가지 (쉼표로 구분)
시나리오: 최악 한 문장 / 최선 한 문장
권고: 포지션 조정 방향 한 문장"""

SYS_SYNTH = """Jason의 수석 투자 어드바이저입니다.
Jason 프로필: 개인 투자자, ISA+직투 운용, 포트폴리오(BTC/금/브렌트/WTI/구글/나스닥/S&P500/삼성/미국선물)
애매한 표현 금지. 구체적 가격과 비율 명시. 마크다운/이모지/표 금지.
아래 형식을 그대로 지키세요:
결론: [한 문장 핵심 결론]

즉시행동:
Bitcoin  : [매수/매도/유지] [구체적 가격 또는 비율]
Gold     : [매수/매도/유지] [구체적 내용]
Brent유  : [매수/매도/유지] [구체적 내용]
WTI원유  : [매수/매도/유지] [구체적 내용]
Google   : [매수/매도/유지] [구체적 내용]
Nasdaq   : [매수/매도/유지] [구체적 내용]
S&P500   : [매수/매도/유지] [구체적 내용]

관찰지표:
1. [지표명] - 기준값
2. [지표명] - 기준값

합의: [에이전트 일치 비율]% - 합의 내용 한 문장
이견: 이견 내용 한 문장
신뢰도: [0-100%] - 이유"""

# ── HTML 대시보드 생성 ────────────────────────────────────

def generate_html(command, now, data, orch, results, debate_results, risk, final):
    e = html_lib.escape

    # 가격 카드
    price_cards = ''
    for name, d in data['prices'].items():
        pct   = d['change_pct']
        price = d['price']
        arrow = '▲' if pct >= 0 else '▼'
        col   = '#c0392b' if pct < 0 else '#27ae60'
        price_cards += f'''
        <div class="price-card">
          <div class="asset-name">{e(name)}</div>
          <div class="price">{price:,.2f}</div>
          <div class="change" style="color:{col}">{arrow} {abs(pct):.2f}%</div>
        </div>'''

    # 기술 지표 카드
    tech_cards = ''
    for name, t in data['technicals'].items():
        rsi_flag  = '과매수' if t['rsi'] > 70 else ('과매도' if t['rsi'] < 30 else '중립')
        macd_flag = '상승' if t['macd_hist'] > 0 else '하락'
        ma_gap    = f" MA50대비 {((t['price']/t['ma50']-1)*100):+.1f}%" if t['ma50'] else ''
        rsi_col   = '#c0392b' if t['rsi'] > 70 else ('#2980b9' if t['rsi'] < 30 else '#555')
        tech_cards += f'''
        <div class="tech-card">
          <div class="tech-name">{e(name)}</div>
          <div class="tech-row"><span class="tech-label">RSI</span>
            <span style="color:{rsi_col};font-weight:600">{t['rsi']} ({rsi_flag})</span></div>
          <div class="tech-row"><span class="tech-label">MACD</span>
            <span>{t["macd_hist"]:.4f} ({macd_flag})</span></div>
          <div class="tech-row"><span class="tech-label">BB</span>
            <span>{t["bb_pct_b"]:.2f}{e(ma_gap)}</span></div>
        </div>'''

    # 거시 지표 행
    macro_rows = ''
    for name, m in data['macro'].items():
        pct = m['change_pct']
        col = '#c0392b' if pct < 0 else '#27ae60'
        macro_rows += f'<tr><td>{e(name)}</td><td><b>{m["value"]}</b></td><td style="color:{col}">{pct:+.2f}%</td></tr>'

    # 뉴스 항목
    news_items = ''
    for asset, titles in data['news'].items():
        for t in titles[:2]:
            news_items += f'<li><span class="news-asset">{e(asset)}</span> {e(t[:80])}</li>'
    if not news_items:
        news_items = '<li>뉴스 없음</li>'

    # 에이전트 카드
    agent_cards = ''
    agent_list = [('기술분석', '📊'), ('거시경제', '🌐'), ('심리/뉴스', '📰')]
    for name, icon in agent_list:
        r1 = e(results.get(name, ''))
        rd = e(debate_results.get(name, ''))
        agent_cards += f'''
        <div class="agent-card">
          <div class="agent-title">{icon} {e(name)}</div>
          <div class="agent-section-label">1차 분석</div>
          <div class="agent-text">{r1}</div>
          <div class="agent-section-label debate-label">토론 후</div>
          <div class="agent-text">{rd}</div>
        </div>'''

    # 리스크 레벨 파싱
    risk_level = '알 수 없음'
    risk_bg    = '#888'
    risk_body  = ''
    for line in risk.split('\n'):
        if '리스크레벨:' in line:
            risk_level = line.split(':', 1)[-1].strip()
            risk_bg = {'매우높음': '#c0392b', '높음': '#e74c3c', '보통': '#e67e22', '낮음': '#27ae60'}.get(risk_level, '#888')
        elif line.strip():
            risk_body += e(line) + '<br>'

    # 최종 권고 파싱
    conclusion = ''
    action_rows = ''
    watch_items = ''
    meta_lines  = ''
    in_action = in_watch = False

    for line in final.split('\n'):
        stripped = line.strip()
        if stripped.startswith('결론:'):
            conclusion = e(stripped[3:].strip())
        elif stripped.startswith('즉시행동:'):
            in_action, in_watch = True, False
        elif stripped.startswith('관찰지표:'):
            in_action, in_watch = False, True
        elif stripped.startswith(('합의:', '이견:', '신뢰도:')):
            in_action, in_watch = False, False
            meta_lines += f'<div class="meta-row">{e(stripped)}</div>'
        elif in_action and ':' in stripped and stripped:
            parts  = stripped.split(':', 1)
            asset  = parts[0].strip()
            action = parts[1].strip()
            if not asset:
                continue
            act_col = 'inherit'
            if any(w in action for w in ['매도', '청산', '축소']):
                act_col = '#c0392b'
            elif '매수' in action:
                act_col = '#27ae60'
            action_rows += f'<tr><td class="asset-cell">{e(asset)}</td><td style="color:{act_col}">{e(action)}</td></tr>'
        elif in_watch and stripped:
            watch_items += f'<li>{e(stripped)}</li>'

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — {e(command)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  background:#f0f0f0;color:#222;font-size:14px;line-height:1.65}}
a{{color:inherit;text-decoration:none}}
.wrap{{max-width:980px;margin:0 auto;padding:28px 18px 60px}}

/* 헤더 */
.header{{background:#fff;border-radius:10px;padding:24px 28px;margin-bottom:18px;
  border-top:4px solid #222}}
.header h1{{font-size:16px;font-weight:700;color:#555;letter-spacing:.04em;margin-bottom:10px}}
.header .q{{font-size:20px;font-weight:700;color:#111;margin-bottom:6px}}
.header .ts{{font-size:12px;color:#aaa}}

/* 섹션 */
.section{{background:#fff;border-radius:10px;padding:22px 24px;margin-bottom:14px}}
.section-title{{font-size:11px;font-weight:700;color:#999;text-transform:uppercase;
  letter-spacing:.08em;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #eee}}

/* 가격 그리드 */
.price-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.price-card{{background:#fafafa;border:1px solid #e8e8e8;border-radius:8px;
  padding:16px 12px;text-align:center}}
.asset-name{{font-size:10px;font-weight:700;color:#aaa;text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:8px}}
.price{{font-size:17px;font-weight:700;margin-bottom:5px}}
.change{{font-size:13px;font-weight:600}}

/* 기술 지표 */
.tech-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}
.tech-card{{background:#fafafa;border:1px solid #e8e8e8;border-radius:8px;padding:14px}}
.tech-name{{font-size:11px;font-weight:700;color:#555;margin-bottom:10px}}
.tech-row{{display:flex;justify-content:space-between;font-size:12px;
  padding:4px 0;border-bottom:1px solid #f0f0f0}}
.tech-row:last-child{{border-bottom:none}}
.tech-label{{color:#aaa;font-weight:600;min-width:48px}}

/* 거시 테이블 */
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:10px;font-weight:700;color:#aaa;text-transform:uppercase;
  letter-spacing:.06em;padding:6px 10px;border-bottom:2px solid #eee}}
td{{padding:9px 10px;border-bottom:1px solid #f5f5f5}}
td:first-child{{color:#555;font-weight:600}}

/* 뉴스 */
.news-list{{list-style:none;padding:0}}
.news-list li{{padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:13px}}
.news-list li:last-child{{border-bottom:none}}
.news-asset{{display:inline-block;font-size:10px;font-weight:700;color:#888;
  background:#f0f0f0;border-radius:3px;padding:1px 6px;margin-right:6px}}

/* 에이전트 그리드 */
.agent-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.agent-card{{background:#fafafa;border:1px solid #e8e8e8;border-radius:8px;padding:16px}}
.agent-title{{font-size:13px;font-weight:700;color:#333;margin-bottom:12px;
  padding-bottom:8px;border-bottom:1px solid #eee}}
.agent-section-label{{font-size:10px;font-weight:700;color:#bbb;text-transform:uppercase;
  letter-spacing:.06em;margin:10px 0 5px}}
.agent-section-label.debate-label{{color:#999;margin-top:14px}}
.agent-text{{font-size:12px;color:#444;white-space:pre-wrap;word-break:break-word;line-height:1.7}}

/* 리스크 */
.risk-badge{{display:inline-block;padding:6px 18px;border-radius:5px;font-size:15px;
  font-weight:700;color:#fff;margin-bottom:14px}}
.risk-body{{font-size:13px;color:#444;white-space:pre-wrap;line-height:1.7}}

/* 최종 권고 */
.final-section{{border-top:4px solid #222}}
.conclusion-box{{background:#f7f7f7;border-radius:8px;padding:16px 20px;
  font-size:16px;font-weight:700;color:#111;margin-bottom:22px;line-height:1.5}}
.sub-title{{font-size:11px;font-weight:700;color:#aaa;text-transform:uppercase;
  letter-spacing:.08em;margin:20px 0 10px}}
.asset-cell{{font-weight:700;color:#333}}
.action-table td{{padding:10px 10px}}
.watch-list{{list-style:none;padding:0}}
.watch-list li{{font-size:13px;padding:6px 0;border-bottom:1px solid #f5f5f5}}
.watch-list li:last-child{{border-bottom:none}}
.watch-list li::before{{content:"→ ";color:#aaa}}
.meta-row{{font-size:12px;color:#888;padding:4px 0}}
.footer{{text-align:center;font-size:11px;color:#ccc;margin-top:30px}}
</style>
</head>
<body>
<div class="wrap">

  <!-- 헤더 -->
  <div class="header">
    <div class="h1">Jason Market 멀티에이전트 분석</div>
    <div class="q">{e(command)}</div>
    <div class="ts">{e(now)}</div>
  </div>

  <!-- 시장 현황 -->
  <div class="section">
    <div class="section-title">시장 현황</div>
    <div class="price-grid">{price_cards}</div>
  </div>

  <!-- 기술 지표 -->
  {'<div class="section"><div class="section-title">기술 지표</div><div class="tech-grid">' + tech_cards + '</div></div>' if tech_cards else ''}

  <!-- 거시 지표 -->
  <div class="section">
    <div class="section-title">거시 지표</div>
    <table>
      <tr><th>지표</th><th>현재값</th><th>등락</th></tr>
      {macro_rows}
    </table>
  </div>

  <!-- 최신 뉴스 -->
  <div class="section">
    <div class="section-title">최신 뉴스</div>
    <ul class="news-list">{news_items}</ul>
  </div>

  <!-- 오케스트레이터 -->
  <div class="section">
    <div class="section-title">오케스트레이터</div>
    <div style="font-size:13px;color:#444;white-space:pre-wrap">{e(orch)}</div>
  </div>

  <!-- 에이전트 분석 & 토론 -->
  <div class="section">
    <div class="section-title">에이전트 분석 및 토론</div>
    <div class="agent-grid">{agent_cards}</div>
  </div>

  <!-- 리스크 평가 -->
  <div class="section">
    <div class="section-title">리스크 평가</div>
    <div class="risk-badge" style="background:{risk_bg}">{e(risk_level)}</div>
    <div class="risk-body">{risk_body}</div>
  </div>

  <!-- 최종 투자 권고 -->
  <div class="section final-section">
    <div class="section-title">최종 투자 권고</div>
    <div class="conclusion-box">{conclusion}</div>

    <div class="sub-title">즉시 행동</div>
    <table class="action-table">
      <tr><th>자산</th><th>행동 및 상세</th></tr>
      {action_rows}
    </table>

    <div class="sub-title">관찰 지표</div>
    <ul class="watch-list">{watch_items}</ul>

    <div class="sub-title">에이전트 합의</div>
    <div style="margin-top:6px">{meta_lines}</div>
  </div>

  <div class="footer">Jason Market · {e(now)}</div>
</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>'''
    return html

# ── 메인 오케스트레이션 ──────────────────────────────────

def orchestrate(command: str):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    W   = 58

    print(f"\n{'━'*W}")
    print(f"  Jason 멀티에이전트 투자 분석 시스템")
    print(f"  질문: {command}")
    print(f"  {now}")
    print(f"{'━'*W}\n")

    data = collect_data()
    portfolio_text = build_portfolio_summary()

    # 데이터 요약 (에이전트 프롬프트용)
    price_lines = [f"  {n}: {d['price']:,.2f} ({d['change_pct']:+.2f}%)" for n, d in data['prices'].items()]
    tech_lines  = []
    for name, t in data['technicals'].items():
        rsi_f = "과매수" if t['rsi'] > 70 else ("과매도" if t['rsi'] < 30 else "중립")
        macd_f = "상승" if t['macd_hist'] > 0 else "하락"
        ma_g   = f", MA50대비 {((t['price']/t['ma50']-1)*100):+.1f}%" if t['ma50'] else ""
        tech_lines.append(f"  {name}: RSI={t['rsi']}({rsi_f}), MACD={t['macd_hist']:.4f}({macd_f}), BB={t['bb_pct_b']:.2f}{ma_g}")
    macro_lines = [f"  {n}: {m['value']} ({m['change_pct']:+.2f}%)" for n, m in data['macro'].items()]
    news_lines  = [f"  [{a}] {t[:65]}" for a, titles in data['news'].items() for t in titles[:2]]

    data_summary = (
        (portfolio_text + "\n\n" if portfolio_text else "") +
        "[현재가격]\n" + "\n".join(price_lines) +
        "\n\n[기술지표]\n" + ("\n".join(tech_lines) if tech_lines else "  없음") +
        "\n\n[거시지표]\n" + "\n".join(macro_lines) +
        "\n\n[최신뉴스]\n" + ("\n".join(news_lines) if news_lines else "  없음")
    )

    # ① 오케스트레이터
    print("  ① 오케스트레이터 분석중...", end='\r')
    orch = call_agent(SYS_ORCH, f"질문: {command}\n\n{data_summary}", model=SMART, max_tokens=150)
    print(f"\n  [ 오케스트레이터 ]\n  {'─'*50}")
    for line in orch.split('\n'):
        print(f"  {line}")

    # ② 3개 에이전트 병렬 분석
    print(f"\n  [ 독립 분석 ]\n  {'─'*50}")
    print("  분석중 (기술/거시/심리 동시)...", end='\r')

    results = {}
    agents  = [('기술분석', SYS_TECH), ('거시경제', SYS_MACRO), ('심리/뉴스', SYS_SENT)]

    def run(name, sys_p):
        try:
            results[name] = call_agent(sys_p, f"질문: {command}\n\n오케스트레이터:\n{orch}\n\n{data_summary}", model=FAST, max_tokens=200)
        except Exception as ex:
            results[name] = f"분석 실패: {ex}"

    threads = [threading.Thread(target=run, args=(n, s)) for n, s in agents]
    for t in threads: t.start()
    for t in threads: t.join()

    print(" " * 42)
    for name, _ in agents:
        print(f"\n  {name}")
        for line in results.get(name, '').split('\n'):
            print(f"    {colorize_signal(line)}")

    # ③ 토론 라운드
    print(f"\n  [ 에이전트 토론 ]\n  {'─'*50}")
    debate_results = {}
    for name, sys_p in agents:
        others = "\n\n".join(f"[{n}]\n{results[n]}" for n, _ in agents if n != name)
        prompt = f"질문: {command}\n\n{data_summary}\n\n다른 에이전트:\n{others}\n\n내 분석:\n{results[name]}"
        debate_results[name] = call_agent(SYS_DEBATE, prompt, model=FAST, max_tokens=120)

    for name, _ in agents:
        print(f"\n  {name} (토론후)")
        for line in debate_results.get(name, '').split('\n'):
            print(f"    {colorize_signal(line)}")

    # ④ 리스크 매니저
    print(f"\n  [ 리스크 평가 ]\n  {'─'*50}")
    print("  리스크 분석중...", end='\r')
    all_analysis = "\n\n".join(
        f"[{n} 분석]\n{results[n]}\n[{n} 토론]\n{debate_results[n]}" for n, _ in agents
    )
    risk = call_agent(SYS_RISK, f"질문: {command}\n\n{data_summary}\n\n{all_analysis}", model=SMART, max_tokens=200)

    print(" " * 40)
    for line in risk.split('\n'):
        if '리스크레벨:' in line:
            lv = line.split(':', 1)[-1].strip()
            print(f"  리스크레벨: {risk_color_term(lv)}")
        elif line.strip():
            print(f"  {colorize_signal(line)}")

    # ⑤ 최종 권고
    print(f"\n{'━'*W}\n  최종 투자 권고\n{'━'*W}")
    print("  생성중...", end='\r')
    final = call_agent(
        SYS_SYNTH,
        f"질문: {command}\n\n{data_summary}\n\n에이전트 분석:\n{all_analysis}\n\n리스크:\n{risk}",
        model=SMART, max_tokens=600
    )

    print(" " * 40)
    for line in final.split('\n'):
        if line.startswith('결론:'):
            print(f"\n  {line}")
        elif line.startswith(('즉시행동:', '관찰지표:')):
            print(f"\n  {line}")
        elif line.strip():
            print(f"  {line}")
    print(f"\n{'━'*W}")

    # ── HTML 대시보드 생성 & 열기 ──────────────────────────
    html_content = generate_html(command, now, data, orch, results, debate_results, risk, final)
    html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    )
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # TXT 리포트도 저장
    txt_path = html_path.replace('.html', '.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"Jason Market 멀티에이전트 분석\n질문: {command}\n생성: {now}\n{'='*58}\n\n")
        f.write(f"[오케스트레이터]\n{orch}\n\n")
        for n, _ in agents:
            f.write(f"[{n} 1차]\n{results[n]}\n\n[{n} 토론]\n{debate_results[n]}\n\n")
        f.write(f"[리스크]\n{risk}\n\n[최종권고]\n{final}\n")

    print(f"  대시보드: {html_path}")
    webbrowser.open(f"file://{html_path}")

    return final

# ── 진입점 ───────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        orchestrate(' '.join(sys.argv[1:]))
    else:
        print("\n  Jason 멀티에이전트 투자 분석 시스템")
        print("  종료: q\n")
        print("  예시:")
        print("    BTC 지금 매수해야 해?")
        print("    포트폴리오 리밸런싱 필요해?")
        print("    지금 시장 위험해? 현금 늘려야 해?")
        print("    금이랑 나스닥 중 어디에 더 넣어야 해?\n")

        while True:
            try:
                cmd = input("  질문: ").strip()
                if not cmd or cmd.lower() in ('q', 'quit', 'exit', '종료'):
                    print("  종료합니다.")
                    break
                orchestrate(cmd)
            except KeyboardInterrupt:
                print("\n  종료합니다.")
                break
            except Exception as e:
                print(f"  오류: {e}")

if __name__ == '__main__':
    main()
