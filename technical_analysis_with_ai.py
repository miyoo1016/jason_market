from jm_lib.colors import ALERT, AMBER, CYAN, RESET, GREEN, RED, WARN
from jm_lib.env import ANTHROPIC_API_KEY

#!/usr/bin/env python3
"""기술분석 + AI 해석 - Jason Market (메인 모듈)
지표: RSI · MACD · 볼린저밴드 · 이동평균(5/20/60/120/200) · 스토캐스틱 · ATR · OBV · 피봇포인트 · 매물대"""

import yfinance as yf
import os
from datetime import datetime

from technical_analysis_indicators import (
    calc_rsi, calc_macd, calc_bollinger, calc_stochastic,
    calc_atr, calc_adx, calc_obv, calc_pivot_weekly,
    calc_volume_profile, calc_composite_score, safe_float, ma_series,
    classify_asset, has_reliable_volume, bb_label, momentum_label,
    rsi_label, stoch_label, obv_label, pivot_position_label,
)
from technical_analysis_html import generate_html
from xlsx_sync import load_portfolio as _load_pf

EXTREME = ['극도공포','극도탐욕','매우높음','즉시청산']

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
            elif t == 'GOLD_KRX':
                t = 'GC=F'
                n = '금선물(COMEX)'
            elif t == 'GC=F' and '금현물' in n:
                n = '금선물(COMEX)'
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


def _debug_tech_enabled():
    return os.getenv('JM_DEBUG_TECH', '').lower() in ('1', 'true', 'yes', 'on')


def _data_warnings(name, ticker, hist, curr, prev_cls):
    warnings = []
    try:
        if curr is None or prev_cls is None or curr <= 0 or prev_cls <= 0:
            return ['DATA_INVALID: current/close 없음 또는 0 이하']
        if abs((curr - prev_cls) / prev_cls * 100) >= 20:
            warnings.append('DATA_CHECK: 최근 등락률 ±20% 이상')
        med60 = float(hist['Close'].tail(60).median())
        if med60 > 0 and (curr >= med60 * 2 or curr <= med60 * 0.5):
            warnings.append('DATA_CHECK: 현재가가 60일 중앙값 대비 2배/0.5배 범위 밖')
        # yfinance가 지수/국내주 스케일을 잘못 반환하는 케이스를 가격 보정 없이 경고만 표시
        if ticker == '^KS11' and (curr >= 5000 or curr <= 1000):
            warnings.append('DATA_CHECK: 코스피 지수 통상 범위 이탈')
        if ticker == '005930.KS' and (curr >= 150000 or curr <= 20000):
            warnings.append('DATA_CHECK: 삼성전자 통상 범위 이탈')
        if ticker == 'GC=F' and '금현물' in name:
            warnings.append('DATA_CHECK: 표시명과 GC=F 불일치')
    except Exception as e:
        warnings.append(f'DATA_CHECK: 검증 실패({e})')
    return warnings


def _debug_tech_print(name, ticker, hist, last_close, prev_close):
    if not _debug_tech_enabled():
        return
    try:
        median60 = float(hist['Close'].tail(60).median())
        rows = len(hist)
        last_date = hist.index[-1]
        change_pct = (last_close - prev_close) / prev_close * 100 if prev_close else 0
        print(
            "    DEBUG_TECH "
            f"symbol={ticker} display_name={name.strip()} "
            f"last_close={last_close:,.4f} prev_close={prev_close:,.4f} "
            f"change_pct={change_pct:+.2f}% median60={median60:,.4f} "
            f"source_rows={rows} last_date={last_date}"
        )
    except Exception as e:
        print(f"    DEBUG_TECH symbol={ticker} display_name={name.strip()} error={e}")

# ── 자산 분석 ────────────────────────────────────────────────

def analyze_asset(name, ticker):
    try:
        hist = yf.Ticker(ticker).history(period='1y')
        if hist.empty or len(hist) < 30: return None
        close    = hist['Close']
        prev_cls = float(close.iloc[-2])
        last_cls = float(close.iloc[-1])
        curr     = last_cls
        _debug_tech_print(name, ticker, hist, last_cls, prev_cls)

        # 미국/글로벌 티커: 1분봉 prepost로 실시간 현재가 갱신
        if not (ticker.endswith('.KS') or ticker in ('^KS11',)):
            try:
                h1m = yf.Ticker(ticker).history(period='1d', interval='1m', prepost=True)
                if not h1m.empty:
                    curr = float(h1m['Close'].iloc[-1])
            except Exception:
                pass

        pct = (curr - prev_cls) / prev_cls * 100
        asset_type = classify_asset(name, ticker)
        data_warnings = _data_warnings(name.strip(), ticker, hist, curr, prev_cls)

        rsi              = calc_rsi(close)
        macd, sig, hst   = calc_macd(close)
        bb_u, bb_m, bb_l, pct_b = calc_bollinger(close)
        stoch_k, stoch_d = calc_stochastic(hist)
        atr_val, atr_pct = calc_atr(hist)
        volume_reliable = has_reliable_volume(hist, asset_type)
        if volume_reliable:
            obv_trend, obv_div = calc_obv(hist)
        else:
            obv_trend, obv_div = 'na', None
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
            'asset_type':asset_type,
            'data_warnings':data_warnings,
            'volume_reliable':volume_reliable,
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
        if asset_type == 'cash_like':
            base['score'] = {**base['score'], 'label': '해석 제한', 'total': 0,
                             'trend_score': 0, 'momentum_score': 0,
                             'volume_score': 0, 'bar_pct': 50, 'color': '#90a4ae'}
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
            f"MACD={momentum_label(r['macd'], r['macd_sig'], r.get('macd_hist'))}, "
            f"BB={bb_label(r.get('pct_b'))}, OBV={obv_label(r.get('obv_trend'), r.get('volume_reliable'))}, "
            f"ATR={atp_s}%, MA=[{' '.join(ma_st) or '모두하위'}], "
            f"종합점수={sc_label}({sc_total:+d})"
        )

    prompt = f"""Jason의 포트폴리오 기술분석 ({datetime.now().strftime('%Y-%m-%d %H:%M')}):

{chr(10).join(lines)}

각 자산: ① 기술상태(상승우위/하락우위/중립) ② 핵심 신호 1개 ③ 단기 레벨
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
        atr_s  = f"{r['atr_pct']:.1f}%" if r['atr_pct'] else '-'
        for w in r.get('data_warnings', []):
            print(f"    ⚠ {w}")
        if t == 'USDKRW=X' and r['pct'] > 0:
            print("    매크로: 환율 부담 / 원화 약세 압력")
        elif t == '^TNX' and r['pct'] > 0:
            print("    매크로: 금리 부담")
        elif t == '^VIX' and r['pct'] > 0:
            print("    매크로: 변동성 부담")
        if r.get('data_warnings'):
            print("    기술지표: 신뢰 제한 — 원천 가격 데이터 이상으로 RSI/MACD/스토캐스틱 해석 제외")
        elif r['asset_type'] == 'cash_like':
            print("    기술지표: 해석 제한 — 현금성/금리형 상품은 RSI/MACD 과열 판단 부적합")
            print(f"    ATR(변동성): {atr_s}")
            print("    피봇위치: N/A — 현금성/금리형 상품은 피봇 해석 부적합")
        else:
            rsi_s  = f"{r['rsi']:.0f}"  if r['rsi']     else 'N/A'
            stk_s  = f"{r['stoch_k']:.0f}" if r['stoch_k'] else '-'
            std_s  = f"{r['stoch_d']:.0f}" if r['stoch_d'] else '-'
            print(
                f"    RSI {rsi_s}({rsi_label(r.get('rsi'), r['asset_type'])})  "
                f"Stoch {stk_s}/{std_s}({stoch_label(r.get('stoch_k'), r['asset_type'])})  "
                f"BB {r['pct_b']:.0f}%({bb_label(r.get('pct_b'))})  "
                f"MACD {momentum_label(r.get('macd'), r.get('macd_sig'), r.get('macd_hist'))}  "
                f"ATR {atr_s}  OBV {obv_label(r.get('obv_trend'), r.get('volume_reliable'))}  "
                f"피봇위치 {pivot_position_label(r.get('pivot'), r.get('curr'))}  [{r['score']['label']}]"
            )
        print()

    generate_html(results)


if __name__ == '__main__':
    main()
