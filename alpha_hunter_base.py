"""Alpha Hunter — 기본 설정 및 유틸리티
증시 고수 글 자동 수집 기본 함수들"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

# ═══ 파일 경로 설정 ═══

DIR = os.path.dirname(os.path.abspath(__file__))
SEEDS_FILE = os.path.join(DIR, 'state', 'alpha_hunter_seeds.json')
SEED_LIST = os.path.join(DIR, 'state', 'seed_list.json')
SEEN_FILE = os.path.join(DIR, 'alpha_hunter_seen.json')
SIGNALS_DIR = os.path.join(DIR, 'signals')
HTML_OUT = os.path.join(DIR, 'alpha_hunter.html')

FRESHNESS_HOURS = 18
MIN_EXCERPT_CHARS = 150
MAX_EXCERPT_MD = 800

# ═══ 키워드 정의 ═══

# Reddit 공지성 제목 차단
NOISY_TITLE_KW = [
    'daily', 'weekly', 'weekend', 'thread', 'megathread',
    'rate my portfolio', 'quarterly', 'discussion',
    'what are your moves', 'meme', 'monthly',
]

# 방향성 키워드 (상승/하락/매수/매도 신호)
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
    '롱', '숏', '매수', '매도',
    '상방', '하방', '저점', '고점',
    '조정', '반락', '폭락', '폭등',
]

# 자산/지수/매크로 키워드
ASSET_KW = [
    's&p', 'nasdaq', 'spx', 'spy', 'qqq',
    'vix', 'dow', 'russell', 'iwm',
    'cpi', 'fomc', 'fed rate', 'federal reserve',
    'yields', 'yield curve', 'treasury',
    'oil', 'crude', 'wti', 'brent',
    'inflation', 'interest rate',
    '나스닥', '금리', '유가', '원유', '연준', '국채',
    '코스피', '달러', '환율',
]

# 지정학·매크로 단독 통과 (100자 이상일 때만)
GEOPOLITICAL_KW = [
    'china', 'taiwan', 'russia', 'ukraine', 'us',
    'trade war', 'tariff', 'sanctions',
    'gdp', 'unemployment', 'earnings',
    '중국', '대만', '러시아', '우크라이나', '미국',
    '무역', '관세', '제재',
    '국내총생산', '실업', '실적',
]

# ═══ HTTP 헤더 ═══

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}

# ═══ 설정 로드 ═══

def load_seeds() -> dict:
    """alpha_hunter_seeds.json 로드"""
    if not os.path.exists(SEEDS_FILE):
        return {}
    try:
        with open(SEEDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def load_seed_list() -> list:
    """seed_list.json 로드 (개인 피드 목록)"""
    if not os.path.exists(SEED_LIST):
        return []
    try:
        with open(SEED_LIST, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get('feeds', [])
            return []
    except Exception:
        return []


# ═══ 중복 방지 ═══

def url_hash(url: str) -> str:
    """URL을 해시로 변환"""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def load_seen() -> dict:
    """seen 파일 로드"""
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_seen(seen: dict):
    """seen 파일 저장"""
    try:
        os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
        with open(SEEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(seen, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def mark_seen(seen: dict, url: str):
    """URL을 본 것으로 마크"""
    h = url_hash(url)
    seen[h] = datetime.now(timezone.utc).isoformat()
    save_seen(seen)


def is_seen(seen: dict, url: str) -> bool:
    """URL을 이미 봤는지 확인"""
    h = url_hash(url)
    return h in seen


__all__ = [
    'DIR', 'SEEDS_FILE', 'SEED_LIST', 'SEEN_FILE', 'SIGNALS_DIR', 'HTML_OUT',
    'FRESHNESS_HOURS', 'MIN_EXCERPT_CHARS', 'MAX_EXCERPT_MD',
    'NOISY_TITLE_KW', 'DIRECTION_KW', 'ASSET_KW', 'GEOPOLITICAL_KW',
    'HEADERS',
    'load_seeds', 'load_seed_list',
    'url_hash', 'load_seen', 'save_seen', 'mark_seen', 'is_seen',
]
