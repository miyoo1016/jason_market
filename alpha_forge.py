#!/usr/bin/env python3
"""Alpha Hunter — Market Intelligence & Signal Collector
Jason Market의 차세대 메인 분석 엔진.
거시 국면 자동 감지 + Alpha Hunter 집계 + AI 브리핑 준비
"""

import sys
import os
import webbrowser
from datetime import datetime

# 기존 모듈 임포트
from alpha_hunter_base import load_seeds, load_seed_list, FRESHNESS_HOURS, HTML_OUT
from alpha_hunter_collector import collect_seed_list, collect_reddit, aggregate
from alpha_hunter_macro import build_macro_dashboard
from alpha_hunter_md import generate_markdown, save_markdown
from alpha_hunter_html import generate_html
from jm_lib.colors import CYAN, AMBER, RESET, GREEN, RED

# 신규 국면 감지 모듈
from alpha_forge_regime import print_regime_header

def main():
    # 1. 국면 감지 헤더 출력
    regime_key, status = print_regime_header()
    
    if regime_key == 'weak':
        print(f"\n  {RED}🚫 오늘 Alpha Hunter 진입 신호 없음{RESET}")
        print(f"     이유: 코스피 약세({status['kospi_chg']:+.2f}%) + VIX({status['vix'] or 0:.2f}) 불안")
        print(f"     → 오늘은 관망하며 관심 종목의 지지력을 확인하세요.")
        # 약세장일 때는 관심 목록 수집은 하되, 상단에 경고 표시 예정
    
    print(f"\n  {CYAN}▶ Alpha Hunter 엔진 가동 중...{RESET}")

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

    print(f"  {CYAN}[1/4] 시드 피드 수집 중...{RESET}")
    seed_posts   = collect_seed_list(feeds, stats, max_n)

    print(f"  {CYAN}[2/4] Reddit 수집 중...{RESET}")
    reddit_posts = collect_reddit(seeds, stats)

    print(f"  {CYAN}[3/4] Macro Dashboard 수집 중...{RESET}")
    macro_md, macro_data = build_macro_dashboard()

    posts = aggregate(seed_posts, reddit_posts)
    stats['final'] = len(posts)

    ts      = datetime.now().strftime('%Y-%m-%d %H:%M')
    md_text = generate_markdown(posts, ts, stats, macro_md)
    md_path = save_markdown(md_text)
    
    # HTML 생성 및 저장
    html = generate_html(posts, md_text, ts, seeds, stats, macro_data)
    
    # 국면 정보를 HTML에 삽입하거나 표시하는 로직은 나중에 확장 가능
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    from alpha_forge_regime import get_tactical_advice
    advice = get_tactical_advice(regime_key, stats['final'])

    print(f"\n{RESET}────────────────────────────────────────────────────────────")
    if stats['final'] == 0:
        print(f"  {AMBER}💡 {advice}{RESET}")
    else:
        print(f"  ✅ 최종 저장: {stats['final']}건")
        print(f"  📢 {advice}")
    
    print(f"  🔍 분석 리포트: {HTML_OUT}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    webbrowser.open(f'file://{HTML_OUT}')

    webbrowser.open(f'file://{HTML_OUT}')

if __name__ == '__main__':
    main()
