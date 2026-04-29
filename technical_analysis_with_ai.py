from jm_lib.colors import ALERT, AMBER, CYAN, RESET, GREEN, RED, WARN
from jm_lib.env import ANTHROPIC_API_KEY

#!/usr/bin/env python3
"""기술분석 + AI 해석 - Jason Market (메인 모듈)
지표: RSI · MACD · 볼린저밴드 · 이동평균(5/20/60/120/200) · 스토캐스틱 · ATR · OBV · 피봇포인트 · 매물대"""

import yfinance as yf
from datetime import datetime

from technical_analysis_indicators import (
    calc_rsi, calc_macd, calc_bollinger, calc_stochastic,
    calc_atr, calc_adx, calc_obv, calc_pivot_weekly,
    calc_volume_profile, calc_composite_score, safe_float, ma_series,
)
from technical_analysis_html import generate_html
from xlsx_sync import load_portfolio as _load_pf

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
    api_key = ANTHROPIC_API_KEY
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
