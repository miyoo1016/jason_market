#!/usr/bin/env python3
"""뉴스 AI 요약 - Jason Market
포트폴리오 자산 관련 최신 뉴스를 수집하고 Claude가 한국어로 요약합니다."""

import os
import yfinance as yf
from datetime import datetime, timezone
from dotenv import load_dotenv
from xlsx_sync import load_portfolio as _load_pf

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

# news_summary: yfinance-compatible tickers only (skip XLSX_PRICE, GOLD_KRX, CASH)
_NEWS_SKIP = {'XLSX_PRICE', 'GOLD_KRX', 'CASH'}

def _build_assets():
    assets = {}
    seen = set()
    try:
        holdings = _load_pf()
        for h in holdings:
            if h.get('is_cash') or h.get('ticker') == 'CASH':
                continue
            ticker = h['ticker']
            if ticker in _NEWS_SKIP:
                continue
            name = h['name']
            if ticker and ticker not in seen:
                seen.add(ticker)
                assets[name] = ticker
    except Exception:
        pass

    market = {
        'Bitcoin':  'BTC-USD',
        'Gold':     'GC=F',
        'Brent':    'BZ=F',
        'Oil':      'CL=F',
        'S&P500':   'SPY',
        'Dow':      '^DJI',
        'KOSPI200': '^KS11',
    }
    for k, v in market.items():
        if v not in seen:
            seen.add(v)
            assets[k] = v
    return assets

ASSETS = _build_assets()

def get_news(ticker, max_items=4):
    """yfinance .news 속성으로 뉴스 수집"""
    try:
        t = yf.Ticker(ticker)
        news = t.news
        if not news:
            return []
        results = []
        for item in news[:max_items]:
            # yfinance 1.x 뉴스 구조
            content = item.get('content', item)
            title   = (content.get('title') or item.get('title') or '').strip()
            pub_ts  = (content.get('pubDate') or item.get('providerPublishTime') or 0)

            if not title:
                continue

            # 시간 변환
            try:
                if isinstance(pub_ts, str):
                    dt_str = pub_ts[:19].replace('T', ' ')
                    pub_dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
                elif isinstance(pub_ts, (int, float)) and pub_ts > 0:
                    pub_dt = datetime.fromtimestamp(pub_ts)
                else:
                    pub_dt = None
                time_str = pub_dt.strftime('%m/%d %H:%M') if pub_dt else ''
            except Exception:
                time_str = ''

            results.append({'title': title, 'time': time_str})
        return results
    except Exception as e:
        return []

def collect_all_news():
    """전체 자산 뉴스 수집 (중복 제거)"""
    all_news = []
    seen_titles = set()

    for asset_name, ticker in ASSETS.items():
        items = get_news(ticker)
        for item in items:
            title = item['title']
            # 중복 체크 (앞 30자 기준)
            key = title[:30].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            item['asset'] = asset_name
            all_news.append(item)

    return all_news

def summarize_with_ai(news_list):
    """Claude로 뉴스 요약"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("\n⚠ ANTHROPIC_API_KEY 없음 → AI 요약 생략")
        return None

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key.strip())
    except Exception as e:
        print(f"\n⚠ Claude 초기화 실패: {e}")
        return None

    if not news_list:
        return "수집된 뉴스가 없습니다."

    news_text = '\n'.join(
        f"[{n['asset']}] ({n['time']}) {n['title']}"
        for n in news_list
    )

    prompt = f"""Jason의 포트폴리오(비트코인, 금, 브렌트유, WTI원유, 구글, 나스닥, S&P500, 다우) 관련 최신 뉴스입니다.
({datetime.now().strftime('%Y-%m-%d %H:%M')} 기준)

{news_text}

다음 형식으로 한국어 요약해주세요:

## 핵심 뉴스 요약 (3줄)
[가장 중요한 3가지 뉴스를 한 줄씩]

## 자산별 영향
[각 자산에 미치는 영향을 간결하게]

## Jason이 즉시 알아야 할 것
[오늘 대응이 필요한 사항이 있다면 1-2줄]

전체 400자 이내."""

    try:
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=800,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return resp.content[0].text
    except Exception as e:
        return f"AI 요약 오류: {e}"

def main():
    print(f"\n{'━'*60}")
    print(f"  Jason 뉴스 AI 요약   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*60}")
    print("  뉴스 수집 중 (약 10-15초)...")

    news_list = collect_all_news()

    # 수집된 뉴스 목록 출력
    if news_list:
        print(f"\n  수집된 뉴스 ({len(news_list)}개)")
        print(f"  {'─'*56}")
        for n in news_list:
            time_str = f"[{n['time']}]" if n['time'] else ''
            title    = n['title'][:60] + ('...' if len(n['title']) > 60 else '')
            print(f"  [{n['asset']:<8}] {time_str:<12} {title}")
    else:
        print(f"\n  ⚠ 뉴스를 가져올 수 없습니다 (네트워크 확인)")

    # AI 요약
    summary = summarize_with_ai(news_list)
    if summary:
        print(f"\n{'━'*60}")
        print(f"  Claude AI 뉴스 요약")
        print(f"{'━'*60}")
        print(summary)
        print(f"{'━'*60}\n")

if __name__ == '__main__':
    main()
