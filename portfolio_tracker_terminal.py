"""포트폴리오 트래커 — 터미널 출력 모듈"""

from portfolio_tracker_base import alert_line, fmt_krw, fmt_pct


def print_terminal(accounts_data: dict, usdkrw: float, timestamp: str) -> tuple:
    """계좌별 손익 + 합계 터미널 출력"""
    print(f"\n{'━'*105}")
    print(f"  Jason & 와이프 포트폴리오 손익   {timestamp}")
    print(f"  환율: ₩{usdkrw:,.2f}/USD")
    print(f"{'━'*105}")

    grand_cost = grand_curr = grand_daily = 0

    for acc, d in accounts_data.items():
        print(f"  ┌─ {acc} {'─'*75}")
        print(f"  │ {'종목':<16} {'수량':>8} {'평단가':>12} {'현재가':>12} "
              f"{'평가금액(₩)':>16} {'총손익(₩)':>14} {'1일손익(₩)':>12} {'수익률':>8}")
        print(f"  │ {'─'*105}")

        for r in d['rows']:
            if r['is_cash']:
                line = (f"  │ {r['name']:<16} {'현금':>8} {r['avg']:>12} {r['price']:>12} "
                        f"{fmt_krw(r['val_krw']):>16} "
                        f"{'-':>14} "
                        f"{'-':>12} "
                        f"{'-':>8}")
            else:
                line = (f"  │ {r['name']:<16} {r['qty']:>8} "
                        f"{r['avg']:>12} {r['price']:>12} "
                        f"{fmt_krw(r['val_krw']):>16} "
                        f"{fmt_krw(r['profit_krw']):>14} "
                        f"{fmt_krw(r['daily_profit_krw']):>12} "
                        f"{fmt_pct(r['pct']):>8}")
            print(alert_line(line))

        print(f"  │ {'─'*105}")
        has_profit_basis = d.get('profit_basis', d['cost']) > 0
        profit_s = fmt_krw(d['profit']) if has_profit_basis else '-'
        daily_s = fmt_krw(d['daily_profit']) if has_profit_basis else '-'
        pct_s = fmt_pct(d['pct']) if has_profit_basis else '-'
        summary = (f"  │ {'[계좌합계]':<16} {'':>8} {'':>12} {'':>12} "
                   f"{fmt_krw(d['curr']):>16} "
                   f"{profit_s:>14} "
                   f"{daily_s:>12} "
                   f"{pct_s:>8}")
        print(alert_line(summary))
        print(f"  └{'─'*106}\n")

        grand_cost += d['cost']
        grand_curr += d['curr']
        grand_daily += d['daily_profit']

    grand_profit = sum(d['profit'] for d in accounts_data.values())
    grand_basis = sum(d.get('profit_basis', d['cost']) for d in accounts_data.values())
    grand_pct = grand_profit / grand_basis * 100 if grand_basis > 0 else 0
    grand_usd = grand_curr / usdkrw

    print(f"  {'━'*105}")
    print(alert_line(f"    총 평가금액  : {fmt_krw(grand_curr)}  (${grand_usd:,.0f})"))
    print(alert_line(f"    총 손익      : {fmt_krw(grand_profit)}  ({grand_pct:+.2f}%)"))
    print(alert_line(f"    총 1일 손익  : {fmt_krw(grand_daily)} (주가+환율 변동 합산)"))
    print(f"  {'━'*105}")
    print(f"\n  ※ 데이터 출처: 구글드라이브 자산계산기.xlsx\n")

    return grand_cost, grand_curr, grand_profit, grand_pct, grand_usd, grand_daily


__all__ = ['print_terminal']
