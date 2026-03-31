#!/usr/bin/env python3
"""Jason Market 메뉴 런처
사용법: python3 menu.py  (또는 터미널에서 그냥 'jm')
"""

import os
import sys
import subprocess

DIR = os.path.dirname(os.path.abspath(__file__))

_W = '\033[96m[HTML🌐]\033[0m'   # HTML 출력 항목 표시 (밝은 파랑)

MENU = [
    # (번호, 표시명, 파일명, 인수, HTML출력여부)
    ('s',  'xlsx 동기화       — 구글드라이브 자산계산기 연동', 'xlsx_sync.py',                [], False),
    ('1',  '가격 조회          — 주요 자산 현재가',          'view_prices.py',              [], False),
    ('2',  '포트폴리오 손익    — 내 계좌 실시간 수익률',     'portfolio_tracker.py',        [], True),
    ('3',  '공포탐욕지수       — 시장 심리 0~100',           'fear_greed.py',               [], False),
    ('4',  '거시경제 대시보드  — 금리·달러·유가·환율',       'macro_dashboard.py',          [], False),
    ('5',  '뉴스 수집·정리     — Yahoo+Google RSS 감성분석',       'news_summary.py',        [], True),
    ('6',  '가격 알리미        — 목표가 도달 시 알림',       'price_alert.py',              [], False),
    ('7',  '기술적 분석        — RSI·MACD·볼린저·스토캐스틱·ATR',   'technical_analysis_with_ai.py', [], True),
    ('8',  '지지·저항선        — 주요 가격대 분석',          'support_resistance.py',       [], True),
    ('9',  '수익률 비교        — 자산별 성과 비교',          'returns_comparison.py',       [], True),
    ('10', '상관관계 매트릭스  — 자산 간 연관성',            'correlation_matrix.py',       [], True),
    ('11', '자동 전체 분석     — 위 항목 일괄 실행 [API 다수]', 'auto_analysis.py',          [], True),
    ('12', '멀티 에이전트 AI   — 6개 Claude 토론 후 판단 [API 6회]', 'multi_agent_analyst.py', [], True),
    ('13', '차트 대시보드     — 16종목 5분봉/일봉 브라우저', 'chart_viewer.py',             [], True),
    ('14', '옵션 모니터      — QQQ/GLD 1개월 배팅 현황',   'options_monitor.py',          [], True),
    ('15', '섹터 흐름        — S&P500 11개 섹터 자금흐름', 'sector_flow.py',              [], True),
    ('16', '포트폴리오 리스크 — VaR·Beta·변동성 분석',     'portfolio_risk.py',           [], True),
    ('17', '시장 스트레스    — VIX구조·금리역전·신용스프레드', 'market_stress.py',           [], True),
]

SEPARATOR = '─' * 58


def print_menu():
    print(f"\n{'━'*68}")
    print(f"  Jason Market  —  무엇을 볼까요?")
    print(f"  {_W} = 브라우저 HTML 창 표시 항목")
    print(f"{'━'*68}")
    for num, desc, _, _, is_html in MENU:
        tag = f'  {_W}' if is_html else ''
        if num == 's':
            print(f"  {'─'*66}")
            print(f"   s. {desc}")
            print(f"  {'─'*66}")
        else:
            print(f"  {num:>2}. {desc}{tag}")
    print(f"{'─'*68}")
    print(f"   0. 종료")
    print(f"{'━'*68}")


def run(script, extra_args=None):
    path = os.path.join(DIR, script)
    cmd  = [sys.executable, path] + (extra_args or [])
    subprocess.run(cmd)


def ask_question(prompt_text):
    q = input(f"  질문 입력 (예: BTC 지금 매수해야 해?): ").strip()
    if q:
        run('multi_agent_analyst.py', [q])
    else:
        print("  취소")


def main():
    while True:
        print_menu()
        choice = input("\n  번호 선택: ").strip()

        if choice == '0':
            print("  종료\n")
            break

        matched = next((item for item in MENU if item[0] == choice), None)

        if not matched:
            print("  ⚠ 없는 번호입니다")
            continue

        _, desc, script, args, _ = matched

        # 멀티 에이전트는 질문을 별도 입력받음
        if choice == '12':
            ask_question(desc)
        else:
            print(f"\n  ▶ {desc.split('—')[0].strip()} 실행 중...\n")
            run(script, args)

        input("\n  Enter 키를 누르면 메뉴로 돌아갑니다...")


if __name__ == '__main__':
    main()
