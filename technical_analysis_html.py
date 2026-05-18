"""기술분석 HTML 렌더링 모듈
차트, 지표 시각화, AI 분석 결과 표시"""

import json
import tempfile
import webbrowser
from datetime import datetime

from jm_lib.html_styles import html_head
from technical_analysis_indicators import (
    bb_label, momentum_label, rsi_label, stoch_label,
    obv_label, pivot_position_label,
)


def generate_html(results, ai_text=""):
    """기술분석 결과를 HTML 대시보드로 생성 및 브라우저 표시

    Args:
        results: analyze_asset() 결과 리스트
        ai_text: AI 분석 텍스트 (선택)
    """
    if not results:
        return

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ═══ 포맷팅 함수들 ═══

    def price_fmt(r):
        """티커별 가격 포맷"""
        t, v = r['ticker'], r['curr']
        if t == 'BTC-USD':
            return f"${v:,.0f}"
        if t in ('GC=F', 'BZ=F', 'CL=F'):
            return f"${v:,.1f}"
        if t in ('YM=F', 'ES=F', 'NQ=F', 'RTY=F'):
            return f"{v:,.1f}"
        if t.endswith('.KS'):
            return f"₩{v:,.0f}"
        if t == 'USDKRW=X':
            return f"₩{v:,.1f}"
        if t in ('^TNX', '^VIX', '^KS11'):
            return f"{v:,.2f}"
        return f"${v:,.2f}"

    def c_chg(p):
        """변동률 색상"""
        return '#00838f' if p >= 0 else '#c62828'

    def c_rsi(v):
        """RSI 색상"""
        if v is None:
            return '#888'
        return '#c62828' if v >= 70 else '#00838f' if v <= 30 else '#1565c0'

    def c_bb(v):
        """볼린저밴드 색상"""
        if v is None:
            return '#888'
        return '#c62828' if v >= 85 else '#00838f' if v <= 15 else '#1565c0'

    def c_obv(v):
        """OBV 추세 색상"""
        return '#00838f' if v == 'up' else '#c62828' if v == 'down' else '#90a4ae'

    def ma_badge(curr, ma, lbl):
        """이동평균 배지"""
        if not ma:
            return ''
        pct = (curr - ma) / ma * 100
        col = '#00838f' if curr > ma else '#c62828'
        return f'<span class="badge" style="background:{col}">{lbl} {pct:+.1f}%</span>'

    def pivot_row(pivot, curr):
        """주간 피봇 포인트 HTML"""
        if not pivot:
            return ''

        def pc(k, v):
            col = '#00838f' if v < curr else '#c62828' if v > curr else '#e65100'
            return f'<span class="pvt" style="border-color:{col};color:{col}">{k}<br><small>{v:,.2f}</small></span>'

        return f"""<div class="pivot-row">
          {pc('S2',pivot['S2'])}{pc('S1',pivot['S1'])}{pc('P',pivot['P'])}{pc('R1',pivot['R1'])}{pc('R2',pivot['R2'])}
        </div><div class="pivot-pos">{pivot_position_label(pivot, curr)}</div>"""

    def vol_profile_bars(vp, curr, poc_price=None):
        """매물대 시각화"""
        if not vp:
            return ''
        bars = ""
        for b in reversed(vp):
            is_curr = abs(b['price'] - curr) / curr < 0.02
            is_poc = (poc_price is not None and
                     abs(b['price'] - poc_price) / max(poc_price, 0.001) < 0.001)
            if is_curr:
                col = '#e67e22'
            elif is_poc:
                col = '#e65100'
            else:
                col = '#b0bec5'
            bars += f"""<div class="vp-row">
              <span class="vp-price">{b['price']:,.2f}</span>
              <div class="vp-bar-wrap"><div class="vp-bar" style="width:{b['pct']}%;background:{col}"></div></div>
            </div>"""
        return f'<div class="vp-container">{bars}</div>'

    # ═══ 차트 데이터 및 카드 생성 ═══

    all_chart_data = {r['name']: r['chart'] for r in results}

    def _macro_burden(r):
        if r['ticker'] == 'USDKRW=X':
            return '환율 부담 / 원화 약세 압력' if r['pct'] > 0 else '환율 부담 완화'
        if r['ticker'] == '^TNX':
            return '금리 부담' if r['pct'] > 0 else '금리 부담 완화'
        if r['ticker'] == '^VIX':
            return '변동성 부담' if r['pct'] > 0 else '변동성 부담 완화'
        return ''

    def _summary_lines():
        warned = [r for r in results if r.get('data_warnings')]
        clean = [r for r in results if not r.get('data_warnings')]
        macro_types = {'macro_fx', 'macro_rate', 'volatility_index', 'cash_like'}
        top_hi_pool = [r for r in clean if r.get('asset_type') not in macro_types]
        top_lo_pool = [
            r for r in clean
            if r.get('asset_type') != 'cash_like'
            and bb_label(r.get('pct_b')) in ('중립 하단', '하단권', '하단 이탈')
        ]
        top_hi = sorted(top_hi_pool, key=lambda x: (x.get('pct_b') or 50), reverse=True)[:5]
        top_lo = sorted(top_lo_pool, key=lambda x: (x.get('pct_b') or 50))[:5]
        top_atr = sorted(clean, key=lambda x: (x.get('atr_pct') or 0), reverse=True)[:5]
        macro = [r for r in results if r['ticker'] in ('USDKRW=X', '^TNX', '^VIX')]
        limited = [r for r in results if r.get('asset_type') == 'cash_like']
        return {
            'warnings': ', '.join(r['name'] for r in warned) + ' — 원천 가격 이상으로 기술지표 해석 제외' if warned else '없음',
            'top_hi': ', '.join(f"{r['name']} {bb_label(r.get('pct_b'))}" for r in top_hi) or '없음',
            'top_lo': ', '.join(f"{r['name']} {bb_label(r.get('pct_b'))}" for r in top_lo) or '뚜렷한 침체권 없음',
            'top_atr': ', '.join(f"{r['name']} {r.get('atr_pct'):.1f}%" for r in top_atr if r.get('atr_pct') is not None) or '없음',
            'macro': ', '.join(f"{r['ticker']} {_macro_burden(r)}" for r in macro) or '없음',
            'limited': ', '.join(r['name'] for r in limited) or '없음',
        }

    summary = _summary_lines()
    summary_html = f"""
<div class="summary-box">
  <div class="summary-title">요약</div>
  <div>데이터 경고: {summary['warnings']}</div>
  <div>과열/상단권 TOP 5: {summary['top_hi']}</div>
  <div>하방/침체 TOP 5: {summary['top_lo']}</div>
  <div>변동성 ATR 상위 TOP 5: {summary['top_atr']}</div>
  <div>매크로 부담: {summary['macro']}</div>
  <div>기술지표 해석 제한: {summary['limited']}</div>
</div>"""

    cards = ""
    for idx, r in enumerate(results):
        cid = f"chart_{idx}"
        rsi = r['rsi'] or 50
        pct_b = max(0, min(100, r['pct_b'] or 50))
        sk = r['stoch_k'] or 50
        sd = r['stoch_d'] or 50

        score = r.get('score', {})
        score_color = score.get('color', '#90a4ae')
        score_label = score.get('label', '중립')
        score_total = score.get('total', 0)
        bar_pct = score.get('bar_pct', 50)
        trend_sc = score.get('trend_score', 0)
        mom_sc = score.get('momentum_score', 0)
        vol_sc = score.get('volume_score', 0)
        obv_div = r.get('obv_div')
        div_warn = (f'<span style="color:#e65100;font-weight:600">{obv_div}</span>'
                   if obv_div and r.get('volume_reliable') else '')
        asset_type = r.get('asset_type', 'equity_or_etf')
        is_cash_like = asset_type == 'cash_like'
        is_data_limited = bool(r.get('data_warnings'))
        macd_lbl = momentum_label(r.get('macd'), r.get('macd_sig'), r.get('macd_hist'))
        obv_lbl = obv_label(r.get('obv_trend'), r.get('volume_reliable'))
        warning_html = ''.join(
            f'<div class="data-warn">⚠ {w}</div>' for w in r.get('data_warnings', [])
        )
        macro_note = _macro_burden(r)
        macro_html = f'<div class="macro-note">{macro_note}</div>' if macro_note else ''

        # ADX 해석
        adx_val = r.get('adx_val')
        plus_di = r.get('plus_di')
        minus_di = r.get('minus_di')
        if adx_val is not None:
            if adx_val >= 40:
                adx_lbl = '매우강한추세'
            elif adx_val >= 25:
                adx_lbl = '강한추세'
            elif adx_val >= 20:
                adx_lbl = '추세형성중'
            else:
                adx_lbl = '추세없음'
            di_lbl = '상승추세' if (plus_di or 0) > (minus_di or 0) else '하락추세'
            adx_str = f"{adx_val:.1f} ({adx_lbl} / {di_lbl})"
        else:
            adx_str = 'N/A'

        poc_fmt = f"{r['poc_price']:,.2f}" if r.get('poc_price') else 'N/A'

        if is_data_limited:
            score_color = '#90a4ae'
            score_label = '신뢰 제한'
            score_total = 0
            bar_pct = 50
            trend_sc = mom_sc = vol_sc = 0
            indicator_html = """
      <div class="limit-box">
        기술지표: 신뢰 제한 — 원천 가격 데이터 이상으로 RSI/MACD/스토캐스틱 해석 제외
      </div>
      <div class="row3">
        <div class="mini-box">
          <div class="mini-title">MACD</div>
          <div class="mini-val">N/A</div>
        </div>
        <div class="mini-box">
          <div class="mini-title">OBV 추세</div>
          <div class="mini-val">N/A</div>
        </div>
        <div class="mini-box">
          <div class="mini-title">피봇위치</div>
          <div class="mini-val">N/A</div>
        </div>
      </div>"""
            pivot_html = '<div class="pivot-pos">N/A</div>'
        elif is_cash_like:
            indicator_html = f"""
      <div class="limit-box">
        기술지표: 해석 제한 — 현금성/금리형 상품은 RSI/MACD 과열 판단 부적합
      </div>
      <div class="row3">
        <div class="mini-box">
          <div class="mini-title">ATR (변동성)</div>
          <div class="mini-val">{f"{r['atr_pct']:.2f}%" if r['atr_pct'] else 'N/A'}</div>
        </div>
        <div class="mini-box">
          <div class="mini-title">OBV 추세</div>
          <div class="mini-val">N/A — 거래량 신뢰도 낮음</div>
        </div>
        <div class="mini-box">
          <div class="mini-title">해석 범위</div>
          <div class="mini-val" style="font-size:11px;color:#555">가격 안정성 중심 확인</div>
        </div>
      </div>"""
            pivot_html = '<div class="pivot-pos">N/A — 현금성/금리형 상품은 피봇 해석 부적합</div>'
        else:
            indicator_html = f"""
      <!-- RSI -->
      <div class="ind-label">RSI <b style="color:{c_rsi(r['rsi'])}">{f"{r['rsi']:.1f}" if r['rsi'] else 'N/A'} {rsi_label(r.get('rsi'), asset_type)}</b></div>
      <div class="track"><div class="zone z-buy" style="left:0;width:30%"></div><div class="zone z-sell" style="left:70%;width:30%"></div><div class="needle" style="left:{rsi}%;background:{c_rsi(r['rsi'])}"></div><span class="tick" style="left:30%">30</span><span class="tick" style="left:70%">70</span></div>

      <!-- 스토캐스틱 -->
      <div class="ind-label">스토캐스틱 <b style="color:{c_rsi(sk)}">%K {sk:.1f} {stoch_label(r.get('stoch_k'), asset_type)}</b> / <b style="color:#aaa">%D {sd:.1f}</b></div>
      <div class="track"><div class="zone z-buy" style="left:0;width:20%"></div><div class="zone z-sell" style="left:80%;width:20%"></div><div class="needle" style="left:{max(0,min(100,sk))}%;background:{c_rsi(sk)}"></div><div class="needle2" style="left:{max(0,min(100,sd))}%"></div><span class="tick" style="left:20%">20</span><span class="tick" style="left:80%">80</span></div>

      <!-- 볼린저 밴드 -->
      <div class="ind-label">볼린저밴드 <b style="color:{c_bb(r.get('pct_b'))}">{bb_label(r.get('pct_b'))} ({r['pct_b']:.0f}%)</b></div>
      <div class="bb-track"><div class="bb-fill" style="width:{pct_b}%;background:{c_bb(r.get('pct_b'))}"></div></div>
      <div class="bb-lbl"><span>하단권</span><span>중간</span><span>상단권</span></div>

      <!-- MACD -->
      <div class="ind-label">MACD <b style="color:{'#00838f' if r['macd']>r['macd_sig'] else '#c62828' if r['macd']<r['macd_sig'] else '#90a4ae'}">{macd_lbl}</b> <small style="color:#888">히스토그램 {r['macd_hist']:+.4f}</small></div>
      <div class="macd-bar"><div style="width:{min(100,abs(r['macd_hist'])/(abs(r['macd_hist'])+1e-9)*100):.0f}%;height:100%;background:{'#00838f' if r['macd']>r['macd_sig'] else '#c62828' if r['macd']<r['macd_sig'] else '#90a4ae'};border-radius:3px;opacity:0.8"></div></div>

      <!-- ATR / OBV / ADX -->
      <div class="row3">
        <div class="mini-box">
          <div class="mini-title">ATR (변동성)</div>
          <div class="mini-val">{f"{r['atr_pct']:.2f}%" if r['atr_pct'] else 'N/A'} <small style="color:#888">일일리스크</small></div>
        </div>
        <div class="mini-box">
          <div class="mini-title">OBV 추세</div>
          <div class="mini-val" style="color:{c_obv(r['obv_trend'])}">{obv_lbl}</div>
        </div>
        <div class="mini-box">
          <div class="mini-title">ADX (추세강도)</div>
          <div class="mini-val" style="font-size:11px;color:#333">{adx_str}</div>
        </div>
      </div>"""
            pivot_html = pivot_row(r['pivot'], r['curr'])

        cards += f"""
    <div class="card">
      <div class="card-header">
        <span class="aname">{r['name']}</span>
        <span class="tbadge">{r['ticker']}</span>
      </div>
      <div class="price-row">
        <span class="price">{price_fmt(r)}</span>
        <span style="color:{c_chg(r['pct'])};font-weight:600">{r['pct']:+.2f}% {'▲' if r['pct']>=0 else '▼'}</span>
      </div>
      {warning_html}
      {macro_html}

      <!-- 종합신호 스코어 바 -->
      <div class="score-section">
        <div class="score-label">종합신호 <strong style="color:{score_color}">{score_label}</strong> <small>({score_total:+d}점)</small></div>
        <div class="score-bar-wrap">
          <div class="score-bar-fill" style="width:{bar_pct}%;background:{score_color}"></div>
        </div>
        <div class="score-details">
          <span>추세 {trend_sc:+d}</span>
          <span>모멘텀 {mom_sc:+d}</span>
          <span>거래량 {vol_sc:+d}</span>
          {div_warn}
        </div>
      </div>

      <!-- 가격 차트 + 이동평균 -->
      <div class="chart-wrap">
        <canvas id="{cid}_price" height="140"></canvas>
      </div>
      <div class="ma-legend">
        <span style="color:#333">━ MA5</span>
        <span style="color:#e67e22">━ MA20</span>
        <span style="color:#e74c3c">━ MA60</span>
        <span style="color:#9b59b6">━ MA120</span>
        <span style="color:#3498db">━ MA200</span>
      </div>

      <!-- 거래량 차트 -->
      <div style="height:50px;margin-bottom:8px">
        <canvas id="{cid}_vol" height="50"></canvas>
      </div>

      <!-- 매물대 (Volume Profile) -->
      <div class="section-title">📊 매물대 — POC: {poc_fmt} (최다거래 가격)</div>
      {vol_profile_bars(r['vol_profile'], r['curr'], r.get('poc_price'))}

      <!-- 이동평균 뱃지 -->
      <div class="ma-row">
        {ma_badge(r['curr'],r['ma5'],'MA5')}
        {ma_badge(r['curr'],r['ma20'],'MA20')}
        {ma_badge(r['curr'],r['ma60'],'MA60')}
        {ma_badge(r['curr'],r['ma120'],'MA120')}
        {ma_badge(r['curr'],r['ma200'],'MA200')}
      </div>

      {indicator_html}

      <!-- 주간 피봇 포인트 -->
      <div class="section-title">📌 주간 피봇 포인트</div>
      {pivot_html}
    </div>"""

    ai_section = ""
    if ai_text:
        ai_section = f"""<div class="ai-box">
      <div class="ai-title">🤖 AI 기술분석 해석 <span style="font-size:12px;font-weight:400;color:#aaa">(Claude Haiku)</span></div>
      <div class="ai-body">{ai_text.replace(chr(10),'<br>')}</div>
    </div>"""

    # ═══ 텍스트 요약 생성 ═══

    def _ma_status(r):
        parts = []
        for p, k in [(5, 'ma5'), (20, 'ma20'), (60, 'ma60'), (120, 'ma120'), (200, 'ma200')]:
            if r[k]:
                parts.append(f"MA{p}{'위' if r['curr']>r[k] else '아래'}")
        return ' '.join(parts) if parts else '정보없음'

    def _pivot_text(pv):
        if not pv:
            return '없음'
        return f"S2={pv['S2']:,.2f} / S1={pv['S1']:,.2f} / P={pv['P']:,.2f} / R1={pv['R1']:,.2f} / R2={pv['R2']:,.2f}"

    text_lines = [
        f"=== Jason Market 기술분석 보고서 ===",
        f"기준시각: {ts}",
        "",
        "[요약]",
        f"- 데이터 경고: {summary['warnings']}",
        f"- 과열/상단권 TOP 5: {summary['top_hi']}",
        f"- 하방/침체 TOP 5: {summary['top_lo']}",
        f"- 변동성 ATR 상위 TOP 5: {summary['top_atr']}",
        f"- 매크로 부담: {summary['macro']}",
        f"- 기술지표 해석 제한: {summary['limited']}",
        "",
    ]
    for r in results:
        asset_type = r.get('asset_type', 'equity_or_etf')
        rsi_lbl = rsi_label(r.get('rsi'), asset_type)
        stk_lbl = stoch_label(r.get('stoch_k'), asset_type)
        bb_lbl = bb_label(r.get('pct_b'))
        macd_lbl = momentum_label(r.get('macd'), r.get('macd_sig'), r.get('macd_hist'))
        obv_lbl = obv_label(r.get('obv_trend'), r.get('volume_reliable'))
        rsi_s = f"{r['rsi']:.1f}" if r['rsi'] else 'N/A'
        sk_s = f"{r['stoch_k']:.0f}" if r['stoch_k'] else 'N/A'
        sd_s = f"{r['stoch_d']:.0f}" if r['stoch_d'] else 'N/A'
        atr_s = f"{r['atr_pct']:.2f}%" if r['atr_pct'] else 'N/A'
        warn_s = '; '.join(r.get('data_warnings', [])) or '없음'
        if r.get('data_warnings'):
            text_lines += [
                f"[{r['name']} / {r['ticker']}]",
                f"현재가: {price_fmt(r)}  등락: {r['pct']:+.2f}%",
                f"데이터 상태: {warn_s}",
                "기술지표: 신뢰 제한 — 원천 가격 데이터 이상으로 RSI/MACD/스토캐스틱 해석 제외",
                "피봇위치: N/A",
                "",
            ]
            continue
        if asset_type == 'cash_like':
            text_lines += [
                f"[{r['name']} / {r['ticker']}]",
                f"현재가: {price_fmt(r)}  등락: {r['pct']:+.2f}%",
                f"데이터 경고: {warn_s}",
                "기술지표: 해석 제한 — 현금성/금리형 상품은 RSI/MACD 과열 판단 부적합",
                f"ATR(변동성): {atr_s}",
                "피봇포인트: 해석 제한",
                "피봇위치: N/A — 현금성/금리형 상품은 피봇 해석 부적합",
                "",
            ]
            continue
        text_lines += [
            f"[{r['name']} / {r['ticker']}]",
            f"현재가: {price_fmt(r)}  등락: {r['pct']:+.2f}%",
            f"데이터 경고: {warn_s}",
            f"RSI: {rsi_s} → {rsi_lbl}",
            f"스토캐스틱: %K={sk_s} / %D={sd_s} → {stk_lbl}",
            f"볼린저밴드: {r['pct_b']:.0f}% → {bb_lbl}",
            f"MACD: {macd_lbl}  (히스토그램 {r['macd_hist']:+.4f})",
            f"ATR(변동성): {atr_s}",
            f"OBV: {obv_lbl}",
            f"이동평균: {_ma_status(r)}",
            f"피봇포인트: {_pivot_text(r['pivot'])}",
            f"피봇위치: {pivot_position_label(r.get('pivot'), r.get('curr'))}",
            "",
        ]
    if ai_text:
        text_lines += ["=== Claude AI 분석 ===", ai_text, ""]
    text_lines.append("※ 이 보고서는 투자 참고용이며 매매 결정은 본인 책임입니다.")
    plain_text = "\n".join(text_lines)

    chart_js = json.dumps(all_chart_data, ensure_ascii=False)
    plain_text_js = json.dumps(plain_text, ensure_ascii=False)

    # ═══ HTML 생성 ═══

    _css = """
body{background:#f5f6f8;color:#222;font-family:'Segoe UI',Arial,sans-serif;padding:20px}
h1{font-size:19px;font-weight:700;color:#1a237e;margin-bottom:3px}
.ts{font-size:12px;color:#888;margin-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.card{background:#fff;border-radius:10px;padding:18px;border:1px solid #dde3f0;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.aname{font-size:15px;font-weight:700;color:#1a237e}
.tbadge{font-size:11px;background:#eef1f8;color:#555;padding:2px 8px;border-radius:4px}
.price-row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}
.price{font-size:22px;font-weight:700;color:#111}
.chart-wrap{margin-bottom:4px}
.ma-legend{display:flex;gap:10px;font-size:10px;margin-bottom:6px;flex-wrap:wrap}
.section-title{font-size:11px;color:#999;margin:10px 0 5px;text-transform:uppercase;letter-spacing:.5px}
.ma-row{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0}
.badge{font-size:11px;color:#fff;padding:2px 7px;border-radius:4px}
.ind-label{font-size:12px;color:#555;margin:10px 0 4px}
.track{position:relative;height:11px;background:#e8eaf0;border-radius:6px;margin-bottom:14px}
.zone{position:absolute;height:100%;opacity:.25;border-radius:6px}
.z-buy{background:#00838f}
.z-sell{background:#c62828}
.needle{position:absolute;top:-3px;width:4px;height:17px;border-radius:2px;transform:translateX(-50%);box-shadow:0 0 4px rgba(0,0,0,.2)}
.needle2{position:absolute;top:0;width:2px;height:100%;background:#e67e22;opacity:.8;transform:translateX(-50%)}
.tick{position:absolute;top:13px;font-size:10px;color:#aaa;transform:translateX(-50%)}
.bb-track{height:9px;background:#e8eaf0;border-radius:5px;overflow:hidden;margin-bottom:2px}
.bb-fill{height:100%;border-radius:5px}
.bb-lbl{display:flex;justify-content:space-between;font-size:10px;color:#aaa;margin-bottom:6px}
.macd-bar{height:8px;background:#e8eaf0;border-radius:4px;overflow:hidden;margin-top:5px;margin-bottom:10px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}
.score-section{margin:8px 0}
.score-label{font-size:12px;color:#555;margin-bottom:4px}
.score-bar-wrap{height:8px;background:#e8eaf0;border-radius:5px;overflow:hidden;margin-bottom:4px}
.score-bar-fill{height:100%;border-radius:5px;transition:width 0.3s}
.score-details{display:flex;gap:10px;font-size:11px;color:#888}
.mini-box{background:#f0f2f8;border-radius:7px;padding:8px 10px}
.mini-title{font-size:10px;color:#999;margin-bottom:3px}
.mini-val{font-size:14px;font-weight:600;color:#333}
.vp-container{margin-bottom:6px}
.vp-row{display:flex;align-items:center;gap:6px;margin-bottom:2px}
.vp-price{font-size:10px;color:#aaa;width:58px;text-align:right;flex-shrink:0}
.vp-bar-wrap{flex:1;height:8px;background:#e8eaf0;border-radius:3px;overflow:hidden}
.vp-bar{height:100%;border-radius:3px;opacity:.85}
.pivot-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.pvt{font-size:11px;border:1px solid;border-radius:5px;padding:3px 8px;text-align:center;line-height:1.5}
.pvt small{font-size:10px;display:block}
.pivot-pos{font-size:11px;color:#555;margin:3px 0 6px}
.summary-box{background:#fff;border:1px solid #dde3f0;border-radius:8px;padding:14px 16px;margin-bottom:16px;line-height:1.7;font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,.05)}
.summary-title{font-size:14px;font-weight:700;color:#1a237e;margin-bottom:5px}
.data-warn{font-size:11px;color:#c62828;background:#fff5f5;border-left:3px solid #c62828;padding:4px 8px;margin:3px 0;border-radius:3px}
.macro-note{font-size:11px;color:#7c4100;background:#fff8e1;border-left:3px solid #e65100;padding:4px 8px;margin:3px 0;border-radius:3px}
.limit-box{font-size:12px;color:#555;background:#f8f9fa;border-left:3px solid #90a4ae;padding:8px 10px;margin:10px 0;border-radius:4px}
.copy-bar{display:flex;align-items:center;gap:10px;margin-bottom:18px;padding:12px 16px;background:#fff;border-radius:8px;border:1px solid #dde3f0;flex-wrap:wrap;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.copy-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:600;transition:all .15s;white-space:nowrap}
.btn-copy{background:#3498db;color:#fff}
.btn-copy:hover{background:#2980b9}
.btn-copy.done{background:#27ae60}
.btn-img{background:#8e44ad;color:#fff}
.btn-img:hover{background:#7d3c98}
.btn-img.working{background:#e67e22}
.btn-html{background:#27ae60;color:#fff}
.btn-html:hover{background:#229954}
.btn-txt{background:#e8eaf0;color:#555}
.btn-txt:hover{background:#dde3f0}
.copy-hint{font-size:11px;color:#aaa;margin-left:4px}
.ai-box{background:#f9f5ff;border-left:4px solid #8e44ad;border-radius:8px;padding:16px;margin-top:20px;font-size:13px;line-height:1.6;color:#333}
.ai-title{font-weight:700;color:#6c3a8e;margin-bottom:10px}
.ai-body{color:#555}
"""
    html = html_head('기술분석 — Jason Market', css=_css, chartjs=True, html2canvas=True) + f"""
<body>
<h1>📊 기술분석 대시보드 — Jason Market</h1>
<div class="ts">{ts} &nbsp;|&nbsp; 이동평균 5·20·60·120·200일 &nbsp;|&nbsp; 매물대 &nbsp;|&nbsp; 스토캐스틱 &nbsp;|&nbsp; ATR &nbsp;|&nbsp; OBV &nbsp;|&nbsp; 피봇포인트</div>
{summary_html}

<!-- 공유 버튼 바 -->
<div class="copy-bar">
  <button class="copy-btn btn-img" id="imgBtn" onclick="saveImage()">🖼️ 이미지로 저장 (AI 업로드용)</button>
  <button class="copy-btn btn-html" onclick="saveHTML()">💾 HTML 파일 저장</button>
  <button class="copy-btn btn-copy" id="copyBtn" onclick="copyAnalysis()">📋 텍스트 복사</button>
  <button class="copy-btn btn-txt" onclick="showText()">📄 텍스트 보기</button>
  <span class="copy-hint">이미지·HTML → 다른 AI에 파일 업로드 &nbsp;/&nbsp; 텍스트 → 붙여넣기</span>
</div>
<div id="textArea" style="display:none;margin-bottom:16px">
  <textarea id="plainText" style="width:100%;height:280px;background:#f5f6f8;color:#333;border:1px solid #dde3f0;border-radius:6px;padding:12px;font-size:12px;font-family:monospace;resize:vertical" readonly></textarea>
</div>

<div class="grid">{cards}</div>
{ai_section}

<script>
const PLAIN_TEXT = {plain_text_js};
const DATA = {chart_js};
Chart.defaults.color = '#999';
Chart.defaults.borderColor = '#e0e4ef';

function copyAnalysis() {{
  navigator.clipboard.writeText(PLAIN_TEXT).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✅ 복사 완료! 다른 AI에 붙여넣기 하세요';
    btn.classList.add('done');
    setTimeout(() => {{
      btn.textContent = '📋 다른 AI에 붙여넣기 (복사)';
      btn.classList.remove('done');
    }}, 3000);
  }}).catch(() => {{
    showText();
    alert('자동 복사 실패 — 아래 텍스트 창에서 Ctrl+A → Ctrl+C 로 복사하세요');
  }});
}}

function showText() {{
  const area = document.getElementById('textArea');
  const ta   = document.getElementById('plainText');
  if (area.style.display === 'none') {{
    ta.value = PLAIN_TEXT;
    area.style.display = 'block';
    ta.select();
  }} else {{
    area.style.display = 'none';
  }}
}}

function saveImage() {{
  const btn = document.getElementById('imgBtn');
  btn.textContent = '⏳ 캡처 중... (잠시 대기)';
  btn.classList.add('working');
  document.querySelector('.copy-bar').style.display = 'none';
  document.getElementById('textArea').style.display = 'none';
  setTimeout(() => {{
    html2canvas(document.body, {{
      backgroundColor: '#f5f6f8',
      scale: 1.5,
      useCORS: true,
      allowTaint: true,
      logging: false,
    }}).then(canvas => {{
      document.querySelector('.copy-bar').style.display = '';
      const ts = new Date().toISOString().slice(0,16).replace('T','_').replace(':','');
      const a  = document.createElement('a');
      a.href     = canvas.toDataURL('image/png');
      a.download = `jason_기술분석_${{ts}}.png`;
      a.click();
      btn.textContent = '✅ 저장 완료! 다른 AI에 업로드 하세요';
      btn.classList.remove('working');
      setTimeout(() => {{
        btn.textContent = '🖼️ 이미지로 저장 (AI 업로드용)';
      }}, 4000);
    }}).catch(err => {{
      document.querySelector('.copy-bar').style.display = '';
      btn.textContent = '🖼️ 이미지로 저장 (AI 업로드용)';
      btn.classList.remove('working');
      alert('이미지 저장 실패: ' + err.message);
    }});
  }}, 300);
}}

function saveHTML() {{
  const blob = new Blob([document.documentElement.outerHTML], {{type:'text/html;charset=utf-8'}});
  const ts   = new Date().toISOString().slice(0,16).replace('T','_').replace(':','');
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `jason_기술분석_${{ts}}.html`;
  a.click();
  URL.revokeObjectURL(a.href);
}}

function makeChart(id, name) {{
  const d = DATA[name];
  if (!d) return;
  const priceCtx = document.getElementById(id + '_price');
  const volCtx   = document.getElementById(id + '_vol');
  if (!priceCtx || !volCtx) return;

  new Chart(priceCtx, {{
    type: 'line',
    data: {{
      labels: d.dates,
      datasets: [
        {{label:'가격',   data:d.closes, borderColor:'#1565c0',borderWidth:2,pointRadius:0,tension:0.1,order:0}},
        {{label:'MA5',  data:d.ma5,    borderColor:'#333333',borderWidth:1,pointRadius:0,tension:0.1,spanGaps:true,order:1}},
        {{label:'MA20', data:d.ma20,   borderColor:'#e67e22',borderWidth:1,pointRadius:0,tension:0.1,spanGaps:true,order:2}},
        {{label:'MA60', data:d.ma60,   borderColor:'#e74c3c',borderWidth:1,pointRadius:0,tension:0.1,spanGaps:true,order:3}},
        {{label:'MA120',data:d.ma120,  borderColor:'#9b59b6',borderWidth:1,pointRadius:0,tension:0.1,spanGaps:true,order:4}},
        {{label:'MA200',data:d.ma200,  borderColor:'#3498db',borderWidth:1,pointRadius:0,tension:0.1,spanGaps:true,order:5}},
      ]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      animation:{{duration:0}},
      interaction:{{mode:'index',intersect:false}},
      plugins:{{legend:{{display:false}},tooltip:{{
        backgroundColor:'#fff',titleColor:'#222',bodyColor:'#555',borderColor:'#dde3f0',borderWidth:1,
        callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y?.toFixed(2)}}`}}
      }}}},
      scales:{{
        x:{{display:false}},
        y:{{
          grid:{{color:'#eef0f5'}},
          ticks:{{color:'#999',font:{{size:10}},maxTicksLimit:5,
            callback:v=>v>=1000?v.toLocaleString():v.toFixed(2)
          }}
        }}
      }}
    }}
  }});

  const maxVol = Math.max(...d.volumes.filter(v=>v>0));
  new Chart(volCtx, {{
    type:'bar',
    data:{{
      labels:d.dates,
      datasets:[{{
        data:d.volumes,
        backgroundColor:'rgba(100,130,200,0.4)',
        borderColor:'rgba(100,130,200,0.7)',
        borderWidth:0,
      }}]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      animation:{{duration:0}},
      plugins:{{legend:{{display:false}},tooltip:{{
        backgroundColor:'#fff',bodyColor:'#555',borderColor:'#dde3f0',borderWidth:1,
        callbacks:{{label:ctx=>' 거래량: '+(ctx.parsed.y/1e6).toFixed(1)+'M'}}
      }}}},
      scales:{{
        x:{{display:false}},
        y:{{display:false,max:maxVol*3}}
      }}
    }}
  }});
}}

const nameMap = {json.dumps({f"chart_{i}": r['name'] for i, r in enumerate(results)})};
Object.entries(nameMap).forEach(([id, name]) => makeChart(id, name));
</script>
</body>
</html>"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                     delete=False, encoding='utf-8') as f:
        f.write(html)
        path = f.name
    webbrowser.open(f'file://{path}')
    print(f"\n  🌐 브라우저 열림")
    print(f"  ┌ 🖼️ [이미지로 저장] → PNG 다운로드 → 다른 AI에 파일 업로드")
    print(f"  ├ 💾 [HTML 파일 저장] → HTML 다운로드 → 다른 AI에 파일 업로드")
    print(f"  └ 📋 [텍스트 복사] → 클립보드 복사 → 다른 AI에 붙여넣기\n")


__all__ = ['generate_html']
