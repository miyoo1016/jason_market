"""Alpha Hunter — 데이터 수집 모듈
RSS 피드 수집, HTTP 요청, Reddit/블로그 파싱"""

import requests
import subprocess
import random
import time
import xml.etree.ElementTree as ET
import re
from html import unescape

from jm_lib.colors import ALERT, CYAN, RESET
from alpha_hunter_base import (
    HEADERS, MIN_EXCERPT_CHARS,
)
from alpha_hunter_md import (
    is_fresh, is_bot_or_noise, check_reddit_pass,
    parse_reddit_atom, parse_generic_rss,
    urlhost, clean_html,
)


def rand_delay(lo=1.5, hi=3.0):
    """Random delay between requests"""
    time.sleep(random.uniform(lo, hi))


def fetch(url: str, timeout: int = 20) -> str | None:
    """requests 기반 HTTP 요청"""
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
             '-H', f'Accept-Language: {HEADERS.get("Accept-Language", "")}',
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


def collect_seed_list(feeds: list, stats: dict, max_n: int) -> list:
    """seed_list.json 개인 피드 수집"""
    posts = []
    if not feeds:
        return posts

    for feed_info in feeds:
        rss_url = feed_info.get('rss_url', '')
        name = feed_info.get('name', urlhost(rss_url))
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
            if not p.get('title') or ' ' not in (p['title'] + ' ' + p['excerpt']):
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
            if is_bot_or_noise(p['author'], p['title']):
                stats['filtered_bot'] += 1
                n_bot += 1
                continue
            if not is_fresh(p['pub_raw']):
                stats['filtered_stale'] += 1
                n_stale += 1
                continue
            if len(p['excerpt']) < MIN_EXCERPT_CHARS:
                stats['filtered_short'] += 1
                n_short += 1
                continue
            reason = check_reddit_pass(
                p['excerpt'],
                p['title'] + ' ' + p['excerpt']
            )
            if reason is None:
                stats['filtered_no_signal'] += 1
                n_nosig += 1
                continue
            p['pass_reason'] = reason
            accepted.append(p)
            if len(accepted) >= max_n:
                break

        posts.extend(accepted)
        detail = []
        if n_bot:
            detail.append(f'봇·공지 {n_bot}')
        if n_stale:
            detail.append(f'72h초과 {n_stale}')
        if n_short:
            detail.append(f'단문 {n_short}')
        if n_nosig:
            detail.append(f'자산+방향미충족 {n_nosig}')
        detail_str = ' | '.join(detail)
        geo_samples = [p['pass_reason'] for p in accepted
                       if p.get('pass_reason', '').startswith('GEO_MACRO')]
        geo_log = f' [{", ".join(geo_samples[:3])}]' if geo_samples else ''
        print(f"{CYAN}{len(accepted)}개 신규{geo_log}{RESET}"
              + (f" ({detail_str} 제거)" if detail_str else ""))
        rand_delay()

    return posts


def aggregate(seed_posts: list, reddit_posts: list) -> list:
    """시드 글 먼저, 레딧 글 뒤에. URL 중복 제거."""
    seen_urls = set()
    result = []
    for p in seed_posts + reddit_posts:
        h = url_hash(p['url'])
        if h not in seen_urls:
            seen_urls.add(h)
            result.append(p)
    return result


__all__ = [
    'fetch', 'fetch_curl',
    'collect_seed_list', 'collect_reddit', 'aggregate',
]
