#!/usr/bin/env python3
"""Alpha Hunter — 증시 고수 글 자동 수집기 | Jason Market 15번
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

import webbrowser
from datetime import datetime

from jm_lib.colors import CYAN, AMBER, RESET

from alpha_hunter_base import load_seeds, load_seed_list, FRESHNESS_HOURS
from alpha_hunter_collector import collect_seed_list, collect_reddit, aggregate
from alpha_hunter_macro import build_macro_dashboard
from alpha_hunter_md import generate_markdown, save_markdown
from alpha_hunter_html import generate_html


def main():
    print(f"\n{'━'*62}")
    print(f"  🎯 Alpha Hunter V1.3 — 증시 고수 글 수집 + Macro Dashboard")
    print(f"  필터: {FRESHNESS_HOURS}h이내 | 본문150자+ | 봇·공지 | 자산AND방향 키워드")
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

    from alpha_hunter_base import HTML_OUT
    html = generate_html(posts, md_text, ts, seeds, stats, macro_data)
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  {CYAN}● HTML 생성:{RESET} {HTML_OUT}")

    print(f"\n{'─'*62}")
    print(f"  ✅ 최종 저장: {stats['final']}건")
    print(f"     시드 피드:  {sum(1 for p in posts if p['source']=='seed')}건")
    print(f"     Reddit:     {sum(1 for p in posts if p['source']=='reddit')}건")
    print(f"  🚫 필터 제거: 봇·공지 {stats['filtered_bot']}건 | "
          f"{FRESHNESS_HOURS}h초과 {stats['filtered_stale']}건 | "
          f"단문 {stats['filtered_short']}건 | "
          f"자산+방향미충족 {stats['filtered_no_signal']}건")
    print(f"\n  💡 AI 분석: HTML에서 '전체 복사' → AI에 붙여넣기")
    print(f"{'━'*62}\n")

    webbrowser.open(f'file://{HTML_OUT}')


if __name__ == '__main__':
    main()
