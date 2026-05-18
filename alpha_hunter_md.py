from __future__ import annotations
"""Alpha Hunter — 마크다운 생성 + 필터링 유틸리티
텍스트 파싱, 필터링, 마크다운 생성"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html import unescape
from email.utils import parsedate_to_datetime

from jm_lib.colors import ALERT, RESET
from alpha_hunter_base import (
    FRESHNESS_HOURS, MIN_EXCERPT_CHARS, MAX_EXCERPT_MD,
    NOISY_TITLE_KW, DIRECTION_KW, ASSET_KW,
    SIGNALS_DIR,
)

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

# 지정학·매크로 단독 통과 키워드 (100자 이상 본문에 한해)
_GEO_MACRO_KW = [
    # 지정학
    'iran', 'israel', 'middle east', 'vance', 'ceasefire', 'hormuz',
    'escalation', 'war', 'negotiation', 'hamas', 'hezbollah', 'houthi',
    'airstrike', 'sanctions', 'nuclear deal', 'opec',
    'nato', 'taiwan strait', 'chip ban', 'china sanctions', 'ukraine',
    'crude', 'brent', 'oil',
    # 거시경제
    'fed', 'federal reserve', 'fomc', 'cpi', 'inflation', 'pce',
    'gdp', 'recession', 'treasury', 'yield curve',
    'rate cut', 'rate hike', 'tariff', 'trade war',
    # 한국어
    '이란', '이스라엘', '중동', '밴스', '휴전', '호르무즈', '확전',
    '유가', '전쟁', '협상', '핵협상', '헤즈볼라', '하마스', '후티',
    '제재', '공습', '연준', '기준금리', '인플레', '금리인하', '금리인상',
    '소비자물가', '경기침체', '관세', '무역전쟁', '대만해협', '반도체제재',
]


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


def _geo_macro_hit(text: str) -> str | None:
    """지정학·매크로 키워드 매칭 → 처음 히트한 키워드 반환, 없으면 None"""
    lower = text.lower()
    for kw in _GEO_MACRO_KW:
        if kw in lower:
            return kw
    return None


def check_reddit_pass(excerpt: str, text: str) -> str | None:
    """Reddit 글 수집 통과 여부 판정.
    반환값: 'ASSET_DIRECTION' | 'GEO_MACRO:<kw>' | None(탈락)

    순서 (변경 금지):
      1. 단문 체크 → 100자 미만이면 지정학 여부 무관 탈락
      2. 자산+방향 AND 조건 → 통과
      3. 지정학·매크로 단독 → 통과
      4. 그 외 → 탈락
    단, 단문 체크(① 100자)는 collect_reddit() 에서 MIN_EXCERPT_CHARS(150자) 체크 이후에
    호출되므로, 이 함수에서는 이미 150자 이상이 보장된 상태.
    → 지정학 경로는 별도 100자 체크 불필요 (호출 시점에 이미 통과).
    """
    if has_relevance(text):
        return 'ASSET_DIRECTION'
    hit = _geo_macro_hit(text)
    if hit:
        return f'GEO_MACRO:{hit}'
    return None


# ── Yahoo 헤드라인 우선순위 분류 ────────────────────────────

_HL_GEO = {
    'iran', 'hormuz', 'ceasefire', 'war', 'conflict', 'vance', 'israel',
    'oil price', 'sanctions', 'nuclear deal', 'airstrike', 'escalation', 'houthi',
}
_HL_MACRO = {
    'fed', 'fomc', 'cpi', 'inflation', 'gdp', 'recession',
    'rate cut', 'rate hike', 'treasury yield', 'pce',
    'unemployment', 'payroll', 'tariff', 'trade war',
}
_HL_MARKET = {
    's&p', 'nasdaq', 'dow', 'market', 'earnings season', 'guidance', 'outlook',
}


def _classify_headline(title: str) -> tuple:
    """Yahoo 헤드라인 우선순위 분류 → (priority:int, label:str)"""
    lower = title.lower()
    for kw in _HL_GEO:
        if kw in lower:
            return (1, '🚨 지정학속보')
    for kw in _HL_MACRO:
        if kw in lower:
            return (2, '📊 거시경제')
    for kw in _HL_MARKET:
        if kw in lower:
            return (3, '📈 시장전반')
    return (4, '🏢 개별종목')


def sort_headlines(headlines: list) -> list:
    """우선순위 정렬 후 상위 8개 반환. 각 항목에 'priority', 'label' 키 추가.
    동일 우선순위 내에서는 최신 기사 우선 (date 내림차순).
    priority 4(개별종목/무관 기사)는 1~3 기사가 8개 미만일 때만 채움.
    Python stable sort 2단계: ① date 내림차순 → ② priority 오름차순"""
    for h in headlines:
        pri, lbl = _classify_headline(h['title'])
        h['priority'] = pri
        h['label']    = lbl
    # ① date 최신순 (stable)
    by_date = sorted(headlines, key=lambda h: h.get('date', ''), reverse=True)
    # ② priority 우선순위순 (stable → 동일 priority는 ①의 date 순서 유지)
    sorted_all = sorted(by_date, key=lambda h: h['priority'])
    # 우선순위 1~3 기사 먼저 최대 8개
    top = [h for h in sorted_all if h['priority'] <= 3][:8]
    # 좋은 기사가 3개 미만일 때만 4등급(노이즈)으로 보충
    if len(top) < 3:
        top += [h for h in sorted_all if h['priority'] == 4][:3 - len(top)]
    return top


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
    import os
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    date_str = datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(SIGNALS_DIR, f'{date_str}.md')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_text)
    return filepath


__all__ = [
    'clean_html', 'urlhost',
    'parse_dt', 'parse_date_str',
    'is_fresh', 'is_bot_or_noise', 'has_relevance', 'check_reddit_pass',
    '_classify_headline', 'sort_headlines',
    'excerpt_md', 'strip_namespaces',
    'parse_reddit_atom', 'parse_generic_rss',
    'generate_markdown', 'save_markdown',
]
