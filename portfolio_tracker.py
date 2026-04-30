#!/usr/bin/env python3
"""포트폴리오 손익 추적기 - Jason Market | 메뉴 2번
구글드라이브 자산계산기.xlsx → 실시간 손익 계산 + HTML 대시보드"""

import os
import json
import webbrowser
import tempfile
from datetime import datetime

from xlsx_sync import update_xlsx_live_fx, load_portfolio

from portfolio_tracker_base import save_cash_tracker
from portfolio_tracker_prices import get_usdkrw
from portfolio_tracker_calc import calc_data
from portfolio_tracker_terminal import print_terminal
from portfolio_tracker_html import generate_html


# (기존 _load_holdings는 load_portfolio로 대체됨)


def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*90}")
    print(f"  Jason & 와이프 포트폴리오 손익   {timestamp}")
    print(f"{'━'*90}")
    print("  xlsx 동기화 및 가격 조회 중...\n")

    # 엑셀/구글시트 최신 데이터 동기화 (Plan A: 완전 자동화)
    holdings = load_portfolio()
    if not holdings:
        print("  동기화 실패 혹은 보유 종목 없음. 엑셀 파일을 확인하세요.")
        return

    usdkrw_tuple = get_usdkrw()
    usdkrw, _ = usdkrw_tuple
    print(f"  현재 환율: ₩{usdkrw:,.2f}/USD\n")

    # 엑셀 O14 셀 실시간 업데이트
    update_xlsx_live_fx(usdkrw)

    accounts_data, new_cash_tracker = calc_data(holdings, usdkrw_tuple)
    if not accounts_data:
        print("  유효한 보유 종목 없음.")
        return

    # 현금 추적값 저장 (다음 실행 시 일일손익 계산용)
    save_cash_tracker(new_cash_tracker)

    print_terminal(accounts_data, usdkrw, timestamp)

    html = generate_html(accounts_data, usdkrw_tuple, timestamp)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='portfolio_tracker_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")


if __name__ == '__main__':
    main()
