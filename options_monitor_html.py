"""옵션 모니터 — HTML 대시보드 생성 모듈
만기별 표 + GEX 차트 + 캘린더 + 0DTE 카드"""

import json
import os
from datetime import datetime, timezone, timedelta

from jm_lib.html_styles import html_head
from jm_lib.options import calc_vanna_charm
from options_monitor_base import (
    pc_signal, pc_color,
    weekday_ko, is_monthly, days_badge,
)
from options_monitor_render import render_iv_rank, render_0dte_block
from options_monitor_validate import (
    validate_price_pair, validate_gex_regime, validate_max_pain_label,
    calc_asset_confidence, record_confidence_history, get_confidence_trend,
    cap_confidence_by_conditions, detect_compressed_gamma_risk,
    select_proxy_mode, detect_iv_rank_anomaly,
)

_SNAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'options_gex_snapshot.json')


def _exp_comment(row: dict, curr: float) -> str:
    """만기별 해설 텍스트 생성"""
    days = row['days']
    pc_oi = row['pc_oi']
    iv = row['iv']
    mp = row['max_pain']
    c_oi = row['c_oi']
    p_oi = row['p_oi']
    ok = row.get('ok', True)

    if not ok:
        return '⚠ 데이터 수집 실패'

    parts = []
    is_mo = is_monthly(row['exp'])

    if days <= 0:
        parts.append('📌 오늘 만기 — 감마 위험 극대, 핀 리스크 주의')
    elif days <= 3:
        parts.append('⚡ 초단기 — 델타·감마 변동 매우 심함')
    elif days <= 7:
        parts.append('🔥 단기 주물 — 빠른 시간가치 소멸')
    elif days <= 30:
        if is_mo:
            parts.append('📅 월물 만기 — 대형 포지션 정리·롤오버 집중')
        else:
            parts.append('📆 단기 주물')
    elif days <= 90:
        if is_mo:
            parts.append('📅 월물 (중기) — 기관 헤지 주요 만기')
        else:
            parts.append('📆 중기 주물')
    else:
        parts.append('🏦 장기 LEAPS — 기관·대형 방향성 배팅')

    if (c_oi + p_oi) > 0:
        if pc_oi >= 2.0:
            parts.append('🐻 극강 풋 우세 (강한 하락 헤지)')
        elif pc_oi >= 1.3:
            parts.append('🐻 풋 우세 (약세 배팅)')
        elif pc_oi <= 0.5:
            parts.append('🐂 극강 콜 우세 (강한 상승 배팅)')
        elif pc_oi <= 0.8:
            parts.append('🐂 콜 우세 (강세 배팅)')
        else:
            parts.append('⚖ 콜·풋 균형')

    if iv >= 50:
        parts.append(f'🌋 IV {iv:.0f}% 매우 높음 (이벤트/공포)')
    elif iv >= 35:
        parts.append(f'⚠ IV {iv:.0f}% 높음')
    elif iv > 0:
        parts.append(f'IV {iv:.0f}%')

    if mp:
        diff = (mp - curr) / curr * 100
        # DTE에 따라 Max Pain 표현 제한 (>45 DTE: 방향 예측 금지)
        parts.append(validate_max_pain_label(diff, days))

    tot_oi = c_oi + p_oi
    if tot_oi >= 1_000_000:
        parts.append('💎 초대형 OI')
    elif tot_oi >= 500_000:
        parts.append('🔵 대형 OI')
    elif tot_oi >= 100_000:
        parts.append('중규모 OI')

    return ' · '.join(parts) if parts else '–'


def generate_html(results: list, timestamp: str) -> str:
    """전체 옵션 모니터 대시보드 HTML"""

    # ─── ① Δ GEX: 이전 스냅샷 로드 ─────────────────────────────
    try:
        with open(_SNAP_FILE) as _f:
            _prev_snap = json.load(_f)
    except Exception:
        _prev_snap = {}
    _curr_snap = {}

    # ─── ④ OCC 시점 경고 (NYSE 개장 1시간 이내) ─────────────────
    _KST = timezone(timedelta(hours=9))
    _now_h = datetime.now(_KST).hour + datetime.now(_KST).minute / 60
    # NYSE: 09:30 EDT = 22:30 KST / 09:30 EST = 23:30 KST
    # 22:00~01:00 KST 구간에 경고 표시
    _occ_warn = _now_h >= 22.0 or _now_h < 1.0
    _occ_banner_html = ''
    if _occ_warn:
        _occ_banner_html = (
            '<div style="margin-top:6px;padding:4px 8px;background:#fff3e0;'
            'border-left:3px solid #f97316;border-radius:3px;font-size:9px;color:#7c4100;">'
            '⚠ <strong>OCC 데이터 시점 주의</strong>: OI는 전일 종가 기준 · Volume은 당일 실시간 '
            '· NYSE 개장 초 1시간은 GEX 신뢰도 제한됨'
            '</div>'
        )

    # ─── ② Prediction Cone 데이터 사전 계산 ──────────────────────
    for _r in results:
        if not _r:
            continue
        _r['cone_data'] = [
            {'days': row['days'], 'upper': row['upper_price'],
             'lower': row['lower_price'], 'exp': row['exp']}
            for row in _r.get('exp_rows', [])
            if row.get('straddle_em', 0) > 0 and row.get('days', 0) > 0
        ]

    data_js = json.dumps(results, ensure_ascii=False)

    # ─── ⑧ 전체 신뢰도 사전 계산 (proxy engine용) ────────────────────
    _pre_confs: dict = {}
    for _r0 in results:
        if not _r0:
            continue
        _s0 = _r0['sym']
        _pc0 = None
        if _s0 == 'SPX':
            _spy0 = next((x['curr'] for x in results if x and x['sym'] == 'SPY'), 0)
            if _spy0 > 0:
                _pc0 = validate_price_pair(_r0['curr'], _spy0)
        _c0  = calc_asset_confidence(_r0, pair_check=_pc0)
        # SPX/NDX confidence cap 적용
        _ds0 = _r0.get('_data_source', {})
        _cap_cond0 = {
            'is_full_fallback':  _ds0.get('price') == 'FALLBACK' and _ds0.get('chain') == 'FALLBACK',
            'chain_is_fallback': _ds0.get('chain') == 'FALLBACK',
            'ratio_abnormal':    (_pc0 or {}).get('low_confidence', False),
            'render_mismatch':   False,
            'stale_timestamp':   _c0.get('stale_penalty', 0) > 0,
        }
        _capped0, _reason0, _forced0 = cap_confidence_by_conditions(_c0['score'], _cap_cond0)
        if _forced0:
            _c0 = {**_c0, 'score': _capped0, 'label': _forced0,
                   '_cap_reason': _reason0}
        _pre_confs[_s0] = _c0

    # ─── ⑨ Proxy Priority Engine ─────────────────────────────────────
    _proxy_mode = select_proxy_mode(_pre_confs)

    # ─── ⑩ IV Rank 이상 감지 (루프 후 집계) ─────────────────────────
    # (루프 내에서 수집 후 루프 뒤에서 사용)
    _iv_rank_map: dict = {}

    # ─── ⑪ Dashboard Integrity Summary HTML ─────────────────────────
    _high_syms = [s for s, c in _pre_confs.items() if c['label'] in ('HIGH', 'MEDIUM_HIGH')]
    _low_syms  = [s for s, c in _pre_confs.items() if c['label'] in ('LOW', 'VERY_LOW')]
    _proxy_sp  = _proxy_mode['proxies']['SP500']['primary']
    _proxy_nq  = _proxy_mode['proxies']['NASDAQ']['primary']
    _spx_ignored = (_proxy_sp != 'SPX')
    _ndx_demoted = (_proxy_nq != 'NDX')

    _summary_notes_html = ''.join(
        f'<li style="margin:2px 0">{n}</li>' for n in _proxy_mode['notes']
    )
    _dashboard_summary = f"""
<div style="background:#0f172a;border:1.5px solid #334155;border-radius:10px;
     padding:14px 18px;margin-bottom:18px;color:#f8fafc;">
  <div style="font-size:13px;font-weight:700;color:#38bdf8;margin-bottom:8px;">
    📊 Data Integrity Summary
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;">
    <div>
      <div style="color:#94a3b8;font-weight:600;margin-bottom:4px;">PROXY STATUS</div>
      <ul style="padding-left:14px;color:#e2e8f0;line-height:1.8;">
        {_summary_notes_html}
      </ul>
    </div>
    <div>
      <div style="color:#94a3b8;font-weight:600;margin-bottom:4px;">CONFIDENCE</div>
      <div style="color:#22c55e">HIGH/MH: {', '.join(_high_syms) or '없음'}</div>
      <div style="color:#f97316">LOW/VL:  {', '.join(_low_syms) or '없음'}</div>
      <div style="color:#94a3b8;margin-top:4px;font-size:10px;">
        ⚠ FALLBACK GEX/Wall/Max Pain은 의사결정 제외
      </div>
    </div>
  </div>
</div>"""

    # SPX stale/fallback 최상단 배너 (SPX가 IGNORED일 때)
    _spx_stale_banner = ''
    if _spx_ignored:
        _spx_stale_banner = f"""
<div style="background:#fff3e0;border:2px solid #f97316;border-radius:8px;
     padding:10px 16px;margin-bottom:14px;font-size:12px;font-weight:700;color:#7c4100;">
  ⛔ SPX price stale/fallback. Ignore SPX GEX/Wall/Max Pain.
  Use <strong>SPY</strong> as S&P500 proxy.
  SPX section is LOW/VERY_LOW confidence — Do not use for trading decisions.
</div>"""

    cards = ''
    for r in results:
        if not r:
            continue
        sym = r['sym']
        curr = r['curr']
        mp = r['max_pain']
        pc_oi = r['pc_oi']
        sig, sig_color = pc_signal(pc_oi)
        mp_diff = round((mp - curr) / curr * 100, 2) if mp else None
        mp_str = f"${mp:,.2f} ({mp_diff:+.1f}%)" if mp and mp_diff is not None else 'N/A'

        # Max Pain 긴급 지표 (7일 이내 만기)
        mp_urgency = ''
        if mp and mp_diff is not None:
            near_exp = next((row for row in r['exp_rows']
                             if row.get('max_pain') and row['days'] <= 7), None)
            if near_exp and near_exp['max_pain']:
                mp_near = near_exp['max_pain']
                mp_near_diff = (mp_near - curr) / curr * 100
                if abs(mp_near_diff) >= 2:
                    direction = '하방' if mp_near_diff < 0 else '상방'
                    mp_urgency = (f"⚡ 주의: 이번주 만기 Max Pain {mp_near_diff:+.1f}% "
                                  f"({direction} 당김)")

        # ── 만기별 상세 테이블 ──────────────────────────────
        exp_rows_html = ''
        for row in r['exp_rows']:
            days = row['days']
            c_vol = row['c_vol']
            p_vol = row['p_vol']
            tot_vol = c_vol + p_vol
            pc_vol = row['pc_vol']
            c_oi = row['c_oi']
            p_oi = row['p_oi']
            tot_oi = c_oi + p_oi
            pc_oi_r = row['pc_oi']
            iv = row['iv']
            st_em = row['straddle_em']
            st_em_pct = row['straddle_em_pct']
            upper_p = row['upper_price']
            lower_p = row['lower_price']
            atm_s = row['atm_strike']
            mp_r = row['max_pain']
            mpd = row['mp_diff']

            pc_vol_c = pc_color(pc_vol)
            pc_oi_c = pc_color(pc_oi_r)
            iv_cls = 'iv-hi' if iv >= 40 else ('iv-mid' if iv >= 25 else 'iv-lo')
            mp_cell = f'${mp_r:,.2f}' if mp_r else '–'
            mpd_cell = f'{mpd:+.1f}%' if mpd is not None else '–'
            mpd_color = '#26a69a' if (mpd or 0) >= 0 else '#ef5350'

            # 기대변동 셀
            if st_em > 0:
                em_cell = (f'<span class="em-val">±{st_em_pct:.1f}%</span>'
                           f'<br><span class="em-sub">±${st_em:,.2f}</span>'
                           f'<br><span class="em-range">'
                           f'<span class="em-up">▲{upper_p:,.2f}</span>'
                           f'<br><span class="em-dn">▼{lower_p:,.2f}</span>'
                           f'</span>')
            else:
                em_cell = '–'

            # Max Pain 합성 셀
            if mp_r:
                mp_combined = (f'<span class="mp-price">${mp_r:,.2f}</span>'
                               f'<br><span class="mp-diff" style="color:{mpd_color}">{mpd_cell}</span>')
            else:
                mp_combined = '–'

            # P/C 합성 셀
            pc_tooltip = (f'콜Vol:{c_vol:,} / 풋Vol:{p_vol:,}&#10;'
                          f'콜OI:{c_oi:,} / 풋OI:{p_oi:,}')
            if tot_oi > 0:
                call_w = round(c_oi / tot_oi * 100, 1)
                put_w = 100 - call_w
                pc_bar = (f'<div class="pc-bar-wrap" title="{pc_tooltip}">'
                          f'<div class="pc-bar-c" style="width:{call_w}%"></div>'
                          f'<div class="pc-bar-p" style="width:{put_w}%"></div>'
                          f'</div>')
            else:
                pc_bar = ''

            pc_cell = (f'<div class="pc-line"><span class="pc-lbl">Vol</span>'
                       f'<span style="color:{pc_vol_c};font-weight:700">{pc_vol:.2f}</span></div>'
                       f'<div class="pc-line"><span class="pc-lbl">OI&nbsp;</span>'
                       f'<span style="color:{pc_oi_c};font-weight:700">{pc_oi_r:.2f}</span></div>'
                       f'{pc_bar}')

            row_cls = ' class="row-near"' if days <= 7 else (
                ' class="row-mid"' if days <= 30 else '')
            wd = weekday_ko(row['exp'])
            comment = _exp_comment(row, curr)
            ok = row.get('ok', True)
            row_cls_extra = '' if ok else ' style="opacity:0.5"'

            exp_rows_html += f"""
<tr{row_cls}{row_cls_extra}>
  <td class="exp-date">{row['exp']}<span class="wd">({wd})</span></td>
  <td style="text-align:center">{days_badge(days)}</td>
  <td class="pc-cell" title="{pc_tooltip}">{pc_cell}</td>
  <td class="num {iv_cls}">{iv:.1f}%</td>
  <td class="em-cell2">{em_cell}</td>
  <td class="mp-cell">{mp_combined}</td>
  <td class="comment-cell">{comment}</td>
</tr>"""

        # 합계행
        tot_c_vol = sum(x['c_vol'] for x in r['exp_rows'])
        tot_p_vol = sum(x['p_vol'] for x in r['exp_rows'])
        tot_c_oi = sum(x['c_oi'] for x in r['exp_rows'])
        tot_p_oi = sum(x['p_oi'] for x in r['exp_rows'])
        tot_pc_vol = round(tot_p_vol / tot_c_vol if tot_c_vol else 0, 2)
        tot_pc_oi = round(tot_p_oi / tot_c_oi if tot_c_oi else 0, 2)
        exp_rows_html += f"""
<tr class="row-total">
  <td colspan="2"><strong>합계</strong></td>
  <td class="pc-cell">
    <div class="pc-line"><span class="pc-lbl">Vol</span><span style="color:{pc_color(tot_pc_vol)};font-weight:700">{tot_pc_vol:.2f}</span></div>
    <div class="pc-line"><span class="pc-lbl">OI&nbsp;</span><span style="color:{pc_color(tot_pc_oi)};font-weight:700">{tot_pc_oi:.2f}</span></div>
  </td>
  <td></td><td></td><td></td><td></td>
</tr>"""

        # 상위 스트라이크 표
        top_c_rows = ''.join(
            f"<tr><td>${x['strike']:,.2f}</td><td>{int(x['oi']):,}</td></tr>"
            for x in r['top_calls']
        )
        top_p_rows = ''.join(
            f"<tr><td>${x['strike']:,.2f}</td><td>{int(x['oi']):,}</td></tr>"
            for x in r['top_puts']
        )

        # ── GEX HTML 준비 ──────────────────────────────────
        gex = r.get('gex', {})
        ngb = gex.get('net_gex_b', 0) or 0
        cwall = gex.get('call_wall')
        pwall = gex.get('put_wall')
        gflip = gex.get('gamma_flip')
        ngb_cls = 'gex-pos' if ngb >= 0 else 'gex-neg'
        ngb_str = f'{"+" if ngb >= 0 else ""}${ngb:.3f}B'

        # GEX 레짐 — NET GEX 부호 + Gamma Flip 위치 분리 검증
        _regime = validate_gex_regime(ngb * 1e9, curr, gflip)
        gex_regime   = _regime['display_label']
        _regime_final = _regime['final_regime']

        # 혼합 신호 주의문 추가
        if _regime['caution_note']:
            gex_regime += f' — {_regime["caution_note"]}'

        # Gamma Flip 라벨
        if gflip:
            _dist = (curr - gflip) / curr * 100
            if curr > gflip:
                _flip_base = f"▼ 현재가 아래 ({_dist:+.1f}%)"
                if _regime_final == 'MIXED_SIGNAL':
                    gflip_label = _flip_base + ' ⚠ 혼합 신호 — 단독 롱감마 판정 금지'
                else:
                    gflip_label = _flip_base + ' ✅'
            else:
                gflip_label = f"▲ 현재가 위 ({_dist:+.1f}%) ⚠"
        else:
            gflip_label = "감마 플립 데이터 없음"

        # Gamma Flip 이탈 주의 (>10%)
        if _regime.get('flip_far_note'):
            gflip_label += f' — {_regime["flip_far_note"]}'

        gflip_cls    = ("gex-pos" if _regime_final == 'LONG_GAMMA'
                        else "gex-neg" if _regime_final == 'SHORT_GAMMA'
                        else "gex-warn")
        regime_badge = ("b-long-gamma"  if _regime_final == 'LONG_GAMMA'
                        else "b-short-gamma" if _regime_final == 'SHORT_GAMMA'
                        else "b-neutral")

        # Call Wall 돌파 판단
        cwall_str = f'${cwall:,.2f}' if cwall else 'N/A'
        if cwall:
            cwall_pct = (cwall / curr - 1) * 100
            if curr > cwall:
                cwall_label = f"돌파 완료 구간 / 하방 지지 전환 ({cwall_pct:.1f}%)"
            else:
                cwall_label = f"콜 감마 집중 저항 ({cwall_pct:.1f}%)"
        else:
            cwall_label = "N/A"

        # Put Wall 고정
        pwall_str = f'${pwall:,.2f}' if pwall else 'N/A'
        pwall_pct = (pwall / curr - 1) * 100 if pwall else 0
        pwall_label = f"풋 감마 집중 지지 ({pwall_pct:.1f}%)"

        gflip_str = f'${gflip:,.2f}' if gflip else 'N/A'

        # ─── ① Δ GEX 계산 ───────────────────────────────────────
        _prev_ngb = _prev_snap.get(sym, {}).get('net_gex_b')
        _curr_snap[sym] = {'net_gex_b': ngb}
        if _prev_ngb is not None:
            _gex_delta = ngb - _prev_ngb
            if _gex_delta > 0:
                _delta_str = f'▲ Δ +{_gex_delta:.3f}B'
                _delta_color = '#22c55e'
            elif _gex_delta < 0:
                _delta_str = f'▼ Δ {_gex_delta:.3f}B'
                _delta_color = '#ef4444'
            else:
                _delta_str = 'Δ 변화없음'
                _delta_color = '#94a3b8'
        else:
            _delta_str = 'Δ 최초 기록 중'
            _delta_color = '#64748b'

        # ─── ③ Gamma Flip 거리 경보 ─────────────────────────────
        if gflip and curr:
            _gdist_pt = curr - gflip
            _gdist_pct = _gdist_pt / curr * 100
            _gdist_abs = abs(_gdist_pct)
            if _gdist_abs < 0.5:
                _gdist_color = '#ef4444'
                _gdist_tag = '🔴 임박'
            elif _gdist_abs < 2.0:
                _gdist_color = '#f97316'
                _gdist_tag = '🟠 근접'
            else:
                _gdist_color = '#22c55e'
                _gdist_tag = '🟢 여유'
            _gflip_dist_html = (
                f'<div class="gex-dist" style="color:{_gdist_color};margin-top:4px;">'
                f'{_gdist_pt:+.2f}pt&nbsp;({_gdist_pct:+.2f}%)&nbsp;{_gdist_tag}</div>'
            )
        else:
            _gflip_dist_html = ''

        # ─── ⑦ 박스 폭 자동 계산 ────────────────────────────────
        if cwall and pwall:
            _box_pt = cwall - pwall
            _box_pct = _box_pt / curr * 100
            _box_lbl = '좁음 ⚠' if _box_pct < 1 else ('넓음 ✅' if _box_pct > 3 else '보통')
            _box_clr = '#ef4444' if _box_pct < 1 else ('#22c55e' if _box_pct > 3 else '#f97316')
            _box_strip_html = (
                f'<div class="box-strip">'
                f'<span class="box-lbl">📏 박스 폭</span>'
                f'<span class="box-val" style="color:{_box_clr}">'
                f'${_box_pt:,.2f}&nbsp;({_box_pct:.1f}%)</span>'
                f'<span class="box-tag" style="color:{_box_clr}">{_box_lbl}</span>'
                f'<span class="box-hint">Call Wall – Put Wall / 현재가</span>'
                f'</div>'
            )
        else:
            _box_strip_html = ''

        # gex-grid 하단 border-radius: box-strip 있을 때는 직각, 없을 때는 둥글게
        _gex_grid_style = '' if not _box_strip_html else ' style="border-radius:8px 8px 0 0;"'

        # Expected Move 위치 표시
        near_em_row = next((row for row in r['exp_rows']
                            if row['straddle_em'] > 0 and row['days'] > 0), None)
        if near_em_row:
            em_upper = near_em_row['upper_price']
            em_lower = near_em_row['lower_price']
            em_pct = near_em_row['straddle_em_pct']
            em_days = near_em_row['days']
            em_range = em_upper - em_lower
            if em_range > 0:
                em_pos = max(0, min(100, (curr - em_lower) / em_range * 100))
            else:
                em_pos = 50
            em_hint = '✅ 기대범위 안' if 20 < em_pos < 80 else '⚠ 기대범위 경계 근처'
            em_html = f"""
    <div class="em-section">
      <div class="em-title">📐 기대변동 위치 — {em_days}일 후 만기 기준 (±{em_pct:.1f}%)</div>
      <div class="em-track-wrap">
        <span class="em-bound">▼${em_lower:,.0f}</span>
        <div class="em-track">
          <div class="em-zone"></div>
          <div class="em-cursor" style="left:{em_pos:.1f}%"></div>
        </div>
        <span class="em-bound">▲${em_upper:,.0f}</span>
      </div>
      <div class="em-hint">{em_hint}</div>
    </div>"""
        else:
            em_html = ''

        # ─── ② Prediction Cone HTML ──────────────────────────────
        _cone_rows = r.get('cone_data', [])
        if len(_cone_rows) >= 2:
            cone_html = f"""
    <div class="section">
      <div class="section-title" style="font-size:12px;font-weight:700;color:#555;margin-bottom:8px;">🔮 Prediction Cone — 만기별 기대변동 범위 <span style="font-weight:400;font-size:10px;color:#aaa">· Expected Move: ATM Straddle 기반</span></div>
      <div style="position:relative;height:140px;">
        <canvas id="chart-{sym}-cone"></canvas>
      </div>
    </div>"""
        else:
            cone_html = ''

        # SPX-SPY 페어 비율 검증 — validate_price_pair로 신뢰도 전파
        pair_ratio_html = ''
        _pair_check     = None          # SPX 외 자산은 None 유지
        if sym == 'SPX':
            spy_p = next((x['curr'] for x in results if x and x['sym'] == 'SPY'), 0)
            if spy_p > 0:
                _pair_check = validate_price_pair(curr, spy_p, 'SPX', 'SPY')
                ratio = _pair_check['ratio']
                if _pair_check['low_confidence']:
                    _pair_warn = (
                        f' <span style="color:#ef5350;font-weight:700">⚠ 페어 비율 이상 '
                        f'({_pair_check["confidence"]})</span>'
                        f'<div style="font-size:9px;color:#ef5350;margin-top:2px;">'
                        f'{_pair_check["warning"][:80]}</div>'
                    )
                else:
                    _pair_warn = ' <span style="color:#22c55e;font-size:9px">✅ 정상 범위</span>'
                pair_ratio_html = (
                    f'<div class="meta-sub" id="SPX-pair-ratio" '
                    f'style="margin-top:4px;color:#333;font-weight:500">'
                    f'📎 페어 ETF: SPY | SPX ÷ SPY 비율: {ratio:.2f}x{_pair_warn}</div>'
                )

        # MODULE 2 & 3 데이터 계산
        vc = calc_vanna_charm(r)
        iv_rank_data = render_iv_rank(r)

        vanna_cls = 'gex-pos' if vc['vanna'] >= 0 else 'gex-neg'
        charm_cls = 'gex-pos' if vc['charm'] >= 0 else 'gex-neg'

        # IV Rank 소스 결정 (실현변동성 proxy vs implied IV)
        _iv_src_label = ('INSUFFICIENT_HISTORY' if iv_rank_data.get('insufficient_history')
                         else 'REALIZED_VOL_PROXY')   # yfinance는 항상 realized vol proxy
        _iv_rank_map[sym] = {'rank': iv_rank_data.get('rank'), 'source': _iv_src_label}

        # IV Rank: None이면 insufficient_history 표시 (100% 강제 금지)
        _iv_rank = iv_rank_data.get('rank')
        _iv_pct  = iv_rank_data.get('pct')
        if _iv_rank is None:
            rank_str   = 'N/A'
            pct_str    = 'N/A'
            rank_color = '#94a3b8'
            rank_desc  = 'INSUFFICIENT_HISTORY — 이력 부족'
            if iv_rank_data.get('low_confidence'):
                rank_desc += ' <span style="font-size:9px;color:#ef5350">⚠ 저신뢰</span>'
        else:
            rank_str   = f'{_iv_rank:.1f}%'
            pct_str    = f'{_iv_pct:.1f}%' if _iv_pct is not None else 'N/A'
            rank_color = '#26a69a' if _iv_rank <= 30 else ('#ef5350' if _iv_rank >= 70 else '#ffb300')
            rank_desc  = ('IV 저렴 🟢' if _iv_rank <= 30
                          else 'IV 고가 🔴' if _iv_rank >= 70 else 'IV 보통 🟡')
            if iv_rank_data.get('new_high'):
                rank_desc += ' <span style="font-size:10px;color:#d32f2f">⚠ 1년 신고IV</span>'
            # REALIZED_VOL_PROXY 경고
            rank_desc += (
                f' <span style="font-size:8px;color:#94a3b8;display:block;margin-top:2px;">'
                f'소스: {_iv_src_label}'
                f'{" ⚠ 옵션 IV 아님" if _iv_src_label == "REALIZED_VOL_PROXY" else ""}'
                f'</span>'
            )

        # 자산별 신뢰도 점수 계산 (사전계산 결과 재사용)
        _conf = _pre_confs.get(sym) or calc_asset_confidence(r, pair_check=_pair_check)

        # SPX/NDX 추가 cap 적용 (사전계산에서 이미 적용됐지만 확인용)
        _ds  = r.get('_data_source', {})
        _cap_cond = {
            'is_full_fallback':  _ds.get('price') == 'FALLBACK' and _ds.get('chain') == 'FALLBACK',
            'chain_is_fallback': _ds.get('chain') == 'FALLBACK',
            'ratio_abnormal':    (_pair_check or {}).get('low_confidence', False),
            'render_mismatch':   False,
            'stale_timestamp':   _conf.get('stale_penalty', 0) > 0,
        }
        # price audit mismatch 감지
        _audit_trail = r.get('_price_audit', {})
        _selected_p  = _audit_trail.get('selected_price')
        _final_rend  = _audit_trail.get('final_rendered_price')
        _mismatch_critical = ''
        if _selected_p and _final_rend and abs(_selected_p - _final_rend) > 1.0:
            _cap_cond['render_mismatch'] = True
            _mismatch_critical = (
                f'<div style="background:#ef4444;color:#fff;font-weight:700;'
                f'padding:6px 10px;border-radius:4px;font-size:10px;margin-top:6px;">'
                f'CRITICAL: selected SPX live price {_selected_p:,.2f} but rendered price '
                f'{_final_rend:,.2f}. Snapshot/render mismatch.</div>'
            )
        _capped_s, _cap_reason, _forced_label = cap_confidence_by_conditions(
            _conf['score'], _cap_cond)
        if _forced_label:
            from options_monitor_validate import calc_confidence_score as _ccs
            _conf = {**_conf, **_ccs({'price_pair': _capped_s,
                                       'expiry_dte': 0, 'chain_completeness': 0,
                                       'gex_consistency': 0, 'iv_history': 0,
                                       'wall_sanity': 0}),
                     'score': _capped_s, 'label': _forced_label,
                     '_cap_reason': _cap_reason}

        try:
            record_confidence_history(sym, _conf)
        except Exception:
            pass

        # 신뢰도 추세 스파크라인
        _trend = get_confidence_trend(sym, n=6)
        _trend_html = ''
        if _trend['scores']:
            _arrow = {'UP': '▲', 'DOWN': '▼', 'FLAT': '→'}[_trend['trend']]
            _arrow_color = ({'UP': '#22c55e', 'DOWN': '#ef4444', 'FLAT': '#94a3b8'}
                            [_trend['trend']])
            _trend_html = (
                f'<span style="font-size:9px;color:#888;margin-left:8px;">'
                f'추세 <span style="font-family:monospace;letter-spacing:1px;">'
                f'{_trend["sparkline"]}</span> '
                f'<span style="color:{_arrow_color}">{_arrow}{abs(_trend["delta"])}pt</span>'
                f'</span>'
            )

        _conf_badge = (
            f'<span style="float:right;font-size:9px;font-weight:600;padding:2px 6px;'
            f'border-radius:3px;background:{_conf["badge_color"]};color:#fff;">'
            f'신뢰도 {_conf["label"]} ({_conf["score"]}점)'
            f'</span>{_trend_html}'
        )
        _conf_note = (
            f'<div style="font-size:9px;color:{_conf["badge_color"]};'
            f'margin-top:2px;font-weight:600">{_conf["display_note"]}'
            + (f' &nbsp;|&nbsp; stale-{_conf["stale_penalty"]}pt fallback-{_conf["fallback_penalty"]}pt'
               if _conf["stale_penalty"] or _conf["fallback_penalty"] else '')
            + '</div>'
            if _conf['display_note'] else ''
        )

        # 데이터 소스 워터마크 (FALLBACK / STALE 시 카드 상단 표시)
        _ds       = r.get('_data_source', {})
        _ds_status = _ds.get('overall', 'LIVE')
        _watermark_html = ''
        if _ds_status == 'FALLBACK':
            _watermark_html = (
                '<div style="margin-top:6px;padding:4px 10px;'
                'background:#fff3e0;border:1.5px dashed #f97316;'
                'border-radius:4px;font-size:9px;color:#7c4100;font-weight:600;">'
                '📦 FALLBACK 데이터 — 옵션 체인 CBOE 미수집 · GEX/Wall/Max Pain 저신뢰'
                '</div>'
            )
        elif _ds_status == 'PARTIAL':
            _watermark_html = (
                '<div style="margin-top:6px;padding:4px 10px;'
                'background:#fff8e1;border:1.5px dashed #f59e0b;'
                'border-radius:4px;font-size:9px;color:#78350f;font-weight:600;">'
                '⚠ PARTIAL 데이터 — 가격은 실시간 · 옵션 체인 폴백'
                '</div>'
            )
        elif _ds_status == 'STALE':
            _watermark_html = (
                '<div style="margin-top:6px;padding:4px 10px;'
                'background:#f0f9ff;border:1.5px dashed #38bdf8;'
                'border-radius:4px;font-size:9px;color:#0c4a6e;font-weight:600;">'
                '⏱ STALE 데이터 — 30분 이상 경과 · 신뢰도 제한'
                '</div>'
            )

        # ─── Compressed Mixed Gamma Risk ───────────────────────────
        _cgr = detect_compressed_gamma_risk(
            spot=curr,
            net_gex=(gex.get('net_gex_b') or 0) * 1e9,
            gamma_flip=gex.get('gamma_flip'),
            call_wall=gex.get('call_wall'),
            put_wall=gex.get('put_wall'),
            pc_oi=r.get('pc_oi', 0),
        )
        _cgr_html = ''
        if _cgr.get('compressed'):
            _cgr_html = (
                f'<div style="margin:8px 0;padding:8px 12px;'
                f'background:#fff8e1;border-left:4px solid #f59e0b;'
                f'border-radius:4px;font-size:11px;color:#78350f;font-weight:600;">'
                f'⚠ {_cgr["label"]}</div>'
            )
        elif _cgr.get('label'):
            _cgr_html = (
                f'<div style="margin:6px 0;padding:6px 10px;'
                f'background:#f0f9ff;border-left:3px solid #38bdf8;'
                f'border-radius:4px;font-size:10px;color:#0c4a6e;">'
                f'{_cgr["label"]}</div>'
            )

        # GEX 저신뢰 강등 (폴백 자산의 GEX 섹션)
        _gex_low_conf = r.get('_gex_low_confidence', False)

        # SPX LOW confidence 전용 배너
        _gex_section_warning = ''
        if _conf.get('label') in ('LOW', 'VERY_LOW') and sym in ('SPX', 'NDX'):
            _proxy_sym = 'SPY' if sym == 'SPX' else 'QQQ'
            _gex_section_warning = (
                f'<div style="margin-bottom:8px;padding:8px 12px;'
                f'background:#fef2f2;border:1.5px solid #ef4444;'
                f'border-radius:6px;font-size:10px;color:#7f1d1d;font-weight:600;">'
                f'⛔ {sym} section is {_conf["label"]} confidence. '
                f'Do not use {sym}-derived GEX/Wall/Max Pain for trading decisions. '
                f'Prefer <strong>{_proxy_sym}</strong> proxy.'
                f'</div>'
            )

        # 0DTE 카드
        zdte = render_0dte_block(r)
        zdte_html = ''
        if zdte:
            is_long = '롱감마' in zdte['gex_dir']
            zdte_cls = 'b-long-gamma' if is_long else 'b-short-gamma'
            zdte_html = f"""
<div class="card" style="background:#0f172a; border-left: 4px solid {'#16a34a' if is_long else '#dc2626'}; margin-bottom:15px; padding:16px;">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
    <div style="font-size:16px; font-weight:800; color:#f8fafc;">🔥 0DTE 당일 결전 데이터</div>
    <span class="badge {zdte_cls}">딜러 {'롱감마 ✅' if is_long else '숏감마 ⚠'}</span>
  </div>
  <div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:1px; background:#334155; border-radius:6px; overflow:hidden;">
    <div class="sbox" style="background:#1e293b; padding:12px;">
      <div class="slbl">기대변동 (±%)</div>
      <div class="sval" style="color:#f8fafc">±{zdte['em_pct']:.1f}%</div>
      <div class="ssub">±${zdte['em_val']:,.2f}</div>
    </div>
    <div class="sbox" style="background:#1e293b; padding:12px;">
      <div class="slbl">당일 편향</div>
      <div class="sval" style="color:#f8fafc; font-size:12px;">{zdte['bias']}</div>
      <div class="ssub">P/C Vol: {zdte['pc_vol']:.2f}</div>
    </div>
    <div class="sbox" style="background:#1e293b; padding:12px;">
      <div class="slbl">기대 범위</div>
      <div class="sval" style="color:#f8fafc; font-size:11px;">▲${zdte['upper']:,.1f} ~ ▼${zdte['lower']:,.1f}</div>
    </div>
    <div class="sbox" style="background:#1e293b; padding:12px;">
      <div class="slbl">Max Pain</div>
      <div class="sval" style="color:#f8fafc">${zdte['mp']:,.1f}</div>
      <div class="ssub">{zdte['mp_diff']:+.1f}% 차이</div>
    </div>
  </div>
</div>"""

        cards += f"""
<div class="card" id="{sym}-card">

  <!-- 헤더 -->
  <div class="card-header">
    <div class="title-row">
      <span class="sym">{sym}</span>
      <span class="lbl">{r['label']}</span>
      <span class="price">${curr:,.2f}</span>
      {_conf_badge}
    </div>
    <div class="meta-sub">{r['exp_count']} 만기 | 소스: CBOE, Straddle EM</div>
    {_conf_note}
    {_watermark_html}
    {_mismatch_critical}
    {pair_ratio_html}
    {_occ_banner_html}
  </div>

  <!-- 요약 통계 -->
  <div class="stats-grid">
    <div class="sbox">
      <div class="slbl">전체 P/C OI</div>
      <div class="sval" style="color:{sig_color}">{pc_oi:.2f}</div>
      <div class="ssub" style="color:{sig_color}">{sig}</div>
      <div class="pc-note">※ P/C > 1.3: 기관 헤지/중립 가능성</div>
    </div>
    <div class="sbox">
      <div class="slbl">전체 P/C Volume</div>
      <div class="sval">{r['pc_vol']:.2f}</div>
      <div class="ssub">{pc_signal(r['pc_vol'])[0]}</div>
    </div>
    <div class="sbox" style="border-left: 3px solid {rank_color}">
      <div class="slbl">IV RANK / PCT</div>
      <div class="sval" style="color:{rank_color}">{rank_str} / {pct_str}</div>
      <div class="ssub">{rank_desc}</div>
    </div>
    <div class="sbox">
      <div class="slbl">1개월 Max Pain</div>
      <div class="sval">{mp_str}</div>
      <div class="ssub">옵션 매도자 유리 가격{f' &nbsp;<span style="color:#e65100;font-size:9px">{mp_urgency}</span>' if mp_urgency else ''}</div>
    </div>
  </div>

  <div class="stats-grid" style="margin-top:10px; border-top:1px solid #eee; padding-top:10px;">
    <div class="sbox" title="Vanna: IV 변화 시 델타 변화 (Black-Scholes 추정)">
      <div class="slbl">⚡ Net VANNA</div>
      <div class="sval {vanna_cls}">${vc['vanna']:.3f}B</div>
      <div class="ssub" style="font-size:8px">{'VIX 하락시 매수' if vc['vanna']>=0 else 'VIX 하락시 매도'} <span style="opacity:0.5">⚠추정치</span></div>
    </div>
    <div class="sbox" title="Charm: 시간 경과 시 델타 변화 (Black-Scholes 추정)">
      <div class="slbl">⏱ Net CHARM</div>
      <div class="sval {charm_cls}">${vc['charm']:.3f}B</div>
      <div class="ssub" style="font-size:8px">{'시간경과시 상방' if vc['charm']>=0 else '시간경과시 하방'} <span style="opacity:0.5">⚠추정치</span></div>
    </div>
    <div class="sbox">
      <div class="slbl">콜 OI / 풋 OI</div>
      <div class="sval"><span class="up">{r['tc_oi']:,}</span> / <span class="dn">{r['tp_oi']:,}</span></div>
      <div class="ssub">전체 Open Interest</div>
    </div>
    <div class="sbox">
      <div class="slbl">IV 콜/풋 평균</div>
      <div class="sval">{r['iv_call']:.1f}% / {r['iv_put']:.1f}%</div>
      <div class="ssub">1개월 이내 만기</div>
    </div>
  </div>

  {em_html}{cone_html}

  <!-- GEX 요약 -->
  {_gex_section_warning}
  {_cgr_html}
  {'<div style="margin-bottom:6px;padding:4px 10px;background:#fff8e1;border-left:3px solid #f59e0b;border-radius:3px;font-size:9px;color:#78350f;font-weight:600;">⚠ GEX/Call Wall/Put Wall/Max Pain — 폴백 데이터 기반, 저신뢰. 원자료 확인 필요.</div>' if _gex_low_conf else ''}
  <div class="gex-grid"{_gex_grid_style}>
    <div class="gex-box">
      <div class="gex-lbl">⚡ Net GEX (1개월이내)</div>
      <div class="gex-val {ngb_cls}">{ngb_str}</div>
      <div class="gex-sub">{gex_regime}</div>
      <div class="gex-delta" style="color:{_delta_color};margin-top:5px;font-size:10px;font-weight:600">{_delta_str}</div>
    </div>
    <div class="gex-box">
      <div class="gex-lbl">🔄 Gamma Flip</div>
      <div class="gex-val {gflip_cls}">{gflip_str}</div>
      <div class="gex-sub">{gflip_label}</div>
      {_gflip_dist_html}
    </div>
    <div class="gex-box">
      <div class="gex-lbl">🟢 Call Wall</div>
      <div class="gex-val gex-pos">{cwall_str}</div>
      <div class="gex-sub">{cwall_label}</div>
    </div>
    <div class="gex-box">
      <div class="gex-lbl">🔴 Put Wall</div>
      <div class="gex-val gex-neg">{pwall_str}</div>
      <div class="gex-sub">{pwall_label}</div>
    </div>
  </div>
  {_box_strip_html}
  <div class="gex-note">
    GEX: G-Flip 위(안정)/아래(증폭) | Call Wall(저항) | Put Wall(지지) | BS기반 추정
  </div>

  {zdte_html}

  <!-- GEX by Strike 차트 -->
  <div class="section">
    <div class="section-title">⚡ GEX (Gamma Exposure) by Strike — 현재가±18% · 1개월이내 &nbsp;
      <span style="font-weight:400;font-size:10px;color:#aaa">🟢양수=안정 / 🔴음수=변동성증폭 &nbsp;|&nbsp; 단위: $M</span>
    </div>
    <div style="position:relative;height:220px;">
      <canvas id="chart-{sym}-gex"></canvas>
    </div>
  </div>

  <!-- 만기별 상세 표 -->
  <div class="section">
    <div class="section-title">📋 만기일별 옵션 배팅 상세</div>
    <div class="table-wrap" id="tw-{sym}">
      <table class="exp-table">
        <colgroup>
          <col class="c-date"><col class="c-days"><col class="c-pc">
          <col class="c-iv"><col class="c-em"><col class="c-mp"><col class="c-cmt">
        </colgroup>
        <thead>
          <tr>
            <th>만기일</th>
            <th>잔존</th>
            <th title="마우스 올리면 원본 수량 표시">P/C<br><span style="font-weight:400;font-size:9px;color:#aaa">Vol / OI</span></th>
            <th>IV</th>
            <th>기대변동<br><span style="font-weight:400;font-size:9px;color:#aaa">±% · ±$ · 범위</span></th>
            <th>Max Pain<br><span style="font-weight:400;font-size:9px;color:#aaa">현재가대비</span></th>
            <th>해설</th>
          </tr>
        </thead>
        <tbody>{exp_rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- 전체 캘린더 차트 -->
  <div class="charts-row">
    <div class="chart-box chart-box-full">
      <div class="section-title">📅 전체 캘린더 — 만기일 OI (모든 날짜 · 만기일만 바 표시 · ★표시)</div>
      <div class="tab-row">
        <button class="tbtn active" onclick="switchCalTab('{sym}','oi',this)">OI</button>
        <button class="tbtn" onclick="switchCalTab('{sym}','vol',this)">Volume</button>
      </div>
      <div class="cal-scroll-wrap">
        <div class="cal-inner" id="cal-inner-{sym}-oi">
          <canvas id="chart-{sym}-cal-oi" height="220"></canvas>
        </div>
        <div class="cal-inner" id="cal-inner-{sym}-vol" style="display:none">
          <canvas id="chart-{sym}-cal-vol" height="220"></canvas>
        </div>
      </div>
    </div>
  </div>

  <!-- 스트라이크 차트 -->
  <div class="charts-row">
    <div class="chart-box" style="grid-column:1/-1;">
      <div class="section-title">📊 스트라이크별 OI / Volume / V·C — 현재가±18% (1개월 이내)</div>
      <div class="tab-row">
        <button class="tbtn active" onclick="switchTab('{sym}','oi',this)">OI</button>
        <button class="tbtn" onclick="switchTab('{sym}','vol',this)">Volume</button>
        <button class="tbtn" onclick="switchTab('{sym}','vc',this)">V/C Ratio 🔴UOA</button>
      </div>
      <div style="position:relative;height:240px;">
        <canvas id="chart-{sym}-oi"></canvas>
        <canvas id="chart-{sym}-vol" style="display:none"></canvas>
        <canvas id="chart-{sym}-vc"  style="display:none"></canvas>
      </div>
      <div id="uoa-{sym}" class="uoa-wrap" style="display:none"></div>
    </div>
  </div>

  <!-- 상위 스트라이크 -->
  <div class="tables-row">
    <div class="tbl-box">
      <div class="tbl-title up">🟢 상위 콜 OI (강세 배팅) — 1개월 이내</div>
      <table><thead><tr><th>스트라이크</th><th>OI</th></tr></thead>
      <tbody>{top_c_rows}</tbody></table>
    </div>
    <div class="tbl-box">
      <div class="tbl-title dn">🔴 상위 풋 OI (약세 배팅) — 1개월 이내</div>
      <table><thead><tr><th>스트라이크</th><th>OI</th></tr></thead>
      <tbody>{top_p_rows}</tbody></table>
    </div>
  </div>

</div>"""

    _css = """
body{background:#f0f2f5;color:#222;font-family:'Segoe UI',system-ui,sans-serif;font-size:12px;}
a{color:inherit;}

.top-header{background:#1a237e;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;}
.top-header h1{font-size:16px;font-weight:700;}
.top-header .meta{font-size:11px;color:#aaa;}

.page{max-width:1500px;margin:0 auto;padding:16px;display:flex;flex-direction:column;gap:20px;}

.card{background:#fff;border:1px solid #ddd;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.card-header{padding:14px 20px;background:#fafafa;border-bottom:1px solid #eee;}
.title-row{display:flex;align-items:baseline;gap:10px;}
.sym{font-size:24px;font-weight:800;color:#1a1a2e;}
.lbl{font-size:12px;color:#999;flex:1;}
.price{font-size:22px;font-weight:700;color:#1a5fa8;}
.meta-sub{font-size:9.5px;color:#ccc;margin-top:4px;}

.stats-grid{display:grid;grid-template-columns:repeat(8,1fr);gap:1px;background:#e8e8e8;}
.sbox{padding:10px 14px;background:#fff;}
.slbl{font-size:9px;color:#aaa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}
.sval{font-size:15px;font-weight:700;color:#222;}
.ssub{font-size:8.5px;color:#bbb;margin-top:2px;}
.pc-note{font-size:8.5px;color:#ccc;margin-top:2px;line-height:1.3}
.em-section{padding:10px 20px;background:#f8f9ff;border-top:1px solid #eee;border-bottom:1px solid #eee;}
.em-title{font-size:11px;font-weight:700;color:#555;margin-bottom:6px}
.em-track-wrap{display:flex;align-items:center;gap:8px}
.em-bound{font-size:11px;font-family:monospace;color:#888;width:80px}
.em-bound:last-child{text-align:left}
.em-track{flex:1;height:14px;background:#e8eaf0;border-radius:7px;position:relative}
.em-zone{position:absolute;left:20%;width:60%;height:100%;background:#e8f5e9;border-radius:7px}
.em-cursor{position:absolute;top:-4px;width:6px;height:22px;background:#1565c0;border-radius:3px;transform:translateX(-50%);box-shadow:0 1px 4px rgba(0,0,0,.2)}
.em-hint{font-size:11px;color:#888;margin-top:4px;text-align:center}
.up{color:#1a8a7a;}.dn{color:#d32f2f;}

.section{padding:14px 20px;border-top:1px solid #f0f0f0;}
.section-title{font-size:12px;font-weight:700;color:#555;margin-bottom:10px;}

.table-wrap{overflow:visible;}
.exp-table{width:auto;min-width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed;}
.exp-table col.c-date{width:105px;}
.exp-table col.c-days{width:52px;}
.exp-table col.c-pc  {width:88px;}
.exp-table col.c-iv  {width:50px;}
.exp-table col.c-em  {width:100px;}
.exp-table col.c-mp  {width:86px;}
.exp-table col.c-cmt {width:200px;}

.exp-table thead th{background:#1a1a2e;color:#fff;padding:6px 8px;font-size:10px;
                     text-align:center;position:sticky;top:0;z-index:2;
                     border-right:1px solid #2d2d44;}
.exp-table thead th:first-child{text-align:left;}
.exp-table thead th:last-child{text-align:right;border-right:none;}
.exp-table tbody td{padding:5px 7px;border-bottom:1px solid #f0f0f0;
                     vertical-align:top;border-right:1px solid #f5f5f5;}
.exp-table tbody td:last-child{border-right:none;}
.exp-table tbody td.exp-date{font-weight:600;color:#333;font-family:monospace;font-size:11px;}
.exp-table tbody td.exp-date .wd{display:block;font-family:sans-serif;font-size:9px;
                                   color:#1a5fa8;font-weight:600;margin-top:1px;}
.exp-table tbody td.num{text-align:right;font-variant-numeric:tabular-nums;}
.exp-table tbody tr:hover td{background:#f5f8ff;}
.exp-table tbody tr.row-near{background:#fff5f5;}
.exp-table tbody tr.row-near:hover td{background:#ffe8e8;}
.exp-table tbody tr.row-mid{background:#fffff5;}
.exp-table tbody tr.row-total{background:#f0f4ff;font-size:11px;}
.exp-table tbody tr.row-total td{padding:6px 7px;border-top:2px solid #dde;}

.iv-hi{color:#ef5350;font-weight:700;}
.iv-mid{color:#ff9800;font-weight:600;}
.iv-lo{color:#26a69a;}

.pc-cell{cursor:help;}
.pc-line{display:flex;align-items:center;justify-content:space-between;
          font-size:10.5px;line-height:1.6;}
.pc-lbl{color:#aaa;font-size:9px;}

.em-cell2{text-align:right;}
.em-val{font-size:11.5px;font-weight:700;color:#1a1a2e;}
.em-sub{font-size:9.5px;color:#888;}
.em-range{font-size:9.5px;}
.em-up{color:#1a8a7a;font-weight:600;}
.em-dn{color:#d32f2f;font-weight:600;}

.mp-cell{text-align:right;}
.mp-price{font-size:11.5px;font-weight:700;color:#333;}
.mp-diff{font-size:10px;font-weight:600;}

.comment-cell{font-size:9px;color:#666;line-height:1.5;
               text-align:right;white-space:normal;
               word-break:keep-all;overflow-wrap:break-word;}

.badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;}
.b-red{background:#fdecea;color:#c62828;}
.b-orange{background:#fff3e0;color:#e65100;}
.b-gray{background:#f5f5f5;color:#555;}
.b-light{background:#fafafa;color:#aaa;}

.pc-bar-wrap{width:80px;height:8px;border-radius:4px;overflow:hidden;display:flex;}
.pc-bar-c{background:#26a69a;height:100%;}
.pc-bar-p{background:#ef5350;height:100%;}

.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#eee;border-top:1px solid #eee;}
.chart-box{padding:14px 18px;background:#fff;}
.chart-box-full{grid-column:1/-1;}
.tab-row{display:flex;gap:5px;margin-bottom:8px;}
.tbtn{padding:3px 11px;border:1px solid #ccc;background:#f0f0f0;color:#666;border-radius:3px;cursor:pointer;font-size:11px;}
.tbtn.active{background:#1a5fa8;border-color:#1a5fa8;color:#fff;}

.cal-scroll-wrap{overflow-x:auto;overflow-y:hidden;border:1px solid #eee;border-radius:4px;}
.cal-inner{height:260px;min-width:100%;}

.tables-row{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#eee;border-top:1px solid #eee;}
.tbl-box{padding:12px 18px;background:#fff;}

.section-title{font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:12px;}
.item-label{font-size:12px;color:#94a3b8;}
.item-value{font-size:13px;color:#f1f5f9;font-weight:500;}

.badge{font-size:11px;padding:2px 8px;border-radius:4px;color:white;font-weight:600;display:inline-block;}
.b-long-gamma{background-color:#16a34a;}
.b-short-gamma{background-color:#dc2626;}
.b-warning{background-color:#d97706;}
.b-neutral{background-color:#6b7280;}

.gex-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#334155;border-radius:8px;overflow:hidden;margin-bottom:0;}
.gex-box{padding:14px;background:#1e293b;}
.gex-lbl{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px;}
.gex-val{font-size:16px;font-weight:700;color:#f8fafc;}
.gex-sub{font-size:11px;color:#cbd5e1;margin-top:6px;line-height:1.4;}
.gex-pos{color:#22c55e;}
.gex-neg{color:#ef4444;}
.gex-warn{color:#eab308;}  /* 혼합 신호 */
.gex-neu{color:#94a3b8;}

.uoa-wrap{padding:10px 4px 4px;display:flex;flex-wrap:wrap;gap:6px;}
.uoa-chip{display:inline-flex;flex-direction:column;align-items:center;
           padding:5px 10px;border-radius:5px;font-size:11px;font-weight:700;min-width:70px;}
.uoa-chip .uoa-strike{font-size:10px;font-weight:400;opacity:.8;margin-bottom:1px;}
.uoa-chip .uoa-vc{font-size:13px;font-weight:800;}
.uoa-chip .uoa-type{font-size:9px;opacity:.7;margin-top:1px;}
.uoa-red   {background:#fdecea;color:#c62828;}
.uoa-orange{background:#fff3e0;color:#e65100;}
.uoa-teal  {background:#e0f2f1;color:#00695c;}

.gex-note{font-size:9px;color:#aaa;padding:4px 14px 10px;margin-top:4px;}
/* ③ Gamma Flip 거리 */
.gex-dist{font-size:10.5px;font-weight:600;margin-top:4px;}
/* ① Δ GEX */
.gex-delta{font-size:10px;font-weight:600;margin-top:5px;letter-spacing:.02em;}
/* ⑦ 박스 폭 */
.box-strip{display:flex;align-items:center;gap:8px;padding:7px 14px;
           background:#1a2535;border-top:1px solid #334155;border-radius:0 0 8px 8px;
           font-size:11px;margin-bottom:10px;}
.box-lbl{font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;}
.box-val{font-size:13px;font-weight:700;}
.box-tag{font-size:10px;font-weight:600;padding:1px 6px;border-radius:3px;background:rgba(255,255,255,.08);}
.box-hint{font-size:8.5px;color:#64748b;margin-left:auto;}
"""
    # ─── ① Δ GEX 스냅샷 저장 ────────────────────────────────────
    # ─── IV Rank 이상 감지 (루프 후 집계) ───────────────────────────
    _iv_anomaly = detect_iv_rank_anomaly(_iv_rank_map)
    if _iv_anomaly['anomaly']:
        _ia_banner = (
            f'<div style="background:#fff3e0;border:1px solid #f97316;'
            f'border-radius:6px;padding:8px 14px;margin-bottom:12px;'
            f'font-size:10px;font-weight:600;color:#7c4100;">'
            f'⚠ IV Rank 이상: {", ".join(_iv_anomaly["affected"])} 동시 100%'
            f' — {_iv_anomaly["flag"]}. 소스: REALIZED_VOL_PROXY (옵션 IV 아님). 해석 주의.'
            f'</div>'
        )
        # 배너를 dashboard_summary 앞에 삽입 (변수 교체)
        _dashboard_summary = _ia_banner + _dashboard_summary

    try:
        with open(_SNAP_FILE, 'w') as _sf:
            json.dump(_curr_snap, _sf)
    except Exception:
        pass

    return html_head('Jason Market — 옵션 모니터 (QQQ/SPY/GOOGL)', css=_css, chartjs=True) + f"""
<body>
<div class="top-header">
  <h1>Jason Market — 옵션 모니터 (QQQ / SPY / GOOGL)</h1>
  <div class="meta">업데이트: {timestamp} &nbsp;|&nbsp; 날짜·OI: CBOE = optioncharts.io &nbsp;|&nbsp; 기대변동: ATM스트래들 = barchart 방식</div>
</div>
<div class="page">
{_spx_stale_banner}
{_dashboard_summary}
{cards}
</div>

<script>
const ALL = {data_js};

function switchTab(sym, mode, el) {{
  el.closest('.chart-box').querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('chart-'+sym+'-oi').style.display  = mode==='oi'  ? '' : 'none';
  document.getElementById('chart-'+sym+'-vol').style.display = mode==='vol' ? '' : 'none';
  document.getElementById('chart-'+sym+'-vc').style.display  = mode==='vc'  ? '' : 'none';
  const uoaEl = document.getElementById('uoa-'+sym);
  if (uoaEl) uoaEl.style.display = mode==='vc' ? 'flex' : 'none';
}}

function switchCalTab(sym, mode, el) {{
  el.closest('.chart-box').querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('cal-inner-'+sym+'-oi').style.display  = mode==='oi'  ? '' : 'none';
  document.getElementById('cal-inner-'+sym+'-vol').style.display = mode==='vol' ? '' : 'none';
}}

function makeCalChart(canvasId, wrapperId, cal, mode) {{
  const ctx     = document.getElementById(canvasId);
  const wrapper = document.getElementById(wrapperId);
  if (!ctx || !wrapper) return;

  const dates   = cal.dates;
  const callOI  = cal.call_oi;
  const putOI   = cal.put_oi;
  const callVol = cal.call_vol;
  const putVol  = cal.put_vol;

  const callData = mode === 'oi' ? callOI  : callVol;
  const putData  = mode === 'oi' ? putOI   : putVol;
  const isExp    = dates.map((_,i) => callOI[i] > 0 || putOI[i] > 0);
  const totals   = callData.map((v,i) => v + putData[i]);
  const maxTot   = Math.max(...totals, 1);

  const W = Math.max(dates.length * 10, 900);
  wrapper.style.width = W + 'px';
  ctx.style.width = W + 'px';
  ctx.width = W;

  const wds = ['일','월','화','수','목','금','토'];
  const labels = dates.map((d,i) => {{
    if (!isExp[i]) return '';
    const dt = new Date(d);
    return d.slice(5) + '(' + wds[dt.getUTCDay()] + ')★';
  }});

  const cColors = callData.map((v,i) =>
    isExp[i] ? `rgba(38,166,154,${{0.3 + 0.65*(totals[i]/maxTot)}})` : 'rgba(0,0,0,0)');
  const pColors = putData.map((v,i) =>
    isExp[i] ? `rgba(239,83,80,${{0.3 + 0.65*(totals[i]/maxTot)}})` : 'rgba(0,0,0,0)');

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{label:'콜', data:callData, backgroundColor:cColors, borderWidth:0, borderRadius:2, barPercentage:0.6}},
        {{label:'풋', data:putData,  backgroundColor:pColors, borderWidth:0, borderRadius:2, barPercentage:0.6}},
      ]
    }},
    options: {{
      responsive: false,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{labels:{{color:'#555',font:{{size:11}}}}}},
        tooltip: {{
          filter: item => totals[item.dataIndex] > 0,
          callbacks: {{
            title: items => {{
              const i  = items[0].dataIndex;
              const d  = dates[i];
              const dt = new Date(d);
              const diff = Math.round((dt - new Date()) / 86400000);
              return d + ' (' + wds[dt.getUTCDay()] + ')' +
                (isExp[i] ? '  ★만기  D' + (diff >= 0 ? '-'+diff : '+'+Math.abs(diff)) : '');
            }},
            label: c => c.dataset.label + ': ' + c.raw.toLocaleString()
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{
            color: '#1a5fa8',
            font:  {{size:8, weight:'bold'}},
            maxRotation: 90,
            autoSkip: false,
          }},
          grid: {{color:'#f0f0f0'}}
        }},
        y: {{
          ticks: {{
            color: '#888', font: {{size:10}},
            callback: v => v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v
          }},
          grid: {{color:'#f0f0f0'}}
        }}
      }}
    }}
  }});
}}

function makeStrikeChart(canvasId, d, curr, maxPain) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  const isVol    = canvasId.endsWith('-vol');
  const callData = isVol ? d.call_vol : d.call_oi;
  const putData  = isVol ? d.put_vol  : d.put_oi;

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: d.strikes.map(l=>'$'+l.toFixed(0)),
      datasets: [
        {{label:'콜', data:callData,           backgroundColor:'rgba(38,166,154,0.75)',borderWidth:0}},
        {{label:'풋', data:putData.map(v=>-v), backgroundColor:'rgba(239,83,80,0.75)', borderWidth:0}},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{labels:{{color:'#555',font:{{size:11}}}}}},
        tooltip: {{
          callbacks: {{
            label: ctx => ctx.dataset.label+': '+Math.abs(ctx.raw).toLocaleString()
          }}
        }}
      }},
      scales: {{
        x: {{ticks:{{color:'#888',font:{{size:9}},maxRotation:45}},grid:{{color:'#f5f5f5'}}}},
        y: {{ticks:{{color:'#888',font:{{size:10}},
               callback:v=>Math.abs(v)>=1e3?(Math.abs(v)/1e3).toFixed(0)+'K':Math.abs(v)}},
             grid:{{color:'#f0f0f0'}}}}
      }}
    }}
  }});
}}

function makeGexChart(canvasId, gex, curr) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx || !gex || !gex.strikes || !gex.strikes.length) return;

  const labels   = gex.strikes.map(s => '$' + s.toFixed(0));
  const netData  = gex.net_gex;
  const callData = gex.call_gex;
  const putData  = gex.put_gex.map(v => -v);

  const flip  = gex.gamma_flip;
  const cwall = gex.call_wall;
  const pwall = gex.put_wall;
  const barColors = netData.map((v, i) => {{
    const s = gex.strikes[i];
    if (Math.abs(s - flip)  < 0.5) return 'rgba(255,165,0,0.95)';
    if (Math.abs(s - cwall) < 0.5) return 'rgba(0,230,180,1.0)';
    if (Math.abs(s - pwall) < 0.5) return 'rgba(255,80,80,1.0)';
    return v >= 0 ? 'rgba(38,166,154,0.75)' : 'rgba(239,83,80,0.75)';
  }});

  const currIdx = gex.strikes.reduce((bi, s, i) =>
    Math.abs(s - curr) < Math.abs(gex.strikes[bi] - curr) ? i : bi, 0);

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{
          label: 'Net GEX ($M)',
          data: netData,
          backgroundColor: barColors,
          borderWidth: 0,
          borderRadius: 2,
        }},
        {{
          label: '콜 GEX ($M)',
          data: callData,
          backgroundColor: 'rgba(38,166,154,0.25)',
          borderWidth: 0,
          borderRadius: 1,
          hidden: true,
        }},
        {{
          label: '풋 GEX ($M)',
          data: putData,
          backgroundColor: 'rgba(239,83,80,0.25)',
          borderWidth: 0,
          borderRadius: 1,
          hidden: true,
        }},
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{
          labels: {{color:'#ccc', font:{{size:11}}}},
        }},
        tooltip: {{
          callbacks: {{
            title: items => {{
              const s = gex.strikes[items[0].dataIndex];
              const tag = Math.abs(s - flip)  < 0.5 ? ' 🔄 Gamma Flip' :
                          Math.abs(s - cwall) < 0.5 ? ' 🟢 Call Wall'  :
                          Math.abs(s - pwall) < 0.5 ? ' 🔴 Put Wall'   : '';
              return '$' + s.toFixed(2) + tag;
            }},
            label: c => c.dataset.label + ': $' + Math.abs(c.raw).toFixed(1) + 'M'
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{
            color: ctx2 => {{
              const s = gex.strikes[ctx2.index];
              return Math.abs(s - curr) < 0.5 ? '#e65100' : '#888';
            }},
            font: {{size:9}},
            maxRotation: 45,
          }},
          grid: {{color:'#f0f0f0'}}
        }},
        y: {{
          ticks: {{
            color: '#888',
            font: {{size:10}},
            callback: v => (v >= 0 ? '+' : '') + v.toFixed(0) + 'M'
          }},
          grid: {{color:'#f0f0f0'}},
          border: {{color:'#eee'}}
        }}
      }}
    }}
  }});
}}

function makeVCChart(canvasId, sym, d) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx || !d.strikes || !d.strikes.length) return;

  const callVC = d.call_vc || d.strikes.map(()=>0);
  const putVC  = d.put_vc  || d.strikes.map(()=>0);

  // 색상: V/C ≥1.0=빨강(UOA), 0.5~1.0=주황(관찰), <0.5=teal(정상)
  function vcColor(v, alpha) {{
    if (v >= 1.0) return `rgba(198,40,40,${{alpha}})`;
    if (v >= 0.5) return `rgba(230,81,0,${{alpha}})`;
    return `rgba(0,131,143,${{alpha}})`;
  }}
  const callColors = callVC.map(v => vcColor(v, 0.85));
  const putColors  = putVC.map(v  => vcColor(v, 0.85));

  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: d.strikes.map(s=>'$'+s.toFixed(0)),
      datasets: [
        {{label:'콜 V/C', data:callVC,           backgroundColor:callColors, borderWidth:0, borderRadius:2}},
        {{label:'풋 V/C', data:putVC.map(v=>-v), backgroundColor:putColors,  borderWidth:0, borderRadius:2}},
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{
        legend: {{labels:{{color:'#555',font:{{size:11}}}}}},
        tooltip: {{
          callbacks: {{
            label: c => {{
              const v = Math.abs(c.raw);
              const tag = v>=1.0?' 🔴UOA': v>=0.5?' 🟠관찰':' 🟢정상';
              return c.dataset.label+': '+v.toFixed(2)+tag;
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ticks:{{color:'#888',font:{{size:9}},maxRotation:45}},grid:{{color:'#f5f5f5'}}}},
        y: {{
          ticks:{{color:'#888',font:{{size:10}},
                  callback:v=>Math.abs(v).toFixed(2)}},
          grid:{{color:'#f0f0f0'}},
          title:{{display:true,text:'V/C Ratio (Volume÷OI)',color:'#aaa',font:{{size:10}}}}
        }}
      }}
    }}
  }});

  // UOA 요약 칩 생성
  const uoaEl = document.getElementById('uoa-'+sym);
  if (!uoaEl) return;
  const items = [];
  d.strikes.forEach((s,i) => {{
    if (callVC[i] >= 0.5) items.push({{strike:s, vc:callVC[i], type:'콜'}});
    if (putVC[i]  >= 0.5) items.push({{strike:s, vc:putVC[i],  type:'풋'}});
  }});
  items.sort((a,b)=>b.vc-a.vc);
  const top = items.slice(0,12);
  if (top.length === 0) {{
    uoaEl.innerHTML = '<span style="color:#aaa;font-size:11px;padding:4px">V/C ≥ 0.5 스트라이크 없음</span>';
    return;
  }}
  uoaEl.innerHTML = '<span style="font-size:10px;color:#aaa;margin-right:6px;align-self:center">🔍 UOA 상위:</span>' +
    top.map(item => {{
      const cls = item.vc>=1.0?'uoa-red':item.vc>=0.5?'uoa-orange':'uoa-teal';
      const mark = item.vc>=1.0?'🔴':item.vc>=0.5?'🟠':'🟢';
      return `<span class="uoa-chip ${{cls}}">
        <span class="uoa-strike">${{mark}} ${{item.strike.toFixed(0)}}</span>
        <span class="uoa-vc">${{item.vc.toFixed(2)}}</span>
        <span class="uoa-type">${{item.type}}</span>
      </span>`;
    }}).join('');
}}

function makePredictionCone(canvasId, curr, coneData) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx || !coneData || coneData.length < 2) return;

  // Sort by DTE ascending
  const pts = [...coneData].sort((a, b) => a.days - b.days);
  // Add current price as day=0 anchor
  const labels = [0, ...pts.map(p => p.days)];
  const uppers = [curr, ...pts.map(p => p.upper)];
  const lowers = [curr, ...pts.map(p => p.lower)];
  const currLine = labels.map(() => curr);

  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: labels.map(d => d === 0 ? '현재' : d + 'D'),
      datasets: [
        {{
          label: '상단 (기대 상방)',
          data: uppers,
          borderColor: 'rgba(38,166,154,0.9)',
          backgroundColor: 'rgba(38,166,154,0.12)',
          fill: '+1',
          tension: 0.35,
          pointRadius: 3,
          borderWidth: 1.5,
        }},
        {{
          label: '하단 (기대 하방)',
          data: lowers,
          borderColor: 'rgba(239,83,80,0.9)',
          backgroundColor: 'rgba(239,83,80,0.05)',
          fill: false,
          tension: 0.35,
          pointRadius: 3,
          borderWidth: 1.5,
        }},
        {{
          label: '현재가',
          data: currLine,
          borderColor: '#f97316',
          borderDash: [4, 3],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
        }},
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{
          labels: {{color: '#888', font: {{size: 10}}}},
          position: 'right',
        }},
        tooltip: {{
          callbacks: {{
            label: c => c.dataset.label + ': $' + c.raw.toFixed(2)
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{color: '#888', font: {{size: 10}}}},
          grid: {{color: '#f5f5f5'}},
        }},
        y: {{
          ticks: {{
            color: '#888',
            font: {{size: 10}},
            callback: v => '$' + v.toFixed(0)
          }},
          grid: {{color: '#f0f0f0'}},
        }}
      }}
    }}
  }});
}}

ALL.forEach(r => {{
  if (!r) return;
  makeCalChart('chart-'+r.sym+'-cal-oi',  'cal-inner-'+r.sym+'-oi',  r.cal_chart, 'oi');
  makeCalChart('chart-'+r.sym+'-cal-vol', 'cal-inner-'+r.sym+'-vol', r.cal_chart, 'vol');
  makeStrikeChart('chart-'+r.sym+'-oi',  r.chart, r.curr, r.max_pain);
  makeStrikeChart('chart-'+r.sym+'-vol', r.chart, r.curr, r.max_pain);
  makeGexChart('chart-'+r.sym+'-gex', r.gex, r.curr);
  makeVCChart('chart-'+r.sym+'-vc', r.sym, r.chart);
  if (r.cone_data && r.cone_data.length >= 2) {{
    makePredictionCone('chart-'+r.sym+'-cone', r.curr, r.cone_data);
  }}
}});

</script>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""


__all__ = ['generate_html']
