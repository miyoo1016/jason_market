#!/usr/bin/env python3
"""Alpha Hunter — 증시 고수 글 자동 수집기 | Jason Market 17번
소스: seed_list.json 개인 피드 + Reddit RSS
→ signals/ 폴더에 날짜별 .md 저장 + HTML 대시보드
완전 무료 | API 키 · 로그인 불필요

저장 조건:
  [필수] ① 제목 차단(봇·공지) 통과
  [OR]   ② 본문에 예측 키워드 있거나
         ③ 본문에 자산/티커 언급 있거나
         → ②③ 둘 중 하나면 수집
  + 72h 이내 + 본문 150자 이상
"""

import os, json, re, time, random, webbrowser, hashlib, subprocess, csv, io
import xml.etree.ElementTree as ET
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from html import unescape

DIR           = os.path.dirname(os.path.abspath(__file__))
SEEDS_FILE    = os.path.join(DIR, 'alpha_hunter_seeds.json')
SEED_LIST     = os.path.join(DIR, 'seed_list.json')
SEEN_FILE     = os.path.join(DIR, 'alpha_hunter_seen.json')
SIGNALS_DIR   = os.path.join(DIR, 'signals')
HTML_OUT      = os.path.join(DIR, 'alpha_hunter.html')

CYAN  = '\033[36m'
AMBER = '\033[38;5;214m'
ALERT = '\033[38;5;203m'
RESET = '\033[0m'

# ── 필터 상수 ────────────────────────────────────────────────
FRESHNESS_HOURS    = 72        # 이 시간 이내 글만 수집
MIN_EXCERPT_CHARS  = 150       # 본문 최소 길이
MAX_EXCERPT_MD     = 800       # MD 저장 시 최대 길이 (초과 시 말줄임)

# Reddit 공지성 제목 키워드 (대소문자 무관)
NOISY_TITLE_KW = [
    'daily', 'weekly', 'weekend', 'thread', 'megathread',
    'rate my portfolio', 'quarterly', 'discussion',
    'what are your moves', 'meme', 'monthly',
]

# ── 방향성 키워드 (② AND 조건 — 반드시 있어야 함) ────────────
DIRECTION_KW = [
    # 영어
    'bullish', 'bearish',
    'rally', 'rallying', 'rallied',
    'drop', 'dropping', 'dropped',
    'crash', 'crashing', 'crashed',
    'bounce', 'bouncing', 'bounced',
    'breakout', 'breaking out', 'broke out',
    'support', 'resistance',
    'target', 'price target',
    'upside', 'downside',
    'overbought', 'oversold',
    # 한국어
    '상승', '하락', '급등', '급락', '반등',
    '지지', '저항', '목표가', '전망', '돌파',
]

# ── 자산/지수/매크로 키워드 (① AND 조건 — 반드시 있어야 함) ──
# 문자열 매칭용 (소문자 비교)
ASSET_KW = [
    # 지수·ETF
    's&p', 'nasdaq', 'spx', 'spy', 'qqq',
    'vix', 'dow', 'russell', 'iwm',
    # 매크로
    'cpi', 'fomc', 'fed rate', 'federal reserve',
    'yields', 'yield curve', 'treasury',
    'oil', 'crude', 'wti', 'brent',
    'inflation', 'interest rate',
    # 한국어
    '나스닥', '금리', '유가', '원유', '연준', '국채',
    '코스피', '달러', '환율',
]

# 티커 패턴: $TSLA 또는 대문자 2~5자 (단어 경계 기준)
# 흔한 영어 단어 제외 목록 (false positive 방지)
_COMMON_WORDS = {
    'I', 'A', 'AN', 'THE', 'IS', 'IT', 'IN', 'AT', 'BE', 'BY',
    'DO', 'GO', 'IF', 'MY', 'NO', 'OF', 'ON', 'OR', 'SO', 'TO',
    'UP', 'US', 'WE', 'AM', 'AS', 'HE', 'HI', 'ME', 'OK', 'PM',
    'AM', 'RE', 'TV', 'AI', 'OP', 'OC', 'DD', 'IMO', 'FYI', 'TIL',
    'AMA', 'ETA', 'PSA', 'TBA', 'YTD', 'YOY', 'MOM', 'CEO', 'CFO',
    'IPO', 'ETF', 'USA', 'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD',
}

_TICKER_RE = re.compile(r'\$[A-Z]{1,5}|\b([A-Z]{2,5})\b')

DEFAULT_SEEDS = {
    "reddit_subreddits": [
        "stocks", "options", "investing", "StockMarket", "SecurityAnalysis"
    ],
    "reddit_users": [],
    "max_per_source": 25,
}

DEFAULT_SEED_LIST = {
    "_guide": [
        "개인 트레이더/블로거 RSS 피드를 아래 feeds에 추가하세요.",
        "추가하면 다음 실행 시 자동으로 수집됩니다.",
        "네이버 블로그 RSS: https://rss.blog.naver.com/{블로그ID}",
        "티스토리 RSS:     https://{블로그주소}/rss",
    ],
    "feeds": []
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


# ── 설정 파일 로드 ───────────────────────────────────────────

def load_seeds() -> dict:
    if not os.path.exists(SEEDS_FILE):
        with open(SEEDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_SEEDS, f, ensure_ascii=False, indent=2)
        return DEFAULT_SEEDS
    with open(SEEDS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for k, v in DEFAULT_SEEDS.items():
        data.setdefault(k, v)
    return data


def load_seed_list() -> list:
    """seed_list.json → feeds 목록 반환. 없으면 빈 파일 생성."""
    if not os.path.exists(SEED_LIST):
        with open(SEED_LIST, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_SEED_LIST, f, ensure_ascii=False, indent=2)
        print(f"  {AMBER}seed_list.json 생성됨 → 추적할 블로거 RSS를 추가하세요{RESET}")
        return []
    with open(SEED_LIST, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('feeds', [])


# ── 중복 방지 ────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def load_seen() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        return {k: v for k, v in data.items() if v >= cutoff}
    except Exception:
        return {}


def save_seen(seen: dict):
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False)


def mark_seen(seen: dict, url: str):
    seen[url_hash(url)] = datetime.now().isoformat()


def is_seen(seen: dict, url: str) -> bool:
    return url_hash(url) in seen


# ── HTTP 헬퍼 ────────────────────────────────────────────────

def fetch(url: str, timeout: int = 20) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  {ALERT}⚠ 요청 실패:{RESET} {url[:60]}... ({type(e).__name__})")
        return None


def fetch_curl(url: str, timeout: int = 20) -> str | None:
    """curl 기반 fetch — Reddit 등 TLS 핑거프린팅 차단 우회"""
    try:
        r = subprocess.run(
            ['curl', '-s', '-L',
             '--max-time', str(timeout),
             '-A', HEADERS['User-Agent'],
             '-H', f'Accept-Language: {HEADERS["Accept-Language"]}',
             '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
             url],
            capture_output=True, timeout=timeout + 5
        )
        text = r.stdout.decode('utf-8', errors='replace')
        if not text.strip():
            print(f"  {ALERT}⚠ 빈 응답:{RESET} {url[:60]}...")
            return None
        return text
    except Exception as e:
        print(f"  {ALERT}⚠ curl 실패:{RESET} {url[:60]}... ({type(e).__name__})")
        return None


def rand_delay(lo=1.5, hi=3.0):
    time.sleep(random.uniform(lo, hi))


# ── 텍스트 유틸 ─────────────────────────────────────────────

def clean_html(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def urlhost(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace('www.', '')
    except Exception:
        return url[:30]


# ── 날짜/시간 파싱 ───────────────────────────────────────────

def parse_dt(raw: str) -> datetime | None:
    """RSS 날짜 문자열 → timezone-aware datetime. 실패 시 None."""
    if not raw:
        return None
    raw = raw.strip()
    # ISO 8601: 2026-04-12T07:00:00+00:00
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        pass
    # RFC 2822: Sat, 12 Apr 2026 07:00:00 GMT
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw)
    except Exception:
        pass
    return None


def parse_date_str(raw: str) -> str:
    """날짜 문자열 → YYYY-MM-DD 문자열"""
    dt = parse_dt(raw)
    if dt:
        return dt.strftime('%Y-%m-%d')
    m = re.search(r'(\d{4}-\d{2}-\d{2})', raw or '')
    return m.group(1) if m else datetime.now().strftime('%Y-%m-%d')


# ── 필터 함수들 ──────────────────────────────────────────────

def is_fresh(raw_date: str) -> bool:
    """72시간 이내 글인지 확인"""
    dt = parse_dt(raw_date)
    if dt is None:
        return True   # 날짜 파싱 실패 시 통과 (보수적)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - dt) <= timedelta(hours=FRESHNESS_HOURS)


def is_bot_or_noise(author: str, title: str) -> bool:
    """AutoModerator 또는 공지성 게시물 여부"""
    if re.search(r'automoderator', author, re.IGNORECASE):
        return True
    title_lower = title.lower()
    for kw in NOISY_TITLE_KW:
        if kw in title_lower:
            return True
    return False


def _has_asset(text: str) -> bool:
    """특정 자산/지수/티커가 언급됐는지 확인 (① 조건)"""
    lower = text.lower()
    # 문자열 키워드 매칭
    for kw in ASSET_KW:
        if kw in lower:
            return True
    # 티커 패턴: $TSLA 또는 대문자 2~5자 (흔한 단어 제외)
    for m in _TICKER_RE.finditer(text):
        full  = m.group(0)
        inner = m.group(1)   # 괄호 캡처 (대문자 단어)
        if full.startswith('$'):
            return True      # $TSLA 형태는 무조건 티커
        if inner and inner not in _COMMON_WORDS:
            return True
    return False


def _has_direction(text: str) -> bool:
    """시장 방향성 단어가 있는지 확인 (② 조건)"""
    lower = text.lower()
    for kw in DIRECTION_KW:
        if kw in lower:
            return True
    return False


def has_relevance(text: str) -> bool:
    """① 자산/티커 AND ② 방향성 — 둘 다 있어야 True"""
    return _has_asset(text) and _has_direction(text)


def excerpt_md(text: str) -> str:
    """MD 저장용: 800자 초과 시 말줄임"""
    if len(text) > MAX_EXCERPT_MD:
        return text[:MAX_EXCERPT_MD] + '…'
    return text


# ── XML 네임스페이스 처리 ────────────────────────────────────

def strip_namespaces(xml_text: str) -> str:
    xml_clean = re.sub(r'\s+xmlns(?::[a-zA-Z0-9_]+)?="[^"]*"', '', xml_text)
    xml_clean = re.sub(r'<(/?)([a-zA-Z0-9_]+):([a-zA-Z0-9_])', r'<\1\3', xml_clean)
    xml_clean = re.sub(r'\s[a-zA-Z0-9_]+:[a-zA-Z0-9_]+=(?:"[^"]*"|\'[^\']*\')', '', xml_clean)
    return xml_clean


# ── Reddit RSS 파싱 ──────────────────────────────────────────

def parse_reddit_atom(xml_text: str, label: str, max_n: int) -> list:
    """Reddit Atom RSS → raw post 목록 (필터 전)"""
    posts = []
    try:
        xml_clean = strip_namespaces(xml_text)
        root = ET.fromstring(xml_clean)
        entries = root.findall('.//entry')
        for entry in entries[:max_n * 2]:   # 필터 후 max_n 확보용으로 넉넉히
            title_el   = entry.find('title')
            link_el    = entry.find('link')
            author_el  = entry.find('.//name')
            pub_el     = entry.find('published')
            content_el = entry.find('content')

            title      = clean_html(title_el.text) if title_el is not None else '(제목 없음)'
            url        = link_el.get('href', '') if link_el is not None else ''
            author     = (author_el.text or '').replace('/u/', 'u/') \
                         if author_el is not None else 'u/unknown'
            pub_raw    = pub_el.text if pub_el is not None else ''
            content    = content_el.text if content_el is not None else ''
            excerpt    = clean_html(content)

            if not url:
                continue

            posts.append({
                'source':   'reddit',
                'label':    label,
                'title':    title,
                'url':      url,
                'author':   author,
                'date':     parse_date_str(pub_raw),
                'pub_raw':  pub_raw,
                'excerpt':  excerpt,   # 원문 (필터·말줄임 전)
            })
    except ET.ParseError as e:
        print(f"  {ALERT}⚠ Reddit XML 파싱 오류:{RESET} {e}")
    return posts


# ── 블로그/개인 피드 RSS 파싱 ────────────────────────────────

def parse_generic_rss(xml_text: str, feed_info: dict, max_n: int) -> list:
    """RSS 2.0 / Atom → raw post 목록"""
    feed_url  = feed_info.get('rss_url', '')
    feed_name = feed_info.get('name', urlhost(feed_url))
    posts = []
    try:
        xml_clean = strip_namespaces(xml_text)
        root = ET.fromstring(xml_clean)

        # RSS 2.0
        items = root.findall('.//item')
        if items:
            for item in items[:max_n * 2]:
                title   = clean_html(item.findtext('title', ''))
                url     = (item.findtext('link') or item.findtext('guid') or '').strip()
                pub_raw = item.findtext('pubDate', '')
                author  = clean_html(item.findtext('author', item.findtext('creator', '')))
                desc    = clean_html(item.findtext('description', ''))
                if not title or not url:
                    continue
                posts.append({
                    'source':   'seed',
                    'label':    f'시드/{feed_name}',
                    'title':    title,
                    'url':      url,
                    'author':   author or feed_name,
                    'date':     parse_date_str(pub_raw),
                    'pub_raw':  pub_raw,
                    'excerpt':  desc,
                })
            return posts

        # Atom
        entries = root.findall('.//entry')
        for entry in entries[:max_n * 2]:
            title_el   = entry.find('title')
            link_el    = entry.find('link')
            author_el  = entry.find('.//name')
            pub_el     = entry.find('published') or entry.find('updated')
            summary_el = entry.find('summary') or entry.find('content')

            title   = clean_html(title_el.text) if title_el is not None else '(제목 없음)'
            url     = link_el.get('href', '') if link_el is not None else ''
            author  = author_el.text if author_el is not None else feed_name
            pub_raw = pub_el.text if pub_el is not None else ''
            desc    = clean_html(summary_el.text if summary_el is not None else '')

            if not url:
                continue
            posts.append({
                'source':   'seed',
                'label':    f'시드/{feed_name}',
                'title':    title,
                'url':      url,
                'author':   author,
                'date':     parse_date_str(pub_raw),
                'pub_raw':  pub_raw,
                'excerpt':  desc,
            })
    except ET.ParseError as e:
        print(f"  {ALERT}⚠ 블로그 RSS 파싱 오류:{RESET} {e}")
    return posts


# ── 수집 함수 ────────────────────────────────────────────────

def collect_seed_list(feeds: list, stats: dict, max_n: int) -> list:
    """seed_list.json 개인 피드 수집"""
    posts = []
    if not feeds:
        return posts

    for feed_info in feeds:
        rss_url = feed_info.get('rss_url', '')
        name    = feed_info.get('name', urlhost(rss_url))
        if not rss_url:
            continue

        print(f"  {CYAN}→ 시드 [{name}]{RESET} 수집 중...", end=' ', flush=True)
        xml = fetch_curl(rss_url)
        if not xml:
            print(f"{ALERT}실패{RESET}")
            continue

        raw = parse_generic_rss(xml, feed_info, max_n)
        accepted = []
        for p in raw:
            stats['total_raw'] += 1
            if not is_fresh(p['pub_raw']):
                stats['filtered_stale'] += 1
                continue
            if len(p['excerpt']) < MIN_EXCERPT_CHARS:
                stats['filtered_short'] += 1
                continue
            if not has_relevance(p['title'] + ' ' + p['excerpt']):
                stats['filtered_no_signal'] += 1
                continue
            accepted.append(p)

        posts.extend(accepted[:max_n])
        print(f"{CYAN}{len(accepted)}개{RESET}")
        rand_delay()

    return posts


def collect_reddit(seeds: dict, stats: dict) -> list:
    """Reddit 서브레딧 + 유저 피드 수집"""
    posts = []
    max_n = seeds.get('max_per_source', 25)

    targets = (
        [(f'Reddit/r/{sub}', f'https://old.reddit.com/r/{sub}/hot.rss?limit=50')
         for sub in seeds.get('reddit_subreddits', [])]
        +
        [(f'Reddit/u/{u.lstrip("u/")}',
          f'https://old.reddit.com/user/{u.lstrip("u/")}/submitted.rss?limit=25')
         for u in seeds.get('reddit_users', [])]
    )

    for label, url in targets:
        print(f"  {CYAN}→ {label}{RESET} 수집 중...", end=' ', flush=True)
        xml = fetch_curl(url)
        if not xml:
            print(f"{ALERT}실패{RESET}")
            rand_delay()
            continue

        raw = parse_reddit_atom(xml, label, max_n * 2)
        accepted = []
        n_bot = n_stale = n_short = n_nosig = 0
        for p in raw:
            stats['total_raw'] += 1
            # [필수] 봇·공지 제목 차단
            if is_bot_or_noise(p['author'], p['title']):
                stats['filtered_bot'] += 1
                n_bot += 1
                continue
            # 72h 필터
            if not is_fresh(p['pub_raw']):
                stats['filtered_stale'] += 1
                n_stale += 1
                continue
            # 단문 필터
            if len(p['excerpt']) < MIN_EXCERPT_CHARS:
                stats['filtered_short'] += 1
                n_short += 1
                continue
            # [OR] 예측KW 또는 자산KW 있어야 수집
            if not has_relevance(p['title'] + ' ' + p['excerpt']):
                stats['filtered_no_signal'] += 1
                n_nosig += 1
                continue
            accepted.append(p)
            if len(accepted) >= max_n:
                break

        posts.extend(accepted)
        detail = []
        if n_bot:    detail.append(f'봇·공지 {n_bot}')
        if n_stale:  detail.append(f'72h초과 {n_stale}')
        if n_short:  detail.append(f'단문 {n_short}')
        if n_nosig:  detail.append(f'자산+방향미충족 {n_nosig}')
        detail_str = ' | '.join(detail)
        print(f"{CYAN}{len(accepted)}개 신규{RESET}"
              + (f" ({detail_str} 제거)" if detail_str else ""))
        rand_delay()

    return posts


# ── 집계 & 정렬 ──────────────────────────────────────────────

def aggregate(seed_posts: list, reddit_posts: list) -> list:
    """시드 글 먼저, 레딧 글 뒤에. URL 중복 제거."""
    seen_urls = set()
    result    = []
    for p in seed_posts + reddit_posts:
        h = url_hash(p['url'])
        if h not in seen_urls:
            seen_urls.add(h)
            result.append(p)
    return result


# ── Macro & Flow Dashboard ───────────────────────────────────

_CNN_API = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
_CNN_REF = 'https://edition.cnn.com/markets/fear-and-greed'

_FG_LABEL_KO = {
    'extreme fear': '극도의 공포 🔴',
    'fear':         '공포 🟠',
    'neutral':      '중립 🟡',
    'greed':        '탐욕 🟢',
    'extreme greed':'극도의 탐욕 💚',
}


def _fetch_fear_greed() -> dict | None:
    """CNN Fear & Greed — curl 방식 (기존 fear_greed.py 동일)"""
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
            'score':  round(float(fg['score']), 1),
            'label':  _FG_LABEL_KO.get(rating, fg.get('rating', 'N/A')),
            'prev1w': round(float(fg.get('previous_1_week', 0)), 1),
        }
    except Exception:
        return None


def _fetch_vix() -> dict | None:
    """VIX 현재가 + 전일 대비"""
    try:
        hist = yf.Ticker('^VIX').history(period='5d')
        if len(hist) < 2:
            return None
        curr = float(hist['Close'].iloc[-1])
        prev = float(hist['Close'].iloc[-2])
        chg  = curr - prev
        return {
            'price':   round(curr, 2),
            'change':  round(chg, 2),
            'pct':     round(chg / prev * 100, 1),
        }
    except Exception:
        return None


def _fetch_cot_sp500() -> dict | None:
    """CFTC Traders in Financial Futures — E-mini S&P 500
    Leveraged Funds(헤지펀드) Net Position 파싱"""
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
            if 'E-MINI S&P 500' not in name and 'S&P 500 STOCK' not in name:
                continue
            # 헤더에서 컬럼 인덱스 찾기
            def idx(keyword):
                for i, h in enumerate(header):
                    if keyword in h:
                        return i
                return None

            date_i  = idx('report_date_as_yyyy')
            lev_l_i = idx('lev_money_positions_long')
            lev_s_i = idx('lev_money_positions_short')
            # 헤더 없으면 위치 기반 폴백 (TFF 표준 위치)
            if date_i  is None: date_i  = 2
            if lev_l_i is None: lev_l_i = 14
            if lev_s_i is None: lev_s_i = 15

            def to_int(s):
                return int(str(s).strip().strip('"').replace(',', '') or 0)

            date      = row[date_i].strip().strip('"') if len(row) > date_i else 'N/A'
            lev_long  = to_int(row[lev_l_i]) if len(row) > lev_l_i else 0
            lev_short = to_int(row[lev_s_i]) if len(row) > lev_s_i else 0
            net       = lev_long - lev_short
            direction = '매수 우위 📈' if net > 0 else '매도 우위 📉'
            return {
                'date':      date[:10],
                'lev_long':  lev_long,
                'lev_short': lev_short,
                'net':       net,
                'direction': direction,
            }
        return None
    except Exception:
        return None


def _fetch_yahoo_headlines(n: int = 5) -> list:
    """Yahoo Finance RSS — 거시/증시 헤드라인"""
    feeds = [
        'https://finance.yahoo.com/news/rss/',
        'https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US',
    ]
    for url in feeds:
        try:
            xml_text = fetch(url)
            if not xml_text:
                continue
            xml_clean = strip_namespaces(xml_text)
            root  = ET.fromstring(xml_clean)
            items = root.findall('.//item')
            results = []
            for item in items[:n]:
                title = clean_html(item.findtext('title', ''))
                link  = item.findtext('link', '').strip()
                pub   = parse_date_str(item.findtext('pubDate', ''))
                if title:
                    results.append({'title': title, 'url': link, 'date': pub})
            if results:
                return results
        except Exception:
            continue
    return []


def build_macro_dashboard() -> tuple:
    """Macro & Flow Dashboard — (markdown_str, data_dict) 반환"""
    print(f"  {CYAN}→ Fear & Greed 수집 중...{RESET}", end=' ', flush=True)
    fg  = _fetch_fear_greed()
    print(f"{CYAN}완료{RESET}" if fg else f"{AMBER}실패{RESET}")

    print(f"  {CYAN}→ VIX 수집 중...{RESET}", end=' ', flush=True)
    vix = _fetch_vix()
    print(f"{CYAN}완료{RESET}" if vix else f"{AMBER}실패{RESET}")

    print(f"  {CYAN}→ CFTC COT 수집 중...{RESET}", end=' ', flush=True)
    cot = _fetch_cot_sp500()
    print(f"{CYAN}완료{RESET}" if cot else f"{AMBER}실패{RESET}")

    print(f"  {CYAN}→ Yahoo Finance 헤드라인 수집 중...{RESET}", end=' ', flush=True)
    headlines = _fetch_yahoo_headlines(5)
    print(f"{CYAN}{len(headlines)}건{RESET}" if headlines else f"{AMBER}실패{RESET}")

    # ── 마크다운 생성 ────────────────────────────────────────
    lines = ['## 🌐 [Macro & Flow Dashboard]', '']

    # 1. 시장 온도계
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
        lines.append(f'- **VIX**: `{vix["price"]:.2f}`  '
                     f'({sign}{vix["change"]:.2f}, {sign}{vix["pct"]:.1f}%)  {vix_note}')
    else:
        lines.append('- **VIX**: 조회 실패')

    lines.append('')

    # 2. 스마트 머니 (CFTC COT)
    lines.append('### 🏦 스마트 머니 포지션 (CFTC COT)')
    if cot:
        net_str = f'+{cot["net"]:,}' if cot['net'] >= 0 else f'{cot["net"]:,}'
        lines.append(f'- **E-mini S&P 500 Leveraged Funds Net** ({cot["date"]}): '
                     f'`{net_str}` 계약 — {cot["direction"]}')
        lines.append(f'  - Long: {cot["lev_long"]:,}계약 / Short: {cot["lev_short"]:,}계약')
        lines.append(f'  > 헤지펀드 포지션. 양수=순매수, 음수=순매도 (매주 금요일 갱신)')
    else:
        lines.append('- CFTC COT 조회 실패 (매주 금요일 갱신, 3일 시차)')

    lines.append('')

    # 3. Yahoo Finance 헤드라인
    lines.append('### 📰 주요 거시/증시 헤드라인 (Yahoo Finance)')
    if headlines:
        for h in headlines:
            title = h['title'].replace('[', '\\[').replace(']', '\\]')
            lines.append(f'- [{title}]({h["url"]})  _{h["date"]}_')
    else:
        lines.append('- 헤드라인 조회 실패')

    lines += ['', '---', '']

    macro_data = {
        'fg':        fg,
        'vix':       vix,
        'cot':       cot,
        'headlines': headlines,
    }
    return '\n'.join(lines), macro_data


# ── 마크다운 생성 ────────────────────────────────────────────

def generate_markdown(posts: list, ts: str, stats: dict, macro_md: str = '') -> str:
    today = datetime.now().strftime('%Y-%m-%d')

    stat_line = (
        f"📊 수집통계 | 최종저장 {stats['final']}건 "
        f"| 봇·공지 제거 {stats['filtered_bot']}건 "
        f"| 72h초과 제거 {stats['filtered_stale']}건 "
        f"| 단문 제거 {stats['filtered_short']}건 "
        f"| 자산+방향 미충족 제거 {stats['filtered_no_signal']}건"
    )

    lines = [
        f'# Alpha Hunter — {today}',
        f'수집 시각: {ts} KST',
        f'',
        stat_line,
        f'',
        f'> 이 파일을 AI(Claude, ChatGPT, Gemini 등)에게 통째로 붙여넣어 분석을 요청하세요.',
        f'> 예시 프롬프트: "위 대시보드와 아래 {len(posts)}개 글을 종합해 시장 방향성을 분석해줘."',
        f'',
        f'---',
        f'',
    ]

    # ★ Macro Dashboard 삽입 (수집 통계 바로 아래)
    if macro_md:
        lines.append(macro_md)

    # 시드 글 먼저
    seed_posts   = [p for p in posts if p['source'] == 'seed']
    reddit_posts = [p for p in posts if p['source'] == 'reddit']

    def write_group(group: list):
        source_groups: dict = {}
        for p in group:
            source_groups.setdefault(p['label'], []).append(p)
        for label, items in source_groups.items():
            lines.append(f'## {label} ({len(items)}개)')
            lines.append('')
            for p in items:
                raw_ex = p.get('excerpt', '')
                md_ex  = excerpt_md(raw_ex)   # MD용: 800자 제한
                lines.append(f'### {p["title"]}')
                lines.append(f'- 작성자: {p["author"]}')
                lines.append(f'- 날짜: {p["date"]}')
                lines.append(f'- 링크: {p["url"]}')
                if md_ex:
                    lines.append(f'')
                    lines.append(f'> {md_ex}')
                lines.append('')
                lines.append('---')
                lines.append('')

    if seed_posts:
        lines.append('<!-- ★ 시드 등록 작성자 글 ★ -->')
        lines.append('')
        write_group(seed_posts)

    if reddit_posts:
        lines.append('<!-- Reddit 수집 -->')
        lines.append('')
        write_group(reddit_posts)

    return '\n'.join(lines)


def save_markdown(md_text: str) -> str:
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    date_str = datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(SIGNALS_DIR, f'{date_str}.md')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_text)
    return filepath


# ── HTML 생성 ────────────────────────────────────────────────

SOURCE_COLORS = {
    'seed':    ('#2e7d32', '#edf7ee', '#2e7d32'),
    'reddit':  ('#c94b2b', '#fff1ee', '#c94b2b'),
}
SOURCE_LABELS_MAP = {
    'seed':   '시드 피드',
    'reddit': 'Reddit',
}


def build_cards_html(posts: list) -> str:
    if not posts:
        return '<div class="empty">수집된 글이 없습니다. seed_list.json을 확인하거나 잠시 후 재실행하세요.</div>'

    parts = []
    for p in posts:
        src    = p['source']
        sc     = SOURCE_COLORS.get(src, ('#555', '#f5f5f5', '#ccc'))
        slabel = SOURCE_LABELS_MAP.get(src, src)
        raw_ex = p.get('excerpt', '')
        disp_ex = excerpt_md(raw_ex)

        excerpt_html = ''
        if disp_ex:
            ex = disp_ex.replace('<', '&lt;').replace('>', '&gt;')
            excerpt_html = f'<p class="excerpt">{ex}</p>'

        parts.append(f'''
<div class="card" data-source="{src}">
  <div class="card-header">
    <span class="badge" style="color:{sc[0]};background:{sc[1]};border-color:{sc[2]}">{slabel}</span>
    <span class="card-label">{p["label"].replace("<","&lt;").replace(">","&gt;")}</span>
    <span class="card-date">{p["date"]}</span>
  </div>
  <a class="card-title" href="{p["url"]}" target="_blank" rel="noopener">
    {p["title"].replace("<","&lt;").replace(">","&gt;")}
  </a>
  <div class="card-meta">
    <span>✍ {p["author"].replace("<","&lt;")}</span>
  </div>
  {excerpt_html}
  <div class="card-footer">
    <a href="{p["url"]}" target="_blank" rel="noopener" class="link-btn">원문 열기 →</a>
  </div>
</div>''')

    return '\n'.join(parts)


def build_macro_html(macro_data: dict) -> str:
    """Macro & Flow Dashboard HTML 섹션 생성"""
    if not macro_data:
        return ''

    fg        = macro_data.get('fg')
    vix       = macro_data.get('vix')
    cot       = macro_data.get('cot')
    headlines = macro_data.get('headlines', [])

    # ── Fear & Greed 바 ─────────────────────────────────────
    if fg:
        score   = fg['score']
        pct     = score  # 0~100 → %
        # 색상 구간
        if score <= 25:
            bar_color = '#c62828'   # 극도 공포 (붉은)
        elif score <= 45:
            bar_color = '#e65100'   # 공포 (주황)
        elif score <= 55:
            bar_color = '#7b6f3a'   # 중립 (올리브)
        elif score <= 75:
            bar_color = '#00838f'   # 탐욕 (teal)
        else:
            bar_color = '#1a5c3a'   # 극도 탐욕 (녹색)

        prev_html = ''
        if fg.get('prev1w'):
            delta = round(score - fg['prev1w'], 1)
            sign  = '+' if delta >= 0 else ''
            prev_html = f'<span class="mcd-prev">1주전 {fg["prev1w"]} ({sign}{delta})</span>'

        fg_html = f'''
<div class="mcd-card">
  <div class="mcd-card-title">📊 CNN Fear &amp; Greed</div>
  <div class="mcd-score" style="color:{bar_color}">{score}</div>
  <div class="mcd-label" style="color:{bar_color}">{fg["label"]}</div>
  <div class="mcd-bar-wrap">
    <div class="mcd-bar-bg">
      <div class="mcd-bar-fill" style="width:{pct}%;background:{bar_color}"></div>
    </div>
    <div class="mcd-bar-range"><span>0 극도공포</span><span>100 극도탐욕</span></div>
  </div>
  {prev_html}
</div>'''
    else:
        fg_html = '<div class="mcd-card"><div class="mcd-card-title">📊 CNN Fear &amp; Greed</div><div class="mcd-na">조회 실패</div></div>'

    # ── VIX ─────────────────────────────────────────────────
    if vix:
        sign     = '+' if vix['change'] >= 0 else ''
        vix_col  = '#c62828' if vix['change'] > 2 else ('#e65100' if vix['change'] > 0 else '#00838f')
        vix_note = '공포 상승 ↑' if vix['change'] > 0 else '공포 완화 ↓'
        vix_html = f'''
<div class="mcd-card">
  <div class="mcd-card-title">🌡 VIX (공포지수)</div>
  <div class="mcd-score" style="color:{vix_col}">{vix["price"]:.2f}</div>
  <div class="mcd-label" style="color:{vix_col}">{vix_note}</div>
  <div class="mcd-sub">{sign}{vix["change"]:.2f} &nbsp;({sign}{vix["pct"]:.1f}%) 전일 대비</div>
</div>'''
    else:
        vix_html = '<div class="mcd-card"><div class="mcd-card-title">🌡 VIX</div><div class="mcd-na">조회 실패</div></div>'

    # ── CFTC COT ─────────────────────────────────────────────
    if cot:
        net_val  = cot['net']
        net_str  = f'+{net_val:,}' if net_val >= 0 else f'{net_val:,}'
        cot_col  = '#00838f' if net_val >= 0 else '#c62828'
        cot_html = f'''
<div class="mcd-card mcd-card-wide">
  <div class="mcd-card-title">🏦 스마트 머니 (CFTC COT E-mini S&amp;P 500)</div>
  <div class="mcd-score" style="color:{cot_col}">{net_str}</div>
  <div class="mcd-label" style="color:{cot_col}">{cot["direction"]}</div>
  <div class="mcd-sub">Leveraged Funds — Long: {cot["lev_long"]:,} / Short: {cot["lev_short"]:,} &nbsp;({cot["date"]} 기준)</div>
  <div class="mcd-hint">헤지펀드 순포지션. 양수=순매수 우위, 음수=순매도 우위 (매주 금요일 갱신)</div>
</div>'''
    else:
        cot_html = '<div class="mcd-card mcd-card-wide"><div class="mcd-card-title">🏦 스마트 머니 (CFTC COT)</div><div class="mcd-na">조회 실패 (매주 금요일 갱신, 3일 시차)</div></div>'

    # ── Yahoo Headlines ───────────────────────────────────────
    if headlines:
        hl_items = '\n'.join(
            f'<li><a href="{h["url"]}" target="_blank" rel="noopener">'
            f'{h["title"].replace("<","&lt;").replace(">","&gt;")}'
            f'</a> <span class="hl-date">{h["date"]}</span></li>'
            for h in headlines
        )
        hl_html = f'''
<div class="mcd-headlines">
  <div class="mcd-card-title">📰 주요 거시/증시 헤드라인 (Yahoo Finance)</div>
  <ul class="hl-list">{hl_items}</ul>
</div>'''
    else:
        hl_html = '<div class="mcd-headlines"><div class="mcd-card-title">📰 Yahoo Finance 헤드라인</div><div class="mcd-na">조회 실패</div></div>'

    return f'''
<section class="macro-section">
  <div class="macro-inner">
    <h2 class="macro-title">🌐 Macro &amp; Flow Dashboard</h2>
    <div class="mcd-grid">
      {fg_html}
      {vix_html}
      {cot_html}
    </div>
    {hl_html}
  </div>
</section>'''


def generate_html(posts: list, md_text: str, ts: str,
                  seeds: dict, stats: dict,
                  macro_data: dict | None = None) -> str:
    today      = datetime.now().strftime('%Y-%m-%d')
    md_fn      = f'{today}.md'
    cards_html = build_cards_html(posts)
    md_json    = json.dumps(md_text)
    macro_html = build_macro_html(macro_data) if macro_data else ''

    cnt_seed   = sum(1 for p in posts if p['source'] == 'seed')
    cnt_reddit = sum(1 for p in posts if p['source'] == 'reddit')

    seed_feeds = []
    if os.path.exists(SEED_LIST):
        with open(SEED_LIST, 'r', encoding='utf-8') as f:
            sl = json.load(f)
        seed_feeds = sl.get('feeds', [])

    seeds_info = ', '.join(
        f"{fd.get('name', urlhost(fd.get('rss_url','')))} ({urlhost(fd.get('rss_url',''))})"
        for fd in seed_feeds
    ) or '(등록된 피드 없음 — seed_list.json에 추가하세요)'

    subreddits_info = ', '.join(f'r/{s}' for s in seeds.get('reddit_subreddits', []))

    stat_html = (
        f"최종저장 <b>{stats['final']}</b>건 &nbsp;|&nbsp; "
        f"봇·공지 <b>{stats['filtered_bot']}</b>건 &nbsp;|&nbsp; "
        f"72h초과 <b>{stats['filtered_stale']}</b>건 &nbsp;|&nbsp; "
        f"단문 <b>{stats['filtered_short']}</b>건 &nbsp;|&nbsp; "
        f"자산+방향미충족 <b>{stats['filtered_no_signal']}</b>건 제거"
    )

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alpha Hunter — {today}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: #f5f4ef;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
    color: #2c2a25;
    min-height: 100vh;
  }}

  .site-header {{
    background: #fff;
    border-bottom: 1px solid #e4e1d8;
    padding: 18px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 1px 6px rgba(0,0,0,.06);
  }}
  .site-title {{ font-size: 22px; font-weight: 700; color: #3b3529; }}
  .site-subtitle {{ font-size: 13px; color: #7a7060; margin-top: 2px; }}
  .header-right {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}

  .btn {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 9px 18px; border-radius: 8px;
    font-size: 14px; font-weight: 600; cursor: pointer; border: none;
    transition: all .15s; text-decoration: none;
  }}
  .btn-primary  {{ background: #4a3f2f; color: #fff; }}
  .btn-primary:hover  {{ background: #5c4f3a; transform: translateY(-1px); }}
  .btn-secondary {{ background: #fff; color: #4a3f2f; border: 1.5px solid #c8c0ae; }}
  .btn-secondary:hover {{ background: #f0ede5; transform: translateY(-1px); }}
  .btn-success  {{ background: #1a5c3a; color: #fff; }}
  .btn-success:hover  {{ background: #236946; transform: translateY(-1px); }}
  .btn.copied   {{ background: #1a5c3a !important; }}

  .stats-bar {{
    background: #fff;
    border-bottom: 1px solid #e4e1d8;
    padding: 10px 24px;
    font-size: 13px;
    color: #6b6052;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .stats-bar b {{ color: #3b3529; }}

  .filter-summary {{
    background: #fdf9f1;
    border-bottom: 1px solid #e4e1d8;
    padding: 8px 24px;
    font-size: 12px;
    color: #8a7d6a;
  }}

  .cnt-badge {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 10px; border-radius: 10px;
    font-size: 12px; font-weight: 700;
  }}
  .cnt-seed   {{ background:#edf7ee; color:#2e7d32; }}
  .cnt-reddit {{ background:#fff1ee; color:#c94b2b; }}

  .filter-bar {{ padding: 14px 24px 0; display: flex; gap: 8px; flex-wrap: wrap; }}
  .filter-btn {{
    padding: 6px 16px; border-radius: 20px;
    border: 1.5px solid #d4cfc5; background: #fff;
    font-size: 13px; font-weight: 500; cursor: pointer; color: #5a5040;
    transition: all .12s;
  }}
  .filter-btn:hover {{ background: #ebe8e0; }}
  .filter-btn.active {{ background: #4a3f2f; color: #fff; border-color: #4a3f2f; }}

  .main {{ max-width: 900px; margin: 0 auto; padding: 20px 20px 60px; }}
  .cards {{ display: flex; flex-direction: column; gap: 14px; margin-top: 18px; }}

  .card {{
    background: #fff; border: 1px solid #e4e1d8;
    border-radius: 12px; padding: 18px 20px;
    transition: box-shadow .15s, transform .1s;
  }}
  .card:hover {{ box-shadow: 0 4px 18px rgba(0,0,0,.08); transform: translateY(-1px); }}
  .card.seed-card {{ border-left: 3px solid #2e7d32; }}
  .card.hidden {{ display: none; }}

  .card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }}
  .badge {{
    display: inline-block; padding: 3px 10px; border-radius: 6px;
    font-size: 11px; font-weight: 700; border: 1px solid; letter-spacing: .3px;
  }}
  .card-label {{ font-size: 12px; color: #8a7d6a; flex: 1; }}
  .card-date  {{ font-size: 12px; color: #aaa098; white-space: nowrap; }}

  .card-title {{
    display: block; font-size: 16px; font-weight: 600; color: #2c2a25;
    line-height: 1.45; text-decoration: none; margin-bottom: 6px;
  }}
  .card-title:hover {{ color: #6b4f2a; text-decoration: underline; }}
  .card-meta {{ font-size: 12px; color: #8a7d6a; margin-bottom: 10px; }}

  .excerpt {{
    font-size: 13.5px; color: #5a5040; line-height: 1.65;
    background: #f9f8f4; border-left: 3px solid #d4cfc5;
    padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 12px;
  }}
  .card-footer {{ text-align: right; }}
  .link-btn {{ font-size: 13px; color: #6b4f2a; text-decoration: none; font-weight: 500; }}
  .link-btn:hover {{ text-decoration: underline; }}

  .info-panel {{
    background: #fff; border: 1px solid #e4e1d8; border-radius: 12px;
    padding: 16px 20px; margin-top: 28px; font-size: 13px; color: #6b6052; line-height: 1.9;
  }}
  .info-panel h3 {{ font-size: 14px; font-weight: 600; color: #3b3529; margin-bottom: 8px; }}
  .info-panel code {{ background: #f0ede5; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}

  .empty {{ text-align: center; padding: 60px 20px; color: #8a7d6a; font-size: 16px; }}

  /* ── Macro Dashboard ── */
  .macro-section {{
    background: #fff;
    border-bottom: 1px solid #e4e1d8;
    padding: 20px 24px 22px;
  }}
  .macro-inner {{ max-width: 900px; margin: 0 auto; }}
  .macro-title {{
    font-size: 16px; font-weight: 700; color: #3b3529;
    margin-bottom: 14px; display: flex; align-items: center; gap: 6px;
  }}
  .mcd-grid {{
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px;
  }}
  .mcd-card {{
    background: #fdf9f1; border: 1px solid #e4e1d8; border-radius: 10px;
    padding: 14px 18px; min-width: 170px; flex: 1;
  }}
  .mcd-card-wide {{ flex: 2 1 320px; }}
  .mcd-card-title {{
    font-size: 12px; font-weight: 600; color: #8a7d6a;
    text-transform: uppercase; letter-spacing: .4px; margin-bottom: 6px;
  }}
  .mcd-score {{
    font-size: 32px; font-weight: 800; line-height: 1.1; margin-bottom: 2px;
  }}
  .mcd-label {{ font-size: 14px; font-weight: 600; margin-bottom: 8px; }}
  .mcd-sub   {{ font-size: 12px; color: #6b6052; margin-top: 4px; }}
  .mcd-hint  {{ font-size: 11px; color: #aaa098; margin-top: 6px; line-height: 1.5; }}
  .mcd-na    {{ font-size: 13px; color: #aaa098; padding: 10px 0; }}
  .mcd-prev  {{ font-size: 12px; color: #8a7d6a; }}
  .mcd-bar-wrap {{ margin-top: 8px; }}
  .mcd-bar-bg {{
    height: 8px; background: #e4e1d8; border-radius: 4px; overflow: hidden;
    margin-bottom: 4px;
  }}
  .mcd-bar-fill {{ height: 100%; border-radius: 4px; transition: width .5s; }}
  .mcd-bar-range {{
    display: flex; justify-content: space-between;
    font-size: 10px; color: #aaa098; margin-bottom: 6px;
  }}
  .mcd-headlines {{
    background: #fdf9f1; border: 1px solid #e4e1d8; border-radius: 10px;
    padding: 14px 18px;
  }}
  .hl-list {{ list-style: none; padding: 0; margin: 8px 0 0; }}
  .hl-list li {{
    padding: 6px 0; border-bottom: 1px solid #eeebe3;
    font-size: 13.5px; line-height: 1.5;
    display: flex; justify-content: space-between; align-items: baseline; gap: 10px;
  }}
  .hl-list li:last-child {{ border-bottom: none; }}
  .hl-list a {{ color: #3b3529; text-decoration: none; flex: 1; }}
  .hl-list a:hover {{ color: #6b4f2a; text-decoration: underline; }}
  .hl-date {{ font-size: 11px; color: #aaa098; white-space: nowrap; }}

  #toast {{
    position: fixed; bottom: 30px; left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: #2c2a25; color: #fff;
    padding: 10px 22px; border-radius: 24px; font-size: 14px;
    opacity: 0; transition: all .3s; pointer-events: none; z-index: 9999;
  }}
  #toast.show {{ opacity: 1; transform: translateX(-50%) translateY(0); }}

  @media (max-width: 600px) {{
    .site-header {{ padding: 14px 16px; }}
    .main {{ padding: 14px 12px 50px; }}
    .filter-bar {{ padding: 12px 12px 0; }}
    .card {{ padding: 14px 16px; }}
    .btn {{ padding: 8px 14px; font-size: 13px; }}
  }}
</style>
</head>
<body>

<header class="site-header">
  <div>
    <div class="site-title">🎯 Alpha Hunter</div>
    <div class="site-subtitle">수집 시각: {ts} KST &nbsp;|&nbsp; {today}</div>
  </div>
  <div class="header-right">
    <button class="btn btn-primary" onclick="copyAll()" id="copyBtn">📋 전체 복사</button>
    <button class="btn btn-success" onclick="downloadMd()">⬇ MD 다운로드</button>
  </div>
</header>

<div class="stats-bar">
  📊 {stat_html}
  &nbsp;&nbsp;
  <span class="cnt-badge cnt-seed">시드 {cnt_seed}</span>
  <span class="cnt-badge cnt-reddit">Reddit {cnt_reddit}</span>
</div>

<div class="filter-summary">
  <b>시드 피드:</b> {seeds_info} &nbsp;|&nbsp;
  <b>서브레딧:</b> {subreddits_info}
</div>

{macro_html}

<div class="filter-bar">
  <button class="filter-btn active" onclick="filterCards(this,'all')">전체 {len(posts)}</button>
  <button class="filter-btn" onclick="filterCards(this,'seed')">시드 피드 {cnt_seed}</button>
  <button class="filter-btn" onclick="filterCards(this,'reddit')">Reddit {cnt_reddit}</button>
</div>

<div class="main">
  <div class="cards" id="cards">
    {cards_html}
  </div>

  <div class="info-panel">
    <h3>⚙ 수집 설정 안내</h3>
    <b>시드 피드 추가:</b> <code>seed_list.json</code>의 feeds 배열에 등록<br>
    &nbsp;&nbsp;예시: <code>{{"name": "홍길동", "rss_url": "https://rss.blog.naver.com/blogID"}}</code><br>
    <b>서브레딧 변경:</b> <code>alpha_hunter_seeds.json</code> 수정<br>
    <b>필터 기준:</b> 72시간 이내 | 본문 150자+ | 봇·공지 제외 | 예측·자산 키워드 OR 조건
  </div>
</div>

<div id="toast"></div>

<script>
const MD_CONTENT = {md_json};
const MD_FILENAME = '{md_fn}';

function showToast(msg, ms) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms || 2500);
}}

function copyAll() {{
  navigator.clipboard.writeText(MD_CONTENT).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✅ 복사 완료!';
    btn.classList.add('copied');
    showToast('클립보드 복사 완료! AI에 바로 붙여넣으세요.', 3000);
    setTimeout(() => {{ btn.textContent = '📋 전체 복사'; btn.classList.remove('copied'); }}, 2500);
  }}).catch(() => {{
    const ta = document.createElement('textarea');
    ta.value = MD_CONTENT;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('복사 완료!', 2000);
  }});
}}

function downloadMd() {{
  const blob = new Blob([MD_CONTENT], {{ type: 'text/markdown;charset=utf-8' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = MD_FILENAME;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast(MD_FILENAME + ' 다운로드 시작!', 2000);
}}

function filterCards(btn, source) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#cards .card').forEach(card => {{
    card.classList.toggle('hidden',
      source !== 'all' && card.dataset.source !== source);
  }});
}}
</script>
</body>
</html>'''


# ── 메인 ────────────────────────────────────────────────────

def main():
    print(f"\n{'━'*62}")
    print(f"  🎯 Alpha Hunter V1.3 — 증시 고수 글 수집 + Macro Dashboard")
    print(f"  필터: 72h이내 | 본문150자+ | 봇·공지 | 자산AND방향 키워드")
    print(f"{'━'*62}\n")

    seeds  = load_seeds()
    feeds  = load_seed_list()

    stats = {
        'total_raw':          0,
        'filtered_bot':       0,
        'filtered_stale':     0,
        'filtered_short':     0,
        'filtered_no_signal': 0,
        'final':              0,
    }

    max_n = seeds.get('max_per_source', 25)

    print(f"  {CYAN}[1/3] 시드 피드 수집 중... ({len(feeds)}개 등록){RESET}")
    if not feeds:
        print(f"  {AMBER}  → seed_list.json에 피드가 없습니다. Reddit만 수집합니다.{RESET}")
    seed_posts   = collect_seed_list(feeds, stats, max_n)

    print(f"\n  {CYAN}[2/3] Reddit 수집 중...{RESET}")
    reddit_posts = collect_reddit(seeds, stats)

    print(f"\n  {CYAN}[3/3] Macro Dashboard 수집 중...{RESET}")
    macro_md, macro_data = build_macro_dashboard()

    print(f"\n  {CYAN}[4/4] 결과 저장 중...{RESET}")
    posts = aggregate(seed_posts, reddit_posts)
    stats['final'] = len(posts)

    ts      = datetime.now().strftime('%Y-%m-%d %H:%M')
    md_text = generate_markdown(posts, ts, stats, macro_md)
    md_path = save_markdown(md_text)
    print(f"  {CYAN}● MD 저장:{RESET} {md_path}")

    html = generate_html(posts, md_text, ts, seeds, stats, macro_data)
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  {CYAN}● HTML 생성:{RESET} {HTML_OUT}")

    print(f"\n{'─'*62}")
    print(f"  ✅ 최종 저장: {stats['final']}건")
    print(f"     시드 피드:  {sum(1 for p in posts if p['source']=='seed')}건")
    print(f"     Reddit:     {sum(1 for p in posts if p['source']=='reddit')}건")
    print(f"  🚫 필터 제거: 봇·공지 {stats['filtered_bot']}건 | "
          f"72h초과 {stats['filtered_stale']}건 | "
          f"단문 {stats['filtered_short']}건 | "
          f"자산+방향미충족 {stats['filtered_no_signal']}건")
    print(f"\n  💡 AI 분석: HTML에서 '전체 복사' → AI에 붙여넣기")
    print(f"{'━'*62}\n")

    webbrowser.open(f'file://{HTML_OUT}')


if __name__ == '__main__':
    main()
