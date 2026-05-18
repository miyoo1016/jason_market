from __future__ import annotations
"""Alpha Hunter — 거시경제 & 지정학 분석 모듈
Fear & Greed, VIX, CFTC COT, Yahoo 헤드라인"""

import json
import csv
import io
import re
import subprocess
import yfinance as yf
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

from jm_lib.colors import CYAN, AMBER, RESET
from alpha_hunter_base import HEADERS
from alpha_hunter_md import parse_date_str, sort_headlines
from alpha_hunter_collector import fetch_curl

_CNN_API = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
_CNN_REF = 'https://edition.cnn.com/markets/fear-and-greed'

_FG_LABEL_KO = {
    'extreme fear': '극도의 공포 🔴',
    'fear': '공포 🟠',
    'neutral': '중립 🟡',
    'greed': '탐욕 🟢',
    'extreme greed': '극도의 탐욕 💚',
}


def _fetch_fear_greed() -> dict | None:
    """CNN Fear & Greed"""
    try:
        r = subprocess.run(
            ['curl', '-s', '-A',
             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
             '-H', f'Referer: {_CNN_REF}',
             _CNN_API],
            capture_output=True, timeout=15
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        fg = d['fear_and_greed']
        rating = fg.get('rating', '').lower()
        return {
            'score': round(float(fg['score']), 1),
            'label': _FG_LABEL_KO.get(rating, fg.get('rating', 'N/A')),
            'prev1w': round(float(fg.get('previous_1_week', 0)), 1),
        }
    except Exception:
        return None


def _fetch_vix() -> dict | None:
    """VIX 현재가"""
    try:
        hist = yf.Ticker('^VIX').history(period='5d')
        if len(hist) < 2:
            return None
        curr = float(hist['Close'].iloc[-1])
        prev = float(hist['Close'].iloc[-2])
        chg = curr - prev
        return {
            'price': round(curr, 2),
            'change': round(chg, 2),
            'pct': round(chg / prev * 100, 1),
        }
    except Exception:
        return None


def _fetch_cot_sp500() -> dict | None:
    """CFTC COT — Leveraged Funds Net Position"""
    url = 'https://www.cftc.gov/dea/newcot/FinFutWk.txt'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.encoding = 'utf-8'
        reader = csv.reader(io.StringIO(resp.text))
        header = None
        for row in reader:
            if not row:
                continue
            if header is None:
                header = [c.strip().strip('"').lower() for c in row]
                continue
            name = row[0].strip().strip('"').upper()
            if 'E-MINI S&P 500' not in name:
                continue
            def idx(keyword):
                for i, h in enumerate(header):
                    if keyword in h:
                        return i
                return None
            date_i = idx('report_date_as_yyyy') or 2
            lev_l_i = idx('lev_money_positions_long') or 14
            lev_s_i = idx('lev_money_positions_short') or 15
            def to_int(s):
                return int(str(s).strip().strip('"').replace(',', '') or 0)
            date = row[date_i].strip().strip('"')[:10] if len(row) > date_i else 'N/A'
            lev_long = to_int(row[lev_l_i]) if len(row) > lev_l_i else 0
            lev_short = to_int(row[lev_s_i]) if len(row) > lev_s_i else 0
            net = lev_long - lev_short
            direction = '매수 우위 📈' if net > 0 else '매도 우위 📉'
            return {
                'date': date,
                'lev_long': lev_long,
                'lev_short': lev_short,
                'net': net,
                'direction': direction,
            }
        return None
    except Exception:
        return None


def _fetch_yahoo_headlines(n: int = 20) -> list:
    """Yahoo RSS 헤드라인 수집"""
    feeds = [
        'https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlBQVAB?hl=en-US&gl=US&ceid=US:en',
        'https://news.google.com/rss/search?q=iran+oil+hormuz+fed+fomc+inflation+tariff&when=1d&hl=en-US&gl=US&ceid=US:en',
        'https://feeds.marketwatch.com/marketwatch/topstories/',
        'https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL%3DF&region=US&lang=en-US',
        'https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US',
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    seen_titles = set()
    all_results = []
    
    for url in feeds:
        try:
            xml_text = fetch_curl(url, timeout=12)
            if not xml_text:
                continue
            xml_clean = re.sub(r'\s+xmlns(?::[a-zA-Z0-9_]+)?="[^"]*"', '', xml_text)
            root = ET.fromstring(xml_clean)
            items = root.findall('.//item')
            for item in items[:n]:
                title = re.sub(r'<[^>]+>', ' ', item.findtext('title', ''))
                link = item.findtext('link', '').strip()
                pub_raw = item.findtext('pubDate', '')
                pub = parse_date_str(pub_raw)
                if not title or not link:
                    continue
                if pub_raw:
                    try:
                        pub_dt = parsedate_to_datetime(pub_raw)
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        if pub_dt < cutoff:
                            continue
                    except Exception:
                        pass
                key = title.lower().strip()[:30]
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                all_results.append({'title': title, 'url': link, 'date': pub or ''})
        except Exception:
            continue
    
    return sort_headlines(all_results) if all_results else []


def build_macro_dashboard() -> tuple:
    """Macro & Flow Dashboard"""
    print(f"  {CYAN}→ Fear & Greed 수집 중...{RESET}", end=' ', flush=True)
    fg = _fetch_fear_greed()
    print(f"{CYAN}완료{RESET}" if fg else f"{AMBER}실패{RESET}")

    print(f"  {CYAN}→ VIX 수집 중...{RESET}", end=' ', flush=True)
    vix = _fetch_vix()
    print(f"{CYAN}완료{RESET}" if vix else f"{AMBER}실패{RESET}")

    print(f"  {CYAN}→ CFTC COT 수집 중...{RESET}", end=' ', flush=True)
    cot = _fetch_cot_sp500()
    print(f"{CYAN}완료{RESET}" if cot else f"{AMBER}실패{RESET}")

    print(f"  {CYAN}→ Yahoo Finance 헤드라인 수집 중...{RESET}", end=' ', flush=True)
    headlines = _fetch_yahoo_headlines(20)
    print(f"{CYAN}{len(headlines)}건{RESET}" if headlines else f"{AMBER}실패{RESET}")

    lines = ['## 🌐 [Macro & Flow Dashboard]', '']
    lines.append('### 📊 시장 온도계')
    if fg:
        score = fg['score']
        filled = int(round(score / 10))
        bar = '█' * filled + '░' * (10 - filled)
        prev_str = f"  (1주전: {fg['prev1w']})" if fg.get('prev1w') else ''
        lines.append(f'- **CNN Fear & Greed**: `{score}/100` — **{fg["label"]}**  `{bar}`{prev_str}')
    else:
        lines.append('- **CNN Fear & Greed**: 조회 실패')

    if vix:
        sign = '+' if vix['change'] >= 0 else ''
        vix_note = '📈 공포 상승' if vix['change'] > 0 else '📉 공포 완화'
        lines.append(f'- **VIX**: `{vix["price"]:.2f}`  ({sign}{vix["change"]:.2f}, {sign}{vix["pct"]:.1f}%)  {vix_note}')
    else:
        lines.append('- **VIX**: 조회 실패')

    lines.append('')
    lines.append('### 🏦 스마트 머니 포지션 (CFTC COT)')
    if cot:
        net_str = f'+{cot["net"]:,}' if cot['net'] >= 0 else f'{cot["net"]:,}'
        lines.append(f'- **E-mini S&P 500 Leveraged Funds Net** ({cot["date"]}): `{net_str}` — {cot["direction"]}')
        lines.append(f'  - Long: {cot["lev_long"]:,} / Short: {cot["lev_short"]:,}')
    else:
        lines.append('- CFTC COT 조회 실패')

    lines.append('')
    lines.append('### 📰 주요 거시/증시 헤드라인')
    if headlines:
        cur_label = None
        for h in headlines:
            if h.get('label') != cur_label:
                cur_label = h.get('label', '')
                lines.append(f'\n**{cur_label}**')
            title = h['title'].replace('[', '\\[').replace(']', '\\]')
            lines.append(f'- [{title}]({h["url"]})  _{h["date"]}_')
    else:
        lines.append('- 헤드라인 조회 실패')

    lines += ['', '---', '']
    macro_data = {'fg': fg, 'vix': vix, 'cot': cot, 'headlines': headlines}
    return '\n'.join(lines), macro_data


__all__ = ['build_macro_dashboard']
