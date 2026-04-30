"""포트폴리오 트래커 — 손익 계산 모듈
계좌별 손익, 일일 손익, 환차 계산"""

from datetime import datetime

from portfolio_tracker_base import load_cash_tracker
from portfolio_tracker_prices import fetch_all_prices, get_price


def calc_data(holdings: list, usdkrw_tuple: tuple) -> tuple:
    """모든 계좌 손익 계산 → (accounts_data, updated_cash_tracker)"""
    usdkrw, prev_usdkrw = usdkrw_tuple
    valid = [h for h in holdings if h.get('ticker') and float(h.get('qty', 0)) > 0]
    price_cache = fetch_all_prices(valid, usdkrw)
    

    tracker = load_cash_tracker()       # 기존 저장값
    new_tracker = {}                     # 이번 실행 후 저장할 값
    today_str = datetime.now().strftime('%Y-%m-%d')
    cash_idx_map = {}                    # acc → 이 계좌에서 몇 번째 현금 행

    accounts = {}
    for h in valid:
        acc = h.get('account', '기타')
        accounts.setdefault(acc, []).append(h)

    accounts_data = {}
    for acc, items in accounts.items():
        rows = []
        acc_cost = acc_curr = acc_daily_profit = 0
        acc_list = tracker.get(acc, [])  # 기존 tracker의 이 계좌 데이터

        for h in items:
            qty = float(h['qty'])
            avg = float(h['avg_price'])
            cur = h.get('currency', 'KRW')

            # ── 현금 처리 ─────────────────────────────────────
            if h.get('is_cash') or h.get('ticker') == 'CASH':
                cash_krw = avg if cur == 'KRW' else avg * usdkrw

                # 이 계좌의 몇 번째 현금 행인지 인덱스 확인
                idx = cash_idx_map.get(acc, 0)
                cash_idx_map[acc] = idx + 1

                # tracker 데이터 로드
                if idx < len(acc_list):
                    entry = acc_list[idx]
                else:
                    # 처음 등장 → 기준값 = 현재 잔액 (손익 0으로 시작)
                    entry = {'cost_basis': cash_krw,
                             'prev_balance': cash_krw,
                             'prev_date': today_str}

                cost_basis = entry.get('cost_basis', cash_krw)
                prev_date = entry.get('prev_date', today_str)
                prev_balance = entry.get('prev_balance', cash_krw)

                # 전일과 날짜가 같으면 same-day → daily 집계 유지
                if prev_date == today_str:
                    daily_profit_krw = cash_krw - prev_balance
                else:
                    daily_profit_krw = cash_krw - prev_balance

                profit_krw = cash_krw - cost_basis
                pct = profit_krw / cost_basis * 100 if cost_basis > 0 else 0

                # new_tracker에 기록 (cost_basis 보존, prev_balance 갱신)
                new_entry = {
                    'cost_basis': cost_basis,
                    'prev_balance': cash_krw,
                    'prev_date': today_str,
                }
                if acc not in new_tracker:
                    new_tracker[acc] = []
                new_tracker[acc].append(new_entry)

                acc_cost += cost_basis
                acc_curr += cash_krw
                acc_daily_profit += daily_profit_krw

                rows.append({
                    'name': h['name'], 'qty': '현금', 'is_cash': True,
                    'avg': f'₩{cost_basis:,.0f}', 'price': f'₩{cash_krw:,.0f}', 'cur': cur,
                    'val_krw': cash_krw, 'profit_krw': profit_krw,
                    'daily_profit_krw': daily_profit_krw, 'pct': pct,
                    'fx_pnl': 0, 'price_pnl': profit_krw, 'base_fx': 0,
                    'is_precision': False,
                })
                continue

            # ── 종목 가격 조회 ────────────────────────────────
            price, prev_close = get_price(h, price_cache, usdkrw)
            if price is None:
                continue

            base_fx = h.get('base_usdkrw', usdkrw)
            is_usd = (cur == 'USD')

            p_cost = h.get('precision_cost_krw')

            if is_usd:
                # 구글시트 기준 손익 계산
                # 손익(₩) = qty × (현재가 - 평단가) × 현재환율
                # cost_krw = qty × 평단가 × 현재환율 (시트와 동일)
                cost_krw = qty * avg * usdkrw
                current_krw = qty * price * usdkrw
                # 1일 손익: (오늘가 - 어제가) × 현재환율 × 수량 (주가 변동분)
                if prev_close:
                    daily_profit_krw = (price - prev_close) * usdkrw * qty
                else:
                    daily_profit_krw = 0
                avg_s = f"${avg:,.2f}"
                pri_s = f"${price:,.2f}"

                # 환차 정보 (보조 표시용)
                purchase_fx = p_cost if (p_cost is not None and p_cost < 10000) else base_fx
                fx_pnl = (usdkrw - purchase_fx) * avg * qty
                price_pnl = qty * (price - avg) * usdkrw  # = profit_krw
            else:
                cost_krw = p_cost if p_cost is not None else (qty * avg)
                current_krw = qty * price
                daily_profit_krw = (price - prev_close) * qty if prev_close else 0
                avg_s = f"₩{avg:,.0f}"
                pri_s = f"₩{price:,.0f}"
                fx_pnl = 0
                price_pnl = current_krw - cost_krw

            profit_krw = current_krw - cost_krw
            pct = profit_krw / cost_krw * 100 if cost_krw > 0 else 0
            acc_cost += cost_krw
            acc_curr += current_krw
            acc_daily_profit += daily_profit_krw

            rows.append({
                'name': h['name'], 'qty': f"{qty:,.0f}", 'is_cash': False,
                'avg': avg_s, 'price': pri_s, 'cur': cur,
                'val_krw': current_krw, 'profit_krw': profit_krw,
                'daily_profit_krw': daily_profit_krw, 'pct': pct,
                'fx_pnl': fx_pnl, 'price_pnl': price_pnl, 'base_fx': base_fx,
                'is_precision': (p_cost is not None)
            })

        acc_profit = acc_curr - acc_cost
        acc_pct = acc_profit / acc_cost * 100 if acc_cost > 0 else 0
        accounts_data[acc] = {
            'rows': rows, 'cost': acc_cost, 'curr': acc_curr,
            'profit': acc_profit, 'daily_profit': acc_daily_profit, 'pct': acc_pct,
        }

    return accounts_data, new_tracker


__all__ = ['calc_data']
