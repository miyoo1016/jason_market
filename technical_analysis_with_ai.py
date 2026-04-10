#!/usr/bin/env python3
"""기술분석 + AI 해석 - Jason Market
지표: RSI · MACD · 볼린저밴드 · 이동평균(5/20/60/120/200) · 스토캐스틱 · ATR · OBV · 피봇포인트 · 매물대"""

import os, sys, json, webbrowser
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

from xlsx_sync import load_portfolio as _load_pf

ALERT = '\033[38;5;203m'
RESET = '\033[0m'
EXTREME = ['극도공포','극도탐욕','강력매도','강력매수','매우높음','즉시청산']

def alert_line(t):
    for kw in EXTREME:
        if kw in t: return ALERT + t + RESET
    return t

PROXY_MAP = {
    'KODEX 나스닥100':  'QQQ',
    'KODEX S&P500':    'SPY',
    'KODEX 미국반도체': 'SOXX',
}

def _build_assets():
    assets, seen = {}, set()
    try:
        for h in _load_pf():
            if h.get('is_cash') or h.get('ticker') == 'CASH': continue
            t = h['ticker']
            n = h['name']
            if t == 'XLSX_PRICE': t = PROXY_MAP.get(n, 'SPY')
            elif t == 'GOLD_KRX': t = 'GC=F'
            if t and t not in seen:
                seen.add(t); assets[f'{n:<10}'] = t
    except Exception: pass
    for k, v in {
        'Bitcoin    ':'BTC-USD','금(COMEX선물) ':'GC=F',
        'WTI원유(NYMEX)':'CL=F','다우지수(CME선물)':'YM=F',
        'S&P500(CME선물)':'ES=F','나스닥100(CME선물)':'NQ=F',
        '코스피      ':'^KS11','달러/원    ':'USDKRW=X',
        '미국 10년물 국채':'^TNX','VIX(현물)   ':'^VIX',
    }.items():
        if v not in seen: seen.add(v); assets[k] = v
    return assets

ASSETS = _build_assets()

# ── 지표 계산 ────────────────────────────────────────────────

def _ma(close, p):
    return close.rolling(p).mean()

def calc_rsi(close, p=14):
    d = close.diff()
    g = d.clip(lower=0); l = -d.clip(upper=0)
    ag = g.ewm(com=p-1, min_periods=p).mean()
    al = l.ewm(com=p-1, min_periods=p).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - 100/(1+rs)
    return float(rsi.iloc[-1]) if not rsi.empty else None

def calc_macd(close, fast=12, slow=26, sig=9):
    ml  = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sl  = ml.ewm(span=sig, adjust=False).mean()
    return float(ml.iloc[-1]), float(sl.iloc[-1]), float((ml-sl).iloc[-1])

def calc_bollinger(close, p=20, std=2):
    ma = close.rolling(p).mean()
    sd = close.rolling(p).std()
    u, l = ma+std*sd, ma-std*sd
    c = float(close.iloc[-1])
    pct_b = (c - float(l.iloc[-1])) / (float(u.iloc[-1]) - float(l.iloc[-1])) * 100
    return float(u.iloc[-1]), float(ma.iloc[-1]), float(l.iloc[-1]), pct_b

def calc_stochastic(hist, k=14, d=3):
    lo = hist['Low'].rolling(k).min()
    hi = hist['High'].rolling(k).max()
    denom = (hi - lo).replace(0, np.nan)
    K = (hist['Close'] - lo) / denom * 100
    D = K.rolling(d).mean()
    kv = K.dropna(); dv = D.dropna()
    return (float(kv.iloc[-1]) if not kv.empty else None,
            float(dv.iloc[-1]) if not dv.empty else None)

def calc_atr(hist, p=14):
    h, l, pc = hist['High'], hist['Low'], hist['Close'].shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=p, adjust=False).mean()
    v = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else None
    curr = float(hist['Close'].iloc[-1])
    return v, (v/curr*100 if v and curr else None)

def calc_adx(hist, p=14):
    """ADX + DI 지표 (Wilder's smoothing)"""
    h = hist['High'].values
    l = hist['Low'].values
    c = hist['Close'].values
    n = len(c)
    if n < p + 1:
        return None, None, None
    plus_dm  = np.zeros(n)
    minus_dm = np.zeros(n)
    tr       = np.zeros(n)
    for i in range(1, n):
        up   = h[i] - h[i-1]
        down = l[i-1] - l[i]
        plus_dm[i]  = up   if up > down and up > 0   else 0
        minus_dm[i] = down if down > up  and down > 0 else 0
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    # Wilder smoothing via ewm
    s = pd.Series
    atr_s  = s(tr).ewm(span=p, adjust=False).mean()
    pdm_s  = s(plus_dm).ewm(span=p, adjust=False).mean()
    mdm_s  = s(minus_dm).ewm(span=p, adjust=False).mean()
    pdi = (pdm_s / atr_s.replace(0, np.nan) * 100).fillna(0)
    mdi = (mdm_s / atr_s.replace(0, np.nan) * 100).fillna(0)
    dx  = ((pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan) * 100).fillna(0)
    adx = dx.ewm(span=p, adjust=False).mean()
    adx_val   = float(adx.iloc[-1]) if not adx.empty else None
    plus_di   = float(pdi.iloc[-1]) if not pdi.empty else None
    minus_di  = float(mdi.iloc[-1]) if not mdi.empty else None
    return adx_val, plus_di, minus_di

def calc_obv(hist):
    """OBV 추세 + 다이버전스 탐지. Returns (trend_str, divergence_str)"""
    c = hist['Close'].values
    vol = hist['Volume'].values if 'Volume' in hist.columns else np.ones(len(c))
    obv = np.zeros(len(c))
    for i in range(1, len(c)):
        if   c[i] > c[i-1]: obv[i] = obv[i-1] + vol[i]
        elif c[i] < c[i-1]: obv[i] = obv[i-1] - vol[i]
        else:                obv[i] = obv[i-1]
    trend = 'flat'
    if len(obv) >= 20:
        r, m = obv[-5:].mean(), obv[-20:-5].mean()
        if   r > m*1.01: trend = 'up'
        elif r < m*0.99: trend = 'down'
    # 다이버전스 탐지 (최근 5일 가격 vs 이전 15일 가격)
    divergence = None
    if len(c) >= 20:
        price_recent = c[-5:].mean()
        price_prev   = c[-20:-5].mean()
        obv_recent   = obv[-5:].mean()
        obv_prev     = obv[-20:-5].mean()
        price_up = price_recent > price_prev * 1.005
        price_dn = price_recent < price_prev * 0.995
        obv_up   = obv_recent > obv_prev * 1.001
        obv_dn   = obv_recent < obv_prev * 0.999
        if price_up and obv_dn:
            divergence = '⚠ 하락다이버전스 (가격↑·OBV↓)'
        elif price_dn and obv_up:
            divergence = '✅ 상승다이버전스 (가격↓·OBV↑)'
    return trend, divergence

def calc_pivot_weekly(hist):
    """주간 피봇 포인트 (지난 주 5거래일 데이터 사용)"""
    if len(hist) < 10: return None
    week = hist.tail(10).head(5)
    H = float(week['High'].max())
    L = float(week['Low'].min())
    C = float(week['Close'].iloc[-1])
    P = (H+L+C)/3
    return {'P':P,'R1':2*P-L,'R2':P+(H-L),'S1':2*P-H,'S2':P-(H-L)}

def calc_volume_profile(hist, bins=12):
    """매물대 분석. Returns (profile_list, poc_price)"""
    c = hist['Close'].values
    v = hist['Volume'].values if 'Volume' in hist.columns else np.ones(len(c))
    v = np.where(v > 0, v, 1)
    mn, mx = c.min(), c.max()
    if mx == mn: return [], None
    edges = np.linspace(mn, mx, bins+1)
    profile = []
    for i in range(bins):
        lo, hi = edges[i], edges[i+1]
        mask = (c >= lo) & (c <= hi)
        vol  = float(v[mask].sum())
        profile.append({'price': round((lo+hi)/2, 4), 'volume': vol})
    mx_v = max(p['volume'] for p in profile) or 1
    for p in profile: p['pct'] = round(p['volume']/mx_v*100, 1)
    poc_price = max(profile, key=lambda x: x['volume'])['price'] if profile else None
    return profile, poc_price

def calc_composite_score(r):
    """종합 매매신호 점수 (-7 ~ +7)"""
    # 추세 점수
    trend_score = 0
    if r.get('ma20'):
        trend_score += 1 if r['curr'] > r['ma20'] else -1
    if r.get('ma60'):
        trend_score += 1 if r['curr'] > r['ma60'] else -1
    if r.get('ma200'):
        trend_score += 1 if r['curr'] > r['ma200'] else -1
    # 모멘텀 점수
    mom = 0
    rsi = r.get('rsi')
    if rsi is not None:
        if   rsi < 30:  mom += 2
        elif rsi < 45:  mom += 1
        elif rsi > 70:  mom -= 2
        elif rsi > 55:  mom -= 1
    if r.get('macd') is not None and r.get('macd_sig') is not None:
        mom += 1 if r['macd'] > r['macd_sig'] else -1
    mom = max(-3, min(3, mom))
    # 거래량 점수
    obv_trend = r.get('obv_trend', 'flat')
    vol_score = 1 if obv_trend == 'up' else (-1 if obv_trend == 'down' else 0)
    total = trend_score + mom + vol_score
    # 레이블
    if   total >= 5:  label, color = '강한매수', '#00838f'
    elif total >= 3:  label, color = '매수',     '#26a69a'
    elif total >= 1:  label, color = '약매수',   '#80cbc4'
    elif total >= -1: label, color = '중립',     '#90a4ae'
    elif total >= -3: label, color = '약매도',   '#ff8a65'
    elif total >= -5: label, color = '매도',     '#e65100'
    else:             label, color = '강한매도', '#c62828'
    bar_pct = int((total + 7) / 14 * 100)
    return {
        'trend_score':    trend_score,
        'momentum_score': mom,
        'volume_score':   vol_score,
        'total':          total,
        'label':          label,
        'color':          color,
        'bar_pct':        bar_pct,
    }

def safe_float(s):
    return round(float(s), 6) if not pd.isna(s) else None

def ma_series(close, p, n=60):
    s = close.rolling(p).mean().tail(n)
    return [safe_float(v) for v in s]

# ── 자산 분석 ────────────────────────────────────────────────

def analyze_asset(name, ticker):
    try:
        hist = yf.Ticker(ticker).history(period='1y')
        if hist.empty or len(hist) < 30: return None
        close    = hist['Close']
        prev_cls = float(close.iloc[-2])
        curr     = float(close.iloc[-1])

        # 미국/글로벌 티커: 1분봉 prepost로 실시간 현재가 갱신
        if not (ticker.endswith('.KS') or ticker in ('^KS11',)):
            try:
                h1m = yf.Ticker(ticker).history(period='1d', interval='1m', prepost=True)
                if not h1m.empty:
                    curr = float(h1m['Close'].iloc[-1])
            except Exception:
                pass

        pct = (curr - prev_cls) / prev_cls * 100

        rsi              = calc_rsi(close)
        macd, sig, hst   = calc_macd(close)
        bb_u, bb_m, bb_l, pct_b = calc_bollinger(close)
        stoch_k, stoch_d = calc_stochastic(hist)
        atr_val, atr_pct = calc_atr(hist)
        obv_trend, obv_div = calc_obv(hist)
        adx_val, plus_di, minus_di = calc_adx(hist)
        pivot            = calc_pivot_weekly(hist)
        vol_profile, poc_price = calc_volume_profile(hist.tail(90))

        def gma(p): return float(close.rolling(p).mean().iloc[-1]) if len(close)>=p else None

        # 차트용 데이터 (최근 60일)
        h60   = hist.tail(60)
        c60   = h60['Close']
        dates = [d.strftime('%m/%d') for d in h60.index]
        vols  = [int(v) for v in (h60['Volume'] if 'Volume' in h60.columns else [0]*60)]
        chart = {
            'dates':  dates,
            'closes': [safe_float(v) for v in c60],
            'volumes':vols,
            'ma5':    ma_series(close, 5),
            'ma20':   ma_series(close, 20),
            'ma60':   ma_series(close, 60),
            'ma120':  ma_series(close, 120),
            'ma200':  ma_series(close, 200),
        }

        base = {
            'name':name.strip(),'ticker':ticker,
            'curr':curr,'pct':pct,
            'rsi':rsi,'macd':macd,'macd_sig':sig,'macd_hist':hst,
            'bb_upper':bb_u,'bb_mid':bb_m,'bb_lower':bb_l,'pct_b':pct_b,
            'ma5':gma(5),'ma20':gma(20),'ma50':gma(50),
            'ma60':gma(60),'ma120':gma(120),'ma200':gma(200),
            'stoch_k':stoch_k,'stoch_d':stoch_d,
            'atr_val':atr_val,'atr_pct':atr_pct,
            'obv_trend':obv_trend,'obv_div':obv_div,
            'adx_val':adx_val,'plus_di':plus_di,'minus_di':minus_di,
            'pivot':pivot,'vol_profile':vol_profile,'poc_price':poc_price,
            'chart':chart,
        }
        base['score'] = calc_composite_score(base)
        return base
    except Exception as e:
        print(f"  ⚠ {name.strip()} 오류: {e}")
        return None

# ── AI 분석 ─────────────────────────────────────────────────

def ai_analysis(results):
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key: return ""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key.strip())
    except Exception as e:
        print(f"\n⚠ Claude 초기화 실패: {e}"); return ""

    lines = []
    for r in results:
        ma_st = []
        if r['ma20']  and r['curr'] > r['ma20']:  ma_st.append("MA20위")
        if r['ma60']  and r['curr'] > r['ma60']:  ma_st.append("MA60위")
        if r['ma200'] and r['curr'] > r['ma200']: ma_st.append("MA200위")
        rsi_s = f"{r['rsi']:.1f}"    if r['rsi']     else 'N/A'
        stk_s = f"{r['stoch_k']:.0f}" if r['stoch_k'] else '-'
        std_s = f"{r['stoch_d']:.0f}" if r['stoch_d'] else '-'
        atp_s = f"{r['atr_pct']:.1f}" if r['atr_pct'] else '-'
        score = r.get('score', {})
        sc_label = score.get('label', '중립')
        sc_total = score.get('total', 0)
        lines.append(
            f"{r['name']}: {r['curr']:,.2f} ({r['pct']:+.2f}%), "
            f"RSI={rsi_s}, Stoch={stk_s}/{std_s}, "
            f"MACD={'양' if r['macd']>r['macd_sig'] else '음'}, "
            f"BB={r['pct_b']:.0f}%, OBV={r['obv_trend']}, "
            f"ATR={atp_s}%, MA=[{' '.join(ma_st) or '모두하위'}], "
            f"종합점수={sc_label}({sc_total:+d})"
        )

    prompt = f"""Jason의 포트폴리오 기술분석 ({datetime.now().strftime('%Y-%m-%d %H:%M')}):

{chr(10).join(lines)}

각 자산: ① 포지션(매수/매도/관망) ② 핵심 신호 1개 ③ 단기 레벨
마지막에 포트폴리오 종합의견 2줄.
한국어, 실용적, 500자 이내."""

    try:
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001', max_tokens=900,
            messages=[{'role':'user','content':prompt}]
        )
        text = resp.content[0].text
        print(f"\n{'━'*60}\n  AI 기술분석 해석\n{'━'*60}")
        print(text); print(f"{'━'*60}\n")
        return text
    except Exception as e:
        print(f"\n⚠ AI 분석 실패: {e}"); return ""

# ── HTML 생성 ────────────────────────────────────────────────

def generate_html(results, ai_text=""):
    if not results: return
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def price_fmt(r):
        t, v = r['ticker'], r['curr']
        if t=='BTC-USD':                        return f"${v:,.0f}"
        if t in ('GC=F','BZ=F','CL=F'):         return f"${v:,.1f}"
        if t in ('YM=F','ES=F','NQ=F','RTY=F'): return f"{v:,.1f}"
        if t.endswith('.KS'):                    return f"₩{v:,.0f}"
        if t=='USDKRW=X':                        return f"₩{v:,.1f}"
        if t in ('^TNX','^VIX','^KS11'):         return f"{v:,.2f}"
        return f"${v:,.2f}"

    def c_chg(p):  return '#00838f' if p>=0 else '#c62828'
    def c_rsi(v):
        if v is None: return '#888'
        return '#c62828' if v>=70 else '#00838f' if v<=30 else '#1565c0'
    def c_bb(v):   return '#c62828' if v>80 else '#00838f' if v<20 else '#1565c0'
    def c_obv(v):  return '#00838f' if v=='up' else '#c62828' if v=='down' else '#90a4ae'

    def ma_badge(curr, ma, lbl):
        if not ma: return ''
        pct = (curr-ma)/ma*100
        col = '#00838f' if curr>ma else '#c62828'
        return f'<span class="badge" style="background:{col}">{lbl} {pct:+.1f}%</span>'

    def pivot_row(pivot, curr):
        if not pivot: return ''
        def pc(k, v):
            col = '#00838f' if v<curr else '#c62828' if v>curr else '#e65100'
            return f'<span class="pvt" style="border-color:{col};color:{col}">{k}<br><small>{v:,.2f}</small></span>'
        return f"""<div class="pivot-row">
          {pc('S2',pivot['S2'])}{pc('S1',pivot['S1'])}{pc('P',pivot['P'])}{pc('R1',pivot['R1'])}{pc('R2',pivot['R2'])}
        </div>"""

    def vol_profile_bars(vp, curr, poc_price=None):
        if not vp: return ''
        bars = ""
        for b in reversed(vp):
            is_curr = abs(b['price']-curr)/curr < 0.02
            is_poc  = (poc_price is not None and abs(b['price']-poc_price)/max(poc_price,0.001) < 0.001)
            if is_curr:   col = '#e67e22'
            elif is_poc:  col = '#e65100'
            else:         col = '#b0bec5'
            bars += f"""<div class="vp-row">
              <span class="vp-price">{b['price']:,.2f}</span>
              <div class="vp-bar-wrap"><div class="vp-bar" style="width:{b['pct']}%;background:{col}"></div></div>
            </div>"""
        return f'<div class="vp-container">{bars}</div>'

    # 차트 데이터 JSON
    all_chart_data = {r['name']: r['chart'] for r in results}

    # 카드 생성
    cards = ""
    for idx, r in enumerate(results):
        cid   = f"chart_{idx}"
        rsi   = r['rsi'] or 50
        pct_b = max(0, min(100, r['pct_b'] or 50))
        sk    = r['stoch_k'] or 50
        sd    = r['stoch_d'] or 50

        score       = r.get('score', {})
        score_color = score.get('color', '#90a4ae')
        score_label = score.get('label', '중립')
        score_total = score.get('total', 0)
        bar_pct     = score.get('bar_pct', 50)
        trend_sc    = score.get('trend_score', 0)
        mom_sc      = score.get('momentum_score', 0)
        vol_sc      = score.get('volume_score', 0)
        obv_div     = r.get('obv_div')
        div_warn    = (f'<span style="color:#e65100;font-weight:600">{obv_div}</span>' if obv_div else '')

        # ADX 해석
        adx_val  = r.get('adx_val')
        plus_di  = r.get('plus_di')
        minus_di = r.get('minus_di')
        if adx_val is not None:
            if   adx_val >= 40: adx_lbl = '매우강한추세'
            elif adx_val >= 25: adx_lbl = '강한추세'
            elif adx_val >= 20: adx_lbl = '추세형성중'
            else:               adx_lbl = '추세없음'
            di_lbl = '상승추세' if (plus_di or 0) > (minus_di or 0) else '하락추세'
            adx_str = f"{adx_val:.1f} ({adx_lbl} / {di_lbl})"
        else:
            adx_str = 'N/A'

        poc_fmt = f"{r['poc_price']:,.2f}" if r.get('poc_price') else 'N/A'

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

      <!-- RSI -->
      <div class="ind-label">RSI <b style="color:{c_rsi(r['rsi'])}">{f"{r['rsi']:.1f}" if r['rsi'] else 'N/A'} {'과매수' if rsi>=70 else '과매도' if rsi<=30 else '중립'}</b></div>
      <div class="track"><div class="zone z-buy" style="left:0;width:30%"></div><div class="zone z-sell" style="left:70%;width:30%"></div><div class="needle" style="left:{rsi}%;background:{c_rsi(r['rsi'])}"></div><span class="tick" style="left:30%">30</span><span class="tick" style="left:70%">70</span></div>

      <!-- 스토캐스틱 -->
      <div class="ind-label">스토캐스틱 <b style="color:{c_rsi(sk)}">%K {sk:.1f}</b> / <b style="color:#aaa">%D {sd:.1f}</b></div>
      <div class="track"><div class="zone z-buy" style="left:0;width:20%"></div><div class="zone z-sell" style="left:80%;width:20%"></div><div class="needle" style="left:{max(0,min(100,sk))}%;background:{c_rsi(sk)}"></div><div class="needle2" style="left:{max(0,min(100,sd))}%"></div><span class="tick" style="left:20%">20</span><span class="tick" style="left:80%">80</span></div>

      <!-- 볼린저 밴드 -->
      <div class="ind-label">볼린저밴드 <b style="color:{c_bb(pct_b)}">{'상단과열' if pct_b>80 else '하단침체' if pct_b<20 else f'{pct_b:.0f}%'}</b></div>
      <div class="bb-track"><div class="bb-fill" style="width:{pct_b}%;background:{c_bb(pct_b)}"></div></div>
      <div class="bb-lbl"><span>하단매수</span><span>중간</span><span>상단과열</span></div>

      <!-- MACD -->
      <div class="ind-label">MACD <b style="color:{'#00838f' if r['macd']>r['macd_sig'] else '#c62828'}">{'▲ 매수' if r['macd']>r['macd_sig'] else '▼ 매도'}</b> <small style="color:#888">히스토그램 {r['macd_hist']:+.4f}</small></div>
      <div class="macd-bar"><div style="width:{min(100,abs(r['macd_hist'])/(abs(r['macd_hist'])+1e-9)*100):.0f}%;height:100%;background:{'#00838f' if r['macd']>r['macd_sig'] else '#c62828'};border-radius:3px;opacity:0.8"></div></div>

      <!-- ATR / OBV / ADX -->
      <div class="row3">
        <div class="mini-box">
          <div class="mini-title">ATR (변동성)</div>
          <div class="mini-val">{f"{r['atr_pct']:.2f}%" if r['atr_pct'] else 'N/A'} <small style="color:#888">일일리스크</small></div>
        </div>
        <div class="mini-box">
          <div class="mini-title">OBV 추세</div>
          <div class="mini-val" style="color:{c_obv(r['obv_trend'])}">{'↑ 매집' if r['obv_trend']=='up' else '↓ 분산' if r['obv_trend']=='down' else '→ 중립'}</div>
        </div>
        <div class="mini-box">
          <div class="mini-title">ADX (추세강도)</div>
          <div class="mini-val" style="font-size:11px;color:#333">{adx_str}</div>
        </div>
      </div>

      <!-- 주간 피봇 포인트 -->
      <div class="section-title">📌 주간 피봇 포인트</div>
      {pivot_row(r['pivot'], r['curr'])}
    </div>"""

    ai_section = ""
    if ai_text:
        ai_section = f"""<div class="ai-box">
      <div class="ai-title">🤖 AI 기술분석 해석 <span style="font-size:12px;font-weight:400;color:#aaa">(Claude Haiku)</span></div>
      <div class="ai-body">{ai_text.replace(chr(10),'<br>')}</div>
    </div>"""

    # ── 다른 AI용 텍스트 요약 생성 ──────────────────────────────
    def _ma_status(r):
        parts = []
        for p, k in [(5,'ma5'),(20,'ma20'),(60,'ma60'),(120,'ma120'),(200,'ma200')]:
            if r[k]:
                parts.append(f"MA{p}{'위' if r['curr']>r[k] else '아래'}")
        return ' '.join(parts) if parts else '정보없음'

    def _pivot_text(pv):
        if not pv: return '없음'
        return f"S2={pv['S2']:,.2f} / S1={pv['S1']:,.2f} / P={pv['P']:,.2f} / R1={pv['R1']:,.2f} / R2={pv['R2']:,.2f}"

    text_lines = [f"=== Jason Market 기술분석 보고서 ===", f"기준시각: {ts}", ""]
    for r in results:
        rsi_lbl  = '과매수' if (r['rsi'] or 0)>=70 else '과매도' if (r['rsi'] or 100)<=30 else '중립'
        stk_lbl  = '과매수' if (r['stoch_k'] or 0)>=80 else '과매도' if (r['stoch_k'] or 100)<=20 else '중립'
        bb_lbl   = '상단과열' if r['pct_b']>80 else '하단침체' if r['pct_b']<20 else '중간'
        macd_lbl = '▲매수' if r['macd']>r['macd_sig'] else '▼매도'
        obv_lbl  = '↑매집' if r.get('obv_trend')=='up' else '↓분산' if r.get('obv_trend')=='down' else '→중립'
        rsi_s    = f"{r['rsi']:.1f}" if r['rsi'] else 'N/A'
        sk_s     = f"{r['stoch_k']:.0f}" if r['stoch_k'] else 'N/A'
        sd_s     = f"{r['stoch_d']:.0f}" if r['stoch_d'] else 'N/A'
        atr_s    = f"{r['atr_pct']:.2f}%" if r['atr_pct'] else 'N/A'
        text_lines += [
            f"[{r['name']} / {r['ticker']}]",
            f"현재가: {price_fmt(r)}  등락: {r['pct']:+.2f}%",
            f"RSI: {rsi_s} → {rsi_lbl}",
            f"스토캐스틱: %K={sk_s} / %D={sd_s} → {stk_lbl}",
            f"볼린저밴드: {r['pct_b']:.0f}% → {bb_lbl}",
            f"MACD: {macd_lbl}  (히스토그램 {r['macd_hist']:+.4f})",
            f"ATR(변동성): {atr_s}",
            f"OBV: {obv_lbl}",
            f"이동평균: {_ma_status(r)}",
            f"피봇포인트: {_pivot_text(r['pivot'])}",
            "",
        ]
    if ai_text:
        text_lines += ["=== Claude AI 분석 ===", ai_text, ""]
    text_lines.append("※ 이 보고서는 투자 참고용이며 매매 결정은 본인 책임입니다.")
    plain_text = "\n".join(text_lines)

    chart_js = json.dumps(all_chart_data, ensure_ascii=False)
    plain_text_js = json.dumps(plain_text, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>기술분석 — Jason Market</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f6f8;color:#222;font-family:'Segoe UI',Arial,sans-serif;padding:20px}}
h1{{font-size:19px;font-weight:700;color:#1a237e;margin-bottom:3px}}
.ts{{font-size:12px;color:#888;margin-bottom:10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}}
.card{{background:#fff;border-radius:10px;padding:18px;border:1px solid #dde3f0;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.aname{{font-size:15px;font-weight:700;color:#1a237e}}
.tbadge{{font-size:11px;background:#eef1f8;color:#555;padding:2px 8px;border-radius:4px}}
.price-row{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}}
.price{{font-size:22px;font-weight:700;color:#111}}
.chart-wrap{{margin-bottom:4px}}
.ma-legend{{display:flex;gap:10px;font-size:10px;margin-bottom:6px;flex-wrap:wrap}}
.section-title{{font-size:11px;color:#999;margin:10px 0 5px;text-transform:uppercase;letter-spacing:.5px}}
.ma-row{{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0}}
.badge{{font-size:11px;color:#fff;padding:2px 7px;border-radius:4px}}
.ind-label{{font-size:12px;color:#555;margin:10px 0 4px}}
.track{{position:relative;height:11px;background:#e8eaf0;border-radius:6px;margin-bottom:14px}}
.zone{{position:absolute;height:100%;opacity:.25;border-radius:6px}}
.z-buy{{background:#00838f}}
.z-sell{{background:#c62828}}
.needle{{position:absolute;top:-3px;width:4px;height:17px;border-radius:2px;transform:translateX(-50%);box-shadow:0 0 4px rgba(0,0,0,.2)}}
.needle2{{position:absolute;top:0;width:2px;height:100%;background:#e67e22;opacity:.8;transform:translateX(-50%)}}
.tick{{position:absolute;top:13px;font-size:10px;color:#aaa;transform:translateX(-50%)}}
.bb-track{{height:9px;background:#e8eaf0;border-radius:5px;overflow:hidden;margin-bottom:2px}}
.bb-fill{{height:100%;border-radius:5px}}
.bb-lbl{{display:flex;justify-content:space-between;font-size:10px;color:#aaa;margin-bottom:6px}}
.macd-bar{{height:8px;background:#e8eaf0;border-radius:4px;overflow:hidden;margin-top:5px;margin-bottom:10px}}
.row2{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}}
.row3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}
.score-section{{margin:8px 0}}
.score-label{{font-size:12px;color:#555;margin-bottom:4px}}
.score-bar-wrap{{height:8px;background:#e8eaf0;border-radius:5px;overflow:hidden;margin-bottom:4px}}
.score-bar-fill{{height:100%;border-radius:5px;transition:width 0.3s}}
.score-details{{display:flex;gap:10px;font-size:11px;color:#888}}
.mini-box{{background:#f0f2f8;border-radius:7px;padding:8px 10px}}
.mini-title{{font-size:10px;color:#999;margin-bottom:3px}}
.mini-val{{font-size:14px;font-weight:600;color:#333}}
.vp-container{{margin-bottom:6px}}
.vp-row{{display:flex;align-items:center;gap:6px;margin-bottom:2px}}
.vp-price{{font-size:10px;color:#aaa;width:58px;text-align:right;flex-shrink:0}}
.vp-bar-wrap{{flex:1;height:8px;background:#e8eaf0;border-radius:3px;overflow:hidden}}
.vp-bar{{height:100%;border-radius:3px;opacity:.85}}
.pivot-row{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}}
.pvt{{font-size:11px;border:1px solid;border-radius:5px;padding:3px 8px;text-align:center;line-height:1.5}}
.pvt small{{font-size:10px;display:block}}
/* 공유 버튼 바 */
.copy-bar{{display:flex;align-items:center;gap:10px;margin-bottom:18px;padding:12px 16px;background:#fff;border-radius:8px;border:1px solid #dde3f0;flex-wrap:wrap;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.copy-btn{{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:600;transition:all .15s;white-space:nowrap}}
.btn-copy{{background:#3498db;color:#fff}}
.btn-copy:hover{{background:#2980b9}}
.btn-copy.done{{background:#27ae60}}
.btn-img{{background:#8e44ad;color:#fff}}
.btn-img:hover{{background:#7d3c98}}
.btn-img.working{{background:#e67e22}}
.btn-html{{background:#27ae60;color:#fff}}
.btn-html:hover{{background:#229954}}
.btn-txt{{background:#e8eaf0;color:#555}}
.btn-txt:hover{{background:#dde3f0}}
.copy-hint{{font-size:11px;color:#aaa;margin-left:4px}}
</style>
</head>
<body>
<h1>📊 기술분석 대시보드 — Jason Market</h1>
<div class="ts">{ts} &nbsp;|&nbsp; 이동평균 5·20·60·120·200일 &nbsp;|&nbsp; 매물대 &nbsp;|&nbsp; 스토캐스틱 &nbsp;|&nbsp; ATR &nbsp;|&nbsp; OBV &nbsp;|&nbsp; 피봇포인트</div>

<!-- 다른 AI 공유 버튼 바 -->
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
  // 버튼 바는 캡처에서 제외
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

  // 가격 + 이동평균 차트
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

  // 거래량 차트
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

// 모든 차트 초기화
const nameMap = {json.dumps({f"chart_{i}": r['name'] for i, r in enumerate(results)})};
Object.entries(nameMap).forEach(([id, name]) => makeChart(id, name));
</script>
</body>
</html>"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                     delete=False, encoding='utf-8') as f:
        f.write(html)
        path = f.name
    webbrowser.open(f'file://{path}')
    print(f"\n  🌐 브라우저 열림")
    print(f"  ┌ 🖼️ [이미지로 저장] → PNG 다운로드 → 다른 AI에 파일 업로드")
    print(f"  ├ 💾 [HTML 파일 저장] → HTML 다운로드 → 다른 AI에 파일 업로드")
    print(f"  └ 📋 [텍스트 복사] → 클립보드 복사 → 다른 AI에 붙여넣기\n")

# ── 메인 ─────────────────────────────────────────────────────

def main():
    print(f"\n{'━'*62}")
    print(f"  Jason 기술분석   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*62}")
    print("  데이터 수집 중 (1y 데이터, 약 20초)...\n")

    results = []
    for name, ticker in ASSETS.items():
        r = analyze_asset(name, ticker)
        if not r: continue
        results.append(r)

        arrow = '▲' if r['pct']>=0 else '▼'
        t = r['ticker']
        if   t=='BTC-USD':                        ps=f"${r['curr']:,.0f}"
        elif t in ('GC=F','BZ=F','CL=F'):         ps=f"${r['curr']:,.1f}"
        elif t in ('YM=F','ES=F','NQ=F','RTY=F'): ps=f"{r['curr']:,.1f}"
        elif t.endswith('.KS'):                    ps=f"₩{r['curr']:,.0f}"
        elif t=='USDKRW=X':                        ps=f"₩{r['curr']:,.1f}"
        elif t in ('^TNX','^VIX','^KS11'):         ps=f"{r['curr']:,.2f}"
        else:                                      ps=f"${r['curr']:,.2f}"

        print(f"  {r['name']}  {ps}  {r['pct']:+.2f}% {arrow}")
        rsi_s  = f"{r['rsi']:.0f}"  if r['rsi']     else 'N/A'
        stk_s  = f"{r['stoch_k']:.0f}" if r['stoch_k'] else '-'
        std_s  = f"{r['stoch_d']:.0f}" if r['stoch_d'] else '-'
        atr_s  = f"{r['atr_pct']:.1f}%" if r['atr_pct'] else '-'
        print(f"    RSI {rsi_s}  Stoch {stk_s}/{std_s}  BB {r['pct_b']:.0f}%  ATR {atr_s}  OBV {r.get('obv_trend','?')}  [{r['score']['label']}]")
        print()

    generate_html(results)


if __name__ == '__main__':
    main()
