#!/usr/bin/env python3
"""뉴스 수집 & 스마트 정리 - Jason Market
완전 무료 (API 불필요): yfinance + Google News RSS + 키워드 감성분석"""

import requests, json, webbrowser, tempfile, time
import xml.etree.ElementTree as ET
import yfinance as yf
from datetime import datetime
from urllib.parse import quote
from xlsx_sync import load_portfolio as _load_pf

# ── 구글 번역 (무료, API 키 불필요) ─────────────────────────
def translate_batch(titles: list[str]) -> list[str]:
    """영어 제목 리스트를 한국어로 일괄 번역 (Google Translate 비공식 endpoint)"""
    if not titles:
        return titles
    # 구분자로 묶어서 한 번에 번역 (속도 개선)
    SEP = ' ||| '
    joined = SEP.join(titles)
    try:
        r = requests.get(
            'https://translate.googleapis.com/translate_a/single',
            params={'client':'gtx','sl':'en','tl':'ko','dt':'t','q': joined},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15,
        )
        data = r.json()
        # 결과 조각들 이어붙이기
        translated = ''.join(seg[0] for seg in data[0] if seg[0])
        parts = translated.split(SEP)
        # 개수 불일치 시 원본 반환
        if len(parts) != len(titles):
            return titles
        return [p.strip() for p in parts]
    except Exception:
        return titles  # 번역 실패 시 원본 영어 그대로

CYAN  = '\033[36m'
AMBER = '\033[38;5;214m'
ALERT = '\033[38;5;203m'
RESET = '\033[0m'

# ── 강세 / 약세 키워드 ────────────────────────────────────────
BULL_KW = [
    'surge','rally','gain','rise','jump','soar','climb','record',
    'beat','strong','growth','positive','upgrade','buy','boost',
    'optimism','recovery','bullish','outperform','high','up ',
]
BEAR_KW = [
    'drop','fall','decline','plunge','crash','slip','tumble','low',
    'miss','weak','sell','downgrade','recession','fear','risk',
    'warning','loss','bearish','underperform','concern','down ',
    'layoff','cut','debt','default','tariff','sanction',
]

def sentiment(title):
    tl = title.lower()
    b = sum(1 for k in BULL_KW if k in tl)
    s = sum(1 for k in BEAR_KW if k in tl)
    if b > s: return 'bull'
    if s > b: return 'bear'
    return 'neutral'

def sent_icon(s):
    return {'bull': '🟢', 'bear': '🔴', 'neutral': '⚪'}[s]

def sent_color(s):
    return {'bull': '#00838f', 'bear': '#c62828', 'neutral': '#888'}[s]

# ── 자산 목록 ─────────────────────────────────────────────────
_SKIP = {'XLSX_PRICE', 'GOLD_KRX', 'CASH'}
_GNEWS_QUERY = {
    'QQQM':     'QQQM Nasdaq ETF',
    'SPY':      'SPY S&P500 ETF',
    'GOOGL':    'Google Alphabet stock',
    'BTC-USD':  'Bitcoin crypto',
    'GC=F':     'Gold commodity',
    'CL=F':     'WTI Oil price',
    'BZ=F':     'Brent Oil price',
    '^VIX':     'VIX volatility market',
    'USDKRW=X': 'US Dollar Korean Won',
    '^TNX':     'US 10 year treasury yield',
    '^KS11':    'KOSPI Korea stock market',
}

def _build_assets():
    assets, seen = {}, set()
    try:
        for h in _load_pf():
            if h.get('is_cash') or h.get('ticker') in _SKIP: continue
            t, n = h['ticker'], h['name']
            if t and t not in seen:
                seen.add(t); assets[n] = t
    except Exception: pass
    for k, v in {
        'Bitcoin':'BTC-USD','Gold':'GC=F','WTI Oil':'CL=F',
        'Brent Oil':'BZ=F','S&P500':'SPY','KOSPI':'^KS11',
        'VIX':'^VIX','달러/원':'USDKRW=X','미국10년물':'^TNX',
    }.items():
        if v not in seen:
            seen.add(v); assets[k] = v
    return assets

ASSETS = _build_assets()

# ── 뉴스 수집 ─────────────────────────────────────────────────
def get_yf_news(ticker, max_items=4):
    """yfinance 뉴스 (URL 포함)"""
    try:
        news = yf.Ticker(ticker).news or []
        results = []
        for item in news[:max_items]:
            c     = item.get('content', item)
            title = (c.get('title') or item.get('title') or '').strip()
            pub   = c.get('pubDate') or item.get('providerPublishTime') or 0
            # URL 추출 (여러 위치에 있을 수 있음)
            url = (c.get('canonicalUrl', {}).get('url') or
                   c.get('clickThroughUrl', {}).get('url') or
                   item.get('link') or '')
            if not title: continue
            try:
                if isinstance(pub, str):
                    dt = datetime.strptime(pub[:19].replace('T',' '), '%Y-%m-%d %H:%M:%S')
                elif isinstance(pub, (int,float)) and pub > 0:
                    dt = datetime.fromtimestamp(pub)
                else: dt = None
                ts = dt.strftime('%m/%d %H:%M') if dt else ''
            except: ts = ''
            results.append({'title': title, 'time': ts, 'src': 'Yahoo', 'url': url})
        return results
    except: return []

def get_gnews(query, max_items=4):
    """Google News RSS (무료, API 불필요, URL 포함)"""
    try:
        url = (f"https://news.google.com/rss/search?"
               f"q={quote(query)}&hl=en-US&gl=US&ceid=US:en")
        r = requests.get(url, timeout=8,
                         headers={'User-Agent': 'Mozilla/5.0'})
        root = ET.fromstring(r.content)
        results = []
        for item in root.findall('.//item')[:max_items]:
            title   = item.findtext('title','').strip()
            link    = item.findtext('link','').strip()
            if ' - ' in title:
                title, pub_src = title.rsplit(' - ', 1)
            else:
                pub_src = ''
            pub = item.findtext('pubDate','')
            if not title: continue
            try:
                dt = datetime.strptime(pub[:25], '%a, %d %b %Y %H:%M:%S')
                ts = dt.strftime('%m/%d %H:%M')
            except: ts = ''
            results.append({'title': title.strip(), 'time': ts,
                            'src': pub_src or 'GNews', 'url': link})
        return results
    except: return []

def collect_all_news():
    """전체 자산 뉴스 수집 + 중복 제거 + 감성 분류"""
    all_news, seen = [], set()
    for name, ticker in ASSETS.items():
        items = get_yf_news(ticker)
        # Google News RSS 추가 수집
        query = _GNEWS_QUERY.get(ticker, name)
        items += get_gnews(query, max_items=3)

        for item in items:
            key = item['title'][:35].lower()
            if key in seen: continue
            seen.add(key)
            item['asset']  = name
            item['ticker'] = ticker
            item['sent']   = sentiment(item['title'])
            all_news.append(item)

    # 최신순 정렬 (시간 있는 것 우선)
    def sort_key(n):
        t = n.get('time','')
        try: return datetime.strptime(f"2026/{t}", '%Y/%m/%d %H:%M')
        except: return datetime.min
    all_news.sort(key=sort_key, reverse=True)

    # ── 한국어 번역 (구글 번역, 무료) ──────────────────────────
    print("  한국어 번역 중...")
    titles_en = [n['title'] for n in all_news]
    titles_ko = translate_batch(titles_en)
    for n, ko in zip(all_news, titles_ko):
        n['title_ko'] = ko

    return all_news

# ── 요약 통계 (무료, 키워드 기반) ────────────────────────────
def make_summary(news_list):
    bull = [n for n in news_list if n['sent']=='bull']
    bear = [n for n in news_list if n['sent']=='bear']
    neu  = [n for n in news_list if n['sent']=='neutral']
    total = len(news_list)
    if total == 0: return None

    # 자산별 감성 집계
    asset_sent = {}
    for n in news_list:
        a = n['asset']
        if a not in asset_sent: asset_sent[a] = {'bull':0,'bear':0,'neu':0}
        asset_sent[a][n['sent'] if n['sent']!='neutral' else 'neu'] += 1

    # 시장 전체 방향
    if len(bull) > len(bear)*1.5:  mood, mood_color = '강세 우세 🟢', '#00838f'
    elif len(bear) > len(bull)*1.5: mood, mood_color = '약세 우세 🔴', '#c62828'
    else:                           mood, mood_color = '중립 혼조 ⚪', '#666'

    return {
        'total': total, 'bull': len(bull), 'bear': len(bear), 'neu': len(neu),
        'mood': mood, 'mood_color': mood_color,
        'asset_sent': asset_sent,
        'top_bull': bull[:3], 'top_bear': bear[:3],
    }

# ── 터미널 출력 ───────────────────────────────────────────────
def print_terminal(news_list, summary):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*64}")
    print(f"  Jason 뉴스 수집   {ts}  ({len(news_list)}건)")
    print(f"{'━'*64}")

    if summary:
        mc = CYAN if 'bull' in summary['mood'] else ALERT if 'bear' in summary['mood'] else AMBER
        print(f"  시장 전반 분위기: {mc}{summary['mood']}{RESET}  "
              f"({CYAN}강세 {summary['bull']}{RESET} / "
              f"{ALERT}약세 {summary['bear']}{RESET} / "
              f"중립 {summary['neu']})")
        print(f"  {'─'*62}")

        # 자산별 감성 요약
        print(f"  자산별 뉴스 분위기:")
        for asset, cnt in summary['asset_sent'].items():
            b, br, n = cnt['bull'], cnt['bear'], cnt['neu']
            if b > br:   col, lbl = CYAN,  '강세▲'
            elif br > b: col, lbl = ALERT, '약세▼'
            else:        col, lbl = '',    '혼조 '
            print(f"    {asset:<14} {col}{lbl}{RESET}  "
                  f"(🟢{b} 🔴{br} ⚪{n})")
        print(f"  {'─'*62}")

    # 뉴스 목록
    prev_asset = None
    for n in news_list[:30]:
        if n['asset'] != prev_asset:
            print(f"\n  {CYAN}▌ {n['asset']}{RESET}")
            prev_asset = n['asset']
        icon  = sent_icon(n['sent'])
        title = n.get('title_ko', n['title'])
        title = title[:62] + ('…' if len(title)>62 else '')
        ts_s  = f"[{n['time']}]" if n['time'] else ''
        print(f"    {icon} {ts_s:<12} {title}")

    print(f"\n{'━'*64}")
    print(f"  ※ 출처: Yahoo Finance + Google News RSS  |  무료·실시간\n")

# ── HTML 생성 ─────────────────────────────────────────────────
def generate_html(news_list, summary):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 자산별 뉴스 그룹
    groups = {}
    for n in news_list:
        a = n['asset']
        if a not in groups: groups[a] = []
        groups[a].append(n)

    # 요약 카드 HTML
    if summary:
        asset_bars = ''
        for asset, cnt in summary['asset_sent'].items():
            b, br, ne = cnt['bull'], cnt['bear'], cnt['neu']
            tot = b + br + ne or 1
            bp  = b/tot*100; sp = br/tot*100
            if b > br:   lbl, lc = '강세', '#00838f'
            elif br > b: lbl, lc = '약세', '#c62828'
            else:        lbl, lc = '혼조', '#888'
            asset_bars += f"""
            <div class="abar">
              <span class="aname">{asset}</span>
              <div class="atrack">
                <div style="width:{bp:.0f}%;background:#00838f;height:100%;display:inline-block;border-radius:3px 0 0 3px"></div>
                <div style="width:{sp:.0f}%;background:#c62828;height:100%;display:inline-block"></div>
              </div>
              <span class="albl" style="color:{lc}">{lbl} 🟢{b}🔴{br}⚪{ne}</span>
            </div>"""

        summary_html = f"""
    <div class="summary-card">
      <div class="sum-header">
        시장 전반 분위기: <span style="color:{summary['mood_color']};font-weight:700">{summary['mood']}</span>
        &nbsp;|&nbsp; 총 {summary['total']}건 &nbsp;
        <span style="color:#00838f">🟢강세 {summary['bull']}</span> &nbsp;
        <span style="color:#c62828">🔴약세 {summary['bear']}</span> &nbsp;
        <span style="color:#888">⚪중립 {summary['neu']}</span>
      </div>
      <div class="abar-wrap">{asset_bars}</div>
    </div>"""
    else:
        summary_html = ''

    # 뉴스 카드 HTML
    cards = ''
    for asset, items in groups.items():
        news_rows = ''
        for n in items:
            sc  = sent_color(n['sent'])
            si  = sent_icon(n['sent'])
            ts_ = f'<span class="ntime">[{n["time"]}]</span>' if n['time'] else ''
            src = f'<span class="nsrc">{n["src"]}</span>'
            title_ko = n.get('title_ko', n['title'])
            article_url = n.get('url', '')
            if article_url:
                title_html = f'<a class="ntitle" href="{article_url}" target="_blank">{title_ko}</a>'
            else:
                title_html = f'<span class="ntitle">{title_ko}</span>'
            news_rows += f"""
        <div class="news-row">
          <span class="sent-dot" style="color:{sc}">{si}</span>
          {ts_}
          {title_html}
          {src}
        </div>"""

        cards += f"""
    <div class="card">
      <div class="card-title">{asset}
        <span class="ticker-badge">{items[0]['ticker']}</span>
      </div>
      {news_rows}
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>뉴스 — Jason Market</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f6f8;color:#222;font-family:'Segoe UI',Arial,sans-serif;padding:20px}}
h1{{font-size:19px;font-weight:700;color:#1a237e;margin-bottom:3px}}
.ts{{font-size:12px;color:#888;margin-bottom:14px}}
/* 요약 카드 */
.summary-card{{background:#fff;border-radius:10px;padding:16px 20px;
  border:1px solid #dde3f0;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:18px}}
.sum-header{{font-size:14px;margin-bottom:12px}}
.abar-wrap{{display:flex;flex-direction:column;gap:6px}}
.abar{{display:flex;align-items:center;gap:10px}}
.aname{{font-size:12px;color:#555;width:110px;flex-shrink:0}}
.atrack{{flex:1;height:10px;background:#e8eaf0;border-radius:4px;overflow:hidden;display:flex}}
.albl{{font-size:11px;width:120px;flex-shrink:0}}
/* 뉴스 카드 그리드 */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}}
.card{{background:#fff;border-radius:10px;padding:16px 18px;
  border:1px solid #dde3f0;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.card-title{{font-size:15px;font-weight:700;color:#1a237e;
  margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.ticker-badge{{font-size:10px;background:#eef1f8;color:#555;
  padding:2px 7px;border-radius:4px;font-weight:400}}
.news-row{{display:flex;align-items:flex-start;gap:6px;
  padding:7px 0;border-bottom:1px solid #f0f2f8;flex-wrap:wrap}}
.news-row:last-child{{border-bottom:none}}
.sent-dot{{font-size:14px;flex-shrink:0;margin-top:1px}}
.ntime{{font-size:11px;color:#aaa;flex-shrink:0;padding-top:2px}}
.ntitle{{font-size:13px;color:#333;line-height:1.5;flex:1;min-width:200px;text-decoration:none}}
a.ntitle{{color:#1a237e;text-decoration:none;cursor:pointer}}
a.ntitle:hover{{text-decoration:underline;color:#0d47a1}}
.nsrc{{font-size:10px;color:#bbb;flex-shrink:0;padding-top:3px;
  background:#f5f6f8;border-radius:3px;padding:1px 5px}}
/* 범례 */
.legend{{font-size:12px;color:#888;margin-bottom:14px}}
.legend span{{margin-right:14px}}
</style>
</head>
<body>
<h1>📰 뉴스 대시보드 — Jason Market</h1>
<div class="ts">{ts} &nbsp;|&nbsp; Yahoo Finance + Google News RSS &nbsp;|&nbsp; 완전 무료</div>
<div class="legend">
  <span>🟢 강세 신호</span><span>🔴 약세 신호</span><span>⚪ 중립</span>
</div>
{summary_html}
<div class="grid">{cards}</div>
</body>
</html>"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                     delete=False, encoding='utf-8') as f:
        f.write(html)
        path = f.name
    webbrowser.open(f'file://{path}')
    print(f"  🌐 브라우저로 열림\n")

# ── 메인 ─────────────────────────────────────────────────────
def main():
    print(f"\n{'━'*64}")
    print(f"  Jason 뉴스 수집   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*64}")
    print("  뉴스 수집 중 (Yahoo Finance + Google News RSS)...")

    news_list = collect_all_news()
    summary   = make_summary(news_list)

    if not news_list:
        print(f"\n  {ALERT}⚠ 뉴스를 가져올 수 없습니다 (네트워크 확인){RESET}\n")
        return

    print_terminal(news_list, summary)
    generate_html(news_list, summary)

if __name__ == '__main__':
    main()
