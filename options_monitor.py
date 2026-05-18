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


def _fetch_yf_spot(ticker: str) -> tuple[float | None, str]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period='5d')
        if not hist.empty:
            v = float(hist['Close'].dropna().iloc[-1])
            if v > 0:
                return v, f'yfinance {ticker}'
        fi = getattr(t, 'fast_info', {}) or {}
        v = float(fi.get('last_price') or fi.get('lastPrice') or 0)
        return (v, f'yfinance {ticker}') if v > 0 else (None, f'yfinance {ticker} unavailable')
    except Exception as e:
        return None, f'yfinance {ticker} error: {str(e)[:60]}'


def _build_ndx_overlay(ndx_result: dict | None, qqq_spot: float) -> dict:
    """Yahoo ^NDX spot/chain overlay. QQQ primary 계산은 건드리지 않는다."""
    spot, spot_src = _fetch_yf_spot('^NDX')
    if not spot and ndx_result:
        spot = float(ndx_result.get('curr') or 0) or None
        spot_src = 'existing NDX current fallback'
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    confidence = 20 if spot else 0
    reasons = []
    exp_count = call_rows = put_rows = 0
    chain_status = 'LOW/FALLBACK'
    derived_metrics = None

    try:
        import yfinance as yf
        import pandas as pd
        t = yf.Ticker('^NDX')
        expirations = list(getattr(t, 'options', []) or [])
        exp_count = len(expirations)
        if expirations:
            confidence += 10
        else:
            reasons.append('no expirations')

        calls_all = []
        puts_all = []
        for exp in expirations[:4]:
            oc = t.option_chain(exp)
            if getattr(oc, 'calls', None) is not None:
                calls_df = oc.calls.copy()
                calls_df['expiration'] = exp
                calls_all.append(calls_df)
            if getattr(oc, 'puts', None) is not None:
                puts_df = oc.puts.copy()
                puts_df['expiration'] = exp
                puts_all.append(puts_df)

        if calls_all and puts_all:
            calls = pd.concat(calls_all, ignore_index=True)
            puts = pd.concat(puts_all, ignore_index=True)
            call_rows, put_rows = len(calls), len(puts)
            if call_rows and put_rows:
                confidence += 10
            else:
                reasons.append('missing call/put rows')

            if spot:
                strikes = set(calls.get('strike', [])) | set(puts.get('strike', []))
                grid = [s for s in strikes if spot * 0.95 <= float(s) <= spot * 1.05]
                if grid:
                    confidence += 15
                else:
                    reasons.append('no ±5% strike grid')

            oi_vol = 0
            for df in (calls, puts):
                if 'openInterest' in df:
                    oi_vol += float(df['openInterest'].fillna(0).sum())
                if 'volume' in df:
                    oi_vol += float(df['volume'].fillna(0).sum())
            if oi_vol > 0:
                confidence += 15
            else:
                reasons.append('OI/volume all zero')

            sane = True
            for df in (calls, puts):
                if {'bid', 'ask'}.issubset(df.columns):
                    q = df[['bid', 'ask']].fillna(0)
                    q = q[(q['bid'] > 0) | (q['ask'] > 0)]
                    if len(q) and ((q['bid'] < 0).any() or (q['ask'] < 0).any() or (q['ask'] < q['bid']).any()):
                        sane = False
            if sane:
                confidence += 15
            else:
                reasons.append('bid/ask sanity failed')
        else:
            reasons.append('option chain unavailable')

        if spot and qqq_spot:
            ratio = spot / qqq_spot
            if 35 <= ratio <= 130:
                confidence += 10
            else:
                reasons.append(f'NDX/QQQ ratio abnormal {ratio:.1f}x')

        if spot and calls_all and puts_all:
            derived_metrics = _derive_ndx_metrics_from_yf_chain(calls, puts, expirations[:4], spot)
    except Exception as e:
        reasons.append(f'chain fetch failed: {str(e)[:60]}')

    confidence = max(0, min(100, int(confidence)))
    if confidence >= 75 and not derived_metrics:
        confidence = 74
        reasons.append('derived metrics unavailable')
    if confidence >= 75 and derived_metrics:
        chain_status = 'LIVE_DELAYED'
        derived_enabled = True
        derived_reason = 'NDX option metrics derived from validated Yahoo delayed chain'
    elif confidence >= 60:
        chain_status = 'REFERENCE_ONLY'
        derived_enabled = False
        derived_reason = 'NDX reference only. QQQ primary remains active.'
    else:
        chain_status = 'LOW/FALLBACK'
        derived_enabled = False
        derived_reason = 'NDX spot only. Do not use NDX-derived GEX/Wall/Max Pain. Use QQQ proxy.'

    equiv_levels = []
    if spot and qqq_spot:
        for lv in (29000, 29087):
            equiv_levels.append({'ndx': lv, 'qqq': qqq_spot * lv / spot})

    return {
        'ndx_spot': {'value': spot, 'source': spot_src, 'timestamp': ts},
        'ndx_option_chain': {
            'status': chain_status, 'confidence': confidence,
            'expirations': exp_count, 'call_rows': call_rows, 'put_rows': put_rows,
            'timestamp': ts, 'reasons': reasons,
        },
        'ndx_derived_metrics': {'enabled': derived_enabled, 'reason': derived_reason},
        'derived_metrics': derived_metrics,
        'qqq_equiv': equiv_levels,
    }


def _derive_ndx_metrics_from_yf_chain(calls, puts, expirations: list[str], spot: float) -> dict | None:
    """검증된 Yahoo NDX 체인에서 최소 Wall/Max Pain/GEX 참고값을 만든다."""
    try:
        import pandas as pd
        today = datetime.now().date()
        for df in (calls, puts):
            for col in ('strike', 'openInterest', 'volume', 'bid', 'ask', 'impliedVolatility'):
                if col in df:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        calls = calls[calls['strike'].between(spot * 0.85, spot * 1.15)].copy()
        puts = puts[puts['strike'].between(spot * 0.85, spot * 1.15)].copy()
        if calls.empty or puts.empty:
            return None

        call_wall_col = 'openInterest' if calls['openInterest'].sum() > 0 else 'volume'
        put_wall_col = 'openInterest' if puts['openInterest'].sum() > 0 else 'volume'
        call_wall = float(calls.loc[calls[call_wall_col].idxmax(), 'strike']) if calls[call_wall_col].sum() > 0 else None
        put_wall = float(puts.loc[puts[put_wall_col].idxmax(), 'strike']) if puts[put_wall_col].sum() > 0 else None

        strikes = sorted(set(calls['strike'].round(2)) | set(puts['strike'].round(2)))
        pain_strikes = [s for s in strikes if spot * 0.9 <= s <= spot * 1.1]
        max_pain = None
        if pain_strikes:
            c_oi = calls.groupby('strike')['openInterest'].sum()
            p_oi = puts.groupby('strike')['openInterest'].sum()
            best = None
            for settlement in pain_strikes:
                call_pain = sum(max(settlement - k, 0) * oi for k, oi in c_oi.items())
                put_pain = sum(max(k - settlement, 0) * oi for k, oi in p_oi.items())
                total = call_pain + put_pain
                if best is None or total < best[1]:
                    best = (settlement, total)
            max_pain = float(best[0]) if best else None

        def _days(exp: str) -> int:
            try:
                return max((datetime.strptime(exp, '%Y-%m-%d').date() - today).days, 0)
            except Exception:
                return 0

        exp_rows = []
        for exp in expirations:
            c = calls[calls['expiration'] == exp]
            p = puts[puts['expiration'] == exp]
            if c.empty or p.empty:
                continue
            c_oi_sum = float(c['openInterest'].sum())
            p_oi_sum = float(p['openInterest'].sum())
            c_vol_sum = float(c['volume'].sum())
            p_vol_sum = float(p['volume'].sum())
            atm = float(min(set(c['strike']) | set(p['strike']), key=lambda x: abs(float(x) - spot)))
            c_atm = c.iloc[(c['strike'] - atm).abs().argsort()[:1]]
            p_atm = p.iloc[(p['strike'] - atm).abs().argsort()[:1]]
            c_mid = float(((c_atm['bid'].iloc[0] or 0) + (c_atm['ask'].iloc[0] or 0)) / 2) if not c_atm.empty else 0
            p_mid = float(((p_atm['bid'].iloc[0] or 0) + (p_atm['ask'].iloc[0] or 0)) / 2) if not p_atm.empty else 0
            em = c_mid + p_mid
            row_mp = max_pain or 0
            exp_rows.append({
                'exp': exp,
                'days': _days(exp),
                'c_vol': int(c_vol_sum),
                'p_vol': int(p_vol_sum),
                'pc_vol': round(p_vol_sum / c_vol_sum, 2) if c_vol_sum > 0 else 0,
                'c_oi': int(c_oi_sum),
                'p_oi': int(p_oi_sum),
                'pc_oi': round(p_oi_sum / c_oi_sum, 2) if c_oi_sum > 0 else 0,
                'iv': round(float(pd.concat([c['impliedVolatility'], p['impliedVolatility']]).mean() * 100), 1),
                'atm_strike': atm,
                'straddle_em': round(em, 2),
                'straddle_em_pct': round(em / spot * 100, 2) if spot else 0,
                'upper_price': round(spot + em, 2),
                'lower_price': round(spot - em, 2),
                'max_pain': row_mp,
                'mp_diff': round((row_mp / spot - 1) * 100, 2) if row_mp else 0,
                'ok': True,
            })

        near_calls = calls[calls['strike'].between(spot * 0.95, spot * 1.05)]
        near_puts = puts[puts['strike'].between(spot * 0.95, spot * 1.05)]
        grouped_c = near_calls.groupby('strike')[['openInterest', 'volume']].sum()
        grouped_p = near_puts.groupby('strike')[['openInterest', 'volume']].sum()
        chart_strikes = sorted(set(grouped_c.index) | set(grouped_p.index))
        if len(chart_strikes) > 60:
            step = max(1, len(chart_strikes) // 60)
            chart_strikes = chart_strikes[::step]

        call_oi = [int(grouped_c['openInterest'].get(s, 0)) for s in chart_strikes]
        put_oi = [int(grouped_p['openInterest'].get(s, 0)) for s in chart_strikes]
        call_vol = [int(grouped_c['volume'].get(s, 0)) for s in chart_strikes]
        put_vol = [int(grouped_p['volume'].get(s, 0)) for s in chart_strikes]
        net_gex = [round((co - po) * spot * 0.000001, 3) for co, po in zip(call_oi, put_oi)]
        net_gex_b = sum(net_gex) / 1000
        gamma_flip = min(chart_strikes, key=lambda s: abs(float(s) - spot)) if chart_strikes else None

        return {
            'exp_rows': exp_rows,
            'exp_count': len(expirations),
            'tc_oi': int(calls['openInterest'].sum()),
            'tp_oi': int(puts['openInterest'].sum()),
            'tc_vol': int(calls['volume'].sum()),
            'tp_vol': int(puts['volume'].sum()),
            'pc_oi': round(float(puts['openInterest'].sum() / calls['openInterest'].sum()), 2) if calls['openInterest'].sum() > 0 else 0,
            'pc_vol': round(float(puts['volume'].sum() / calls['volume'].sum()), 2) if calls['volume'].sum() > 0 else 0,
            'max_pain': max_pain,
            'gex': {
                'net_gex_b': round(net_gex_b, 3),
                'call_wall': call_wall,
                'put_wall': put_wall,
                'gamma_flip': gamma_flip,
                'strikes': [float(s) for s in chart_strikes],
                'net_gex': net_gex,
                'call_gex': [round(co * spot * 0.000001, 3) for co in call_oi],
                'put_gex': [round(po * spot * 0.000001, 3) for po in put_oi],
            },
            'chart': {
                'strikes': [float(s) for s in chart_strikes],
                'call_oi': call_oi,
                'put_oi': put_oi,
                'call_vol': call_vol,
                'put_vol': put_vol,
                'call_vc': [0 for _ in chart_strikes],
                'put_vc': [0 for _ in chart_strikes],
            },
            'top_calls': [{'strike': float(x['strike']), 'oi': int(x['openInterest'])}
                          for _, x in calls.nlargest(2, 'openInterest').iterrows()],
            'top_puts': [{'strike': float(x['strike']), 'oi': int(x['openInterest'])}
                         for _, x in puts.nlargest(2, 'openInterest').iterrows()],
        }
    except Exception:
        return None


def _print_index_detail(sym: str, label: str, r: dict, spy_price: float):
    """SPX/NDX 상세 터미널 출력 — GEX 레짐 + 0DTE"""
    if sym == 'NDX' and r.get('_ndx_overlay'):
        ov = r['_ndx_overlay']
        spot = ov.get('ndx_spot', {})
        chain = ov.get('ndx_option_chain', {})
        derived = ov.get('ndx_derived_metrics', {})
        print("──────────────────────────────────")
        print(f"NDX  |  {label} overlay")
        if spot.get('value'):
            print(f"NDX spot: {spot['value']:,.2f}  ({spot.get('source')})")
        else:
            print("NDX spot: N/A")
        print(f"NDX Chain: {chain.get('status')} / confidence {chain.get('confidence', 0)}")
        for eq in ov.get('qqq_equiv', []):
            print(f"  NDX {eq['ndx']:,.0f} ≈ QQQ {eq['qqq']:,.1f}")
        if not derived.get('enabled'):
            if chain.get('status') == 'LOW/FALLBACK':
                print("NDX Chain: LOW/FALLBACK - NDX spot only. Do not use NDX-derived GEX/Wall/Max Pain. Use QQQ proxy.")
            else:
                print("NDX Chain: REFERENCE_ONLY - NDX reference only. QQQ primary remains active.")
            print("──────────────────────────────────")
            return

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
            regime_text = "딜러 롱감마 ✅ — 딜러 헤지가 하락 완충·상승 억제 → 시장 안정화"
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
    print(f"  {gflip:,.2f}" if gflip else "  N/A")
    print(f"  {gflip_text}")
    print("\n🟢 CALL WALL")
    print(f"  {cwall:,.2f}" if cwall else "  N/A")
    print(f"  {cwall_text}")
    print("\n🔴 PUT WALL")
    print(f"  {pwall:,.2f}" if pwall else "  N/A")
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
        vanna_msg = '상방 수급 → 상승 가속 가능 ✅' if vc['vanna'] >= 0 else '상승 제한 수급 가능 ⚠'
        print(f"    · [{'양수' if vc['vanna']>=0 else '음수'}] VIX 하락 시 딜러 {vanna_msg}")
        print(f"⏱ CHARM EXPOSURE (추정): ${vc['charm']:.3f}B")
        charm_msg = '상방 드리프트 → 서서히 상승 인력 ✅' if vc['charm'] >= 0 else '하방 드리프트 → 서서히 하방 인력 ⚠'
        print(f"    · [{'양수' if vc['charm']>=0 else '음수'}] 시간 경과 시 딜러 {charm_msg}")

    iv_data = render_iv_rank(r)
    if iv_data['status'] != 'OK':
        print(f"\n📊 IV Rank: {iv_data['status']}")
    else:
        new_high_lbl = " ⚠ 1년 신고IV" if iv_data.get('new_high') else ""
        print(f"\n📊 IV RANK: {iv_data['rank']}%{new_high_lbl} | IV PERCENTILE: {iv_data['pct']}%")
        if iv_data['rank'] <= 30:
            status_icon = "🟢"
            status_txt = "IV 저렴 → 옵션 프리미엄 낮음"
        elif iv_data['rank'] >= 70:
            status_icon = "🔴"
            status_txt = "IV 고가 → 옵션 프리미엄 높음 / 이벤트 내포"
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

        if sym == 'NDX':
            continue
        if sym in ['SPX', 'NDX']:
            _print_index_detail(sym, label, r, spy_price)
        else:
            _print_summary(sym, r)

    qqq_spot = next((float(r.get('curr') or 0) for r in results
                     if r and r.get('sym') == 'QQQ'), 0)
    for r in results:
        if r and r.get('sym') == 'NDX':
            overlay = _build_ndx_overlay(r, qqq_spot)
            r['_ndx_overlay'] = overlay
            if overlay['ndx_spot']['value']:
                r['curr'] = overlay['ndx_spot']['value']
            if overlay['ndx_derived_metrics']['enabled'] and overlay.get('derived_metrics'):
                r.update(overlay['derived_metrics'])
                r['_gex_low_confidence'] = False
                r['_data_source'] = {
                    **r.get('_data_source', {}),
                    'price': 'LIVE',
                    'chain': 'LIVE_DELAYED',
                    'oi': 'LIVE_DELAYED',
                    'overall': 'LIVE_DELAYED',
                }
                r['_timestamps'] = {
                    **r.get('_timestamps', {}),
                    'price_timestamp': overlay['ndx_spot']['timestamp'],
                    'option_chain_timestamp': overlay['ndx_option_chain']['timestamp'],
                    'oi_snapshot_timestamp': overlay['ndx_option_chain']['timestamp'],
                }
            else:
                r['_gex_low_confidence'] = True
                r['_data_source'] = {
                    **r.get('_data_source', {}),
                    'price': 'LIVE' if overlay['ndx_spot']['value'] else 'FALLBACK',
                    'chain': 'FALLBACK',
                    'overall': 'FALLBACK',
                }
            print("\n  NDX overlay 검증")
            print(f"  NDX spot: {overlay['ndx_spot']['value']:,.2f}" if overlay['ndx_spot']['value'] else "  NDX spot: N/A")
            print(f"  NDX Chain: {overlay['ndx_option_chain']['status']} / confidence {overlay['ndx_option_chain']['confidence']}")
            for eq in overlay.get('qqq_equiv', []):
                print(f"  NDX {eq['ndx']:,.0f} ≈ QQQ {eq['qqq']:,.1f}")
            if not overlay['ndx_derived_metrics']['enabled']:
                if overlay['ndx_option_chain']['status'] == 'LOW/FALLBACK':
                    print("  NDX Chain: LOW/FALLBACK - NDX spot only. Do not use NDX-derived GEX/Wall/Max Pain. Use QQQ proxy.")
                else:
                    print("  NDX Chain: REFERENCE_ONLY - NDX reference only. QQQ primary remains active.")
            print()
            _print_index_detail('NDX', r.get('label', 'Nasdaq 100 Index'), r, spy_price)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_content = generate_html(results, timestamp)

    DIR = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(DIR, 'options_dashboard.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"  브라우저에서 오픈 중...")
    webbrowser.open(f'file://{html_path}')
    print(f"  완료!\n")
    print("  💡 가이드:")
    print("  - P/C: >1.0 풋(헤지) | <0.7 콜(강세)")
    print("  - Max Pain: 옵션 포지션 분포 참고값 — 가격 예측 신호 아님")
    print("  - GEX: 양수(안정) | 음수(변동)")
    print("  - Wall: Call(저항) | Put(지지)\n")


if __name__ == '__main__':
    main()
