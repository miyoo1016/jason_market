#!/usr/bin/env python3
"""옵션 모니터 - Jason Market | 메뉴 11번
QQQ / GLD 전체 만기 옵션 배팅 현황
데이터 소스:
  · 날짜/OI/Volume/IV : CBOE Delayed Quotes API (= optioncharts.io 동일 소스)
  · 기대변동폭 : ATM 스트래들 미드가격 (= barchart.com/expected-move 동일 방식)
만기별 상세표 · 스트라이크 OI 차트 · Max Pain · P/C 비율 · 상한/하한 범위"""

import os
import webbrowser
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

from jm_lib.options import calc_vanna_charm
from options_monitor_base import ASSETS, pc_signal
from options_monitor_data import process
from options_monitor_render import render_iv_rank, render_0dte_block
from options_monitor_html import generate_html


def _print_index_detail(sym: str, label: str, r: dict, spy_price: float):
    """SPX/NDX 상세 터미널 출력 — GEX 레짐 + 0DTE"""
    gex = r.get('gex', {})
    curr = r['curr']
    gflip = gex.get('gamma_flip')
    cwall = gex.get('call_wall')
    pwall = gex.get('put_wall')
    ngb = gex.get('net_gex_b', 0)
    sig_oi, _ = pc_signal(r['pc_oi'])
    sig_vol, _ = pc_signal(r['pc_vol'])

    if gflip:
        if curr > gflip:
            regime_text = "딜러 롱감마 ✅ — 딜러가 하락시 매수·상승시 매도 → 시장 안정화"
            gflip_text = "▼ 현재가 아래 ✅ — 딜러 롱감마 구간, 안정화 작동 중"
            market_regime = "Pos Pinning (딜러 롱감마, 안정화)"
        else:
            regime_text = "딜러 숏감마 ⚠ — 딜러가 하락을 따라 팜 → 변동성 증폭 위험"
            gflip_text = "▲ 현재가 위 ⚠ — 딜러 숏감마 구간, 변동 증폭 위험"
            market_regime = "숏감마 구간 (딜러 변동성 증폭 가능)"
    else:
        regime_text = gflip_text = market_regime = "N/A"

    cwall_text = "N/A"
    if cwall:
        cwall_pct = (cwall / curr - 1) * 100
        if curr > cwall:
            cwall_text = f"돌파 완료 구간 / 하방 지지 전환 ({cwall_pct:+.1f}%)"
        else:
            cwall_text = f"콜 감마 집중 저항 ({cwall_pct:+.1f}%)"

    pwall_text = "N/A"
    if pwall:
        pwall_pct = (pwall / curr - 1) * 100
        pwall_text = f"풋 감마 집중 지지 ({pwall_pct:+.1f}%)"

    print("──────────────────────────────────")
    print(f"{sym}  |  {label}")
    print(f"현재가: {curr:,.2f}")
    print(f"레짐: {market_regime}")

    # SPX-SPY 페어 비율 경고
    if sym == 'SPX' and spy_price > 0:
        ratio = curr / spy_price
        warning = " ⚠ 괴리율 경고" if ratio < 7.8 or ratio > 8.2 else ""
        print(f"📎 페어 ETF: SPY | SPX ÷ SPY 비율: {ratio:.2f}x{warning}")

    print("──────────────────────────────────")
    print("⚡ NET GEX (1개월이내)")
    print(f"  {'+' if ngb >= 0 else ''}{ngb:.3f}B")
    print(f"  {regime_text}")
    print("\n🔄 GAMMA FLIP")
    print(f"  {gflip:,.2f}")
    print(f"  {gflip_text}")
    print("\n🟢 CALL WALL")
    print(f"  {cwall:,.2f}")
    print(f"  {cwall_text}")
    print("\n🔴 PUT WALL")
    print(f"  {pwall:,.2f}")
    print(f"  {pwall_text}")
    print(f"\nP/C OI  : {r['pc_oi']:.2f} → {sig_oi}")
    print(f"P/C VOL : {r['pc_vol']:.2f} → {sig_vol}")
    print("──────────────────────────────────")

    # MODULE 2 & 3 터미널 출력
    vc = calc_vanna_charm(r)
    if 'err' in vc:
        print(f"  ⚠ Greeks 오류: {vc['err']}")
    else:
        print(f"⚡ VANNA EXPOSURE (추정): ${vc['vanna']:.3f}B")
        vanna_msg = '매수 압력 → 상승 가속 가능 ✅' if vc['vanna'] >= 0 else '매도 압력 → 상승 제한 가능 ⚠'
        print(f"    · [{'양수' if vc['vanna']>=0 else '음수'}] VIX 하락 시 딜러 {vanna_msg}")
        print(f"⏱ CHARM EXPOSURE (추정): ${vc['charm']:.3f}B")
        charm_msg = '매수 드리프트 → 서서히 상승 인력 ✅' if vc['charm'] >= 0 else '매도 드리프트 → 서서히 하방 인력 ⚠'
        print(f"    · [{'양수' if vc['charm']>=0 else '음수'}] 시간 경과 시 딜러 {charm_msg}")

    iv_data = render_iv_rank(r)
    if iv_data['status'] != 'OK':
        print(f"\n📊 IV Rank: {iv_data['status']}")
    else:
        new_high_lbl = " ⚠ 1년 신고IV" if iv_data.get('new_high') else ""
        print(f"\n📊 IV RANK: {iv_data['rank']}%{new_high_lbl} | IV PERCENTILE: {iv_data['pct']}%")
        if iv_data['rank'] <= 30:
            status_icon = "🟢"
            status_txt = "IV 저렴 → 옵션 매수 유리"
        elif iv_data['rank'] >= 70:
            status_icon = "🔴"
            status_txt = "IV 고가 → 옵션 매도 유리 / 이벤트 내포"
        else:
            status_icon = "🟡"
            status_txt = "IV 보통 → 방향성 배팅 중립"
        print(f"    · [{iv_data['rank']}%] {status_txt} {status_icon}")

    # 0DTE 출력
    zdte = render_0dte_block(r)
    if not zdte:
        print("\n⚡ 0DTE: 오늘 만기 없음 (주말/공휴일)")
    else:
        print("\n┌─────────────────────────────────────────┐")
        print("│  🔥 0DTE 당일 결전 데이터               │")
        print(f"│  만기: {zdte['exp']} | IV: {zdte['iv']:.1f}%           │")
        print(f"│  P/C Vol: {zdte['pc_vol']:.2f} | P/C OI: {zdte['pc_oi']:.2f}          │")
        print(f"│  기대변동: ±{zdte['em_pct']:.1f}% / ±${zdte['em_val']:,.2f}               │")
        print(f"│  기대범위: ▲${zdte['upper']:,.1f} ~ ▼${zdte['lower']:,.1f}           │")
        print(f"│  Max Pain: ${zdte['mp']:,.1f} ({zdte['mp_diff']:+.1f}%)     │")
        print(f"│  0DTE GEX 방향: [딜러 {zdte['gex_dir']}] │")
        print(f"│  당일 Intraday 편향: [{zdte['bias']}] │")
        print("└─────────────────────────────────────────┘")
    print("──────────────────────────────────")


def _print_summary(sym: str, r: dict):
    """일반 자산 요약 출력"""
    sig, _ = pc_signal(r['pc_oi'])
    gex = r.get('gex', {})
    gflip = gex.get('gamma_flip')
    regime = "N/A"
    if gflip:
        if r['curr'] > gflip:
            regime = "딜러 롱감마 ✅ (시장 안정)"
        else:
            regime = "딜러 숏감마 ⚠ (변동성 증폭)"

    print(f"  {sym}  현재가 ${r['curr']:,.2f}  |  P/C OI {r['pc_oi']:.2f}  ({sig})")
    print(f"       레짐: {regime}")
    print(f"       Max Pain ${r['max_pain']:,.2f}" if r['max_pain'] else "       Max Pain N/A")
    print(f"       만기 {r['exp_count']}개\n")


def main():
    print(f"\n{'━'*55}")
    print(f"  Jason 옵션 모니터  (QQQ / SPY / GOOGL)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*55}")
    print("  CBOE delayed quotes 수집 중 (약 10-20초)...\n")

    # SPX-SPY 페어 비율을 위한 SPY 선행 fetch
    spy_data = process('SPY', 'S&P 500 ETF')
    spy_price = spy_data['curr'] if spy_data else 0

    results = []
    for sym, label in ASSETS:
        r = process(sym, label)
        results.append(r)
        if not r:
            print(f"  {sym}  데이터 수집 실패\n")
            continue

        if sym in ['SPX', 'NDX']:
            _print_index_detail(sym, label, r, spy_price)
        else:
            _print_summary(sym, r)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_content = generate_html(results, timestamp)

    DIR = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(DIR, 'options_dashboard.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"  브라우저에서 오픈 중...")
    webbrowser.open(f'file://{html_path}')
    print(f"  완료!\n")
    print("  보는 법:")
    print("  - P/C 비율 > 1.0 : 풋 많음 (헤지/약세)  < 0.7 : 콜 많음 (강세)")
    print("  - Max Pain : 옵션 매도자 입장에서 가장 유리한 만기 가격")
    print("  - 기대변동폭 : ATM 스트래들 미드가 (= barchart expected-move)")
    print("  - GEX 양수 : 딜러 롱감마 → 가격 안정 / GEX 음수 : 딜러 숏감마 → 변동성 증폭")
    print("  - Gamma Flip : 이 가격 아래로 내려가면 딜러가 하락을 오히려 증폭시킴")
    print("  - Call Wall : 강한 저항 / Put Wall : 강한 지지\n")


if __name__ == '__main__':
    main()
