#!/usr/bin/env python3
"""포트폴리오 리스크 분석 - Jason Market
개별 자산 변동성/Beta/MaxDD 및 포트폴리오 VaR/Sharpe 분석
- 현금 포함 전체 평가금액 산출
- 동일 종목 계좌 통합 (합산 수량·가중 평단가)
- HTML: 종목별 리스크 카드 + 종합 지표"""

import os
import webbrowser
import tempfile
import threading
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from xlsx_sync import load_portfolio

load_dotenv()

ALERT  = '\033[38;5;203m'
RESET  = '\033[0m'
EXTREME = ['극도공포', '극도탐욕', '강력매도', '강력매수', '매우높음', '즉시청산']

def alert_line(text):
    for kw in EXTREME:
        if kw in text:
            return ALERT + text + RESET
    return text

PROXY_MAP = {
    'KODEX 나스닥100':  'QQQ',
    'KODEX S&P500':    'SPY',
    'KODEX 미국반도체': 'SOXX',
}

RISK_FREE_RATE = 0.044  # 4.4% 연간

def get_usdkrw():
    try:
        h = yf.Ticker('USDKRW=X').history(period='2d')
        return float(h['Close'].iloc[-1]) if not h.empty else 1450.0
    except Exception:
        return 1450.0

# ── 포트폴리오 로드 + 종목 통합 ──────────────────────────────

def load_holdings():
    """
    xlsx 전체 포트폴리오 로드.
    - 현금 포함 (is_cash=True)
    - 동일 (name, ticker) 중복 → 수량 합산 / 평단가 가중 평균
    반환: (합산_holdings_list, 'portfolio')
    """
    raw = load_portfolio()
    if not raw:
        return [], 'empty'

    # 동일 종목 통합 (key = (name, ticker))
    merged = {}
    for h in raw:
        is_cash = h.get('is_cash', False) or h.get('ticker') == 'CASH'
        ticker  = h.get('ticker', '')
        name    = h.get('name', '')
        qty     = float(h.get('qty', 0))
        avg     = float(h.get('avg_price', 0))
        cur     = h.get('currency', 'KRW')
        key     = (name, ticker)

        if is_cash:
            # 현금: avg_price = 금액, qty = 1
            cash_amt = avg  # qty=1 이므로 avg_price 자체가 금액
            acc      = h.get('account', '')
            if key in merged:
                merged[key]['avg_price'] += cash_amt
                if acc and acc not in merged[key]['accounts']:
                    merged[key]['accounts'].append(acc)
            else:
                merged[key] = {
                    'name': name, 'ticker': ticker,
                    'qty': 1, 'avg_price': cash_amt,
                    'xlsx_price': None, 'currency': cur,
                    'is_cash': True,
                    'accounts': [acc] if acc else []
                }
            continue

        if qty <= 0:
            continue

        xlsx_price = h.get('xlsx_price')
        if key in merged:
            prev = merged[key]
            total_qty = prev['qty'] + qty
            prev['avg_price'] = (prev['avg_price'] * prev['qty'] + avg * qty) / total_qty
            prev['qty'] = total_qty
            prev['accounts'].append(h.get('account', ''))
            if xlsx_price and not prev.get('xlsx_price'):
                prev['xlsx_price'] = xlsx_price
        else:
            merged[key] = {
                'name': name, 'ticker': ticker,
                'qty': qty, 'avg_price': round(avg, 4),
                'xlsx_price': xlsx_price, 'currency': cur,
                'is_cash': False,
                'accounts': [h.get('account', '')]
            }

    return list(merged.values()), 'portfolio'

# ── 데이터 조회 ──────────────────────────────────────────────

def get_benchmark_returns():
    """S&P500 KRW기준 수익률 + USDKRW 일간 수익률 반환 (Beta/VaR 정확도 향상)"""
    try:
        spy_hist = yf.Ticker('^GSPC').history(period='1y')
        fx_hist  = yf.Ticker('USDKRW=X').history(period='1y')
        if spy_hist.empty or fx_hist.empty:
            return None, None
        spy_ret = spy_hist['Close'].pct_change().dropna()
        fx_ret  = fx_hist['Close'].pct_change().dropna()
        # 인덱스 정규화 (날짜만, tz-naive)
        spy_ret.index = pd.to_datetime(spy_ret.index).normalize().tz_localize(None) \
                        if spy_ret.index.tzinfo else pd.to_datetime(spy_ret.index).normalize()
        fx_ret.index  = pd.to_datetime(fx_ret.index).normalize().tz_localize(None) \
                        if fx_ret.index.tzinfo else pd.to_datetime(fx_ret.index).normalize()
        common = spy_ret.index.intersection(fx_ret.index)
        spy_krw = spy_ret.loc[common] + fx_ret.loc[common]   # KRW 기준 S&P500
        return spy_krw, fx_ret.loc[common]
    except Exception:
        return None, None

def get_risk_metrics(holding, spy_krw_returns, usdkrw_daily, usdkrw):
    ticker   = holding['ticker']
    name     = holding['name']
    currency = holding['currency']
    qty      = holding['qty']
    is_cash  = holding.get('is_cash', False)

    result = {
        'name': name, 'ticker': ticker, 'qty': qty,
        'avg_price': holding['avg_price'], 'currency': currency,
        'is_cash': is_cash, 'accounts': holding.get('accounts', []),
        'current_price': None, 'ann_vol': None, 'beta': None,
        'max_dd': None, 'pos_52w': None, 'daily_ret': None,
        'market_val': 0,
    }

    # ── 현금 처리 ─────────────────────────────────────────────
    if is_cash:
        cash_krw = holding['avg_price'] if currency == 'KRW' else holding['avg_price'] * usdkrw
        result['current_price'] = holding['avg_price']
        result['ann_vol']   = 0.0
        result['beta']      = 0.0
        result['max_dd']    = 0.0
        result['pos_52w']   = 100.0
        result['market_val'] = cash_krw / usdkrw   # USD 환산
        return result

    # ── 일반 종목 처리 ────────────────────────────────────────
    if ticker == 'XLSX_PRICE':
        fetch_ticker = PROXY_MAP.get(name, 'SPY')
    elif ticker == 'GOLD_KRX':
        fetch_ticker = 'GC=F'   # 변동성/Beta 계산용 프록시 (국제 금 선물)
    else:
        fetch_ticker = ticker

    # KRX 금현물 현재가: 네이버 API 직접 조회
    gold_krx_price = None
    if ticker == 'GOLD_KRX':
        import subprocess as _sp, json as _json
        try:
            _r = _sp.run(
                ['curl', '-s', '-A', 'Mozilla/5.0',
                 'https://api.stock.naver.com/marketindex/metals/M04020000'],
                capture_output=True, timeout=10
            )
            _d = _json.loads(_r.stdout.decode('utf-8', errors='replace'))
            _ps = _d.get('closePrice') or _d.get('currentPrice') or ''
            _p = float(_ps.replace(',', ''))
            if _p > 0:
                gold_krx_price = _p
        except Exception:
            pass

    try:
        hist = yf.Ticker(fetch_ticker).history(period='1y')
        if hist is None or hist.empty or len(hist) < 20:
            return result

        close       = hist['Close'].dropna()
        fetch_price = float(close.iloc[-1])

        # 미국/글로벌 티커: 1분봉 prepost로 실시간 현재가 갱신 (KRW 자산·GOLD_KRX 제외)
        _is_kr = fetch_ticker.endswith('.KS') or fetch_ticker in ('^KS11',)
        if not _is_kr and ticker not in ('XLSX_PRICE', 'GOLD_KRX'):
            try:
                h1m = yf.Ticker(fetch_ticker).history(period='1d', interval='1m', prepost=True)
                if not h1m.empty:
                    fetch_price = float(h1m['Close'].iloc[-1])
            except Exception:
                pass

        if ticker == 'XLSX_PRICE':
            result['current_price'] = float(holding['xlsx_price']) if holding.get('xlsx_price') else fetch_price
        elif ticker == 'GOLD_KRX':
            # 네이버 KRX 공식 시세 우선, 없으면 GC=F 계산
            result['current_price'] = gold_krx_price if gold_krx_price else round(fetch_price * usdkrw / 31.1035, 0)
        else:
            result['current_price'] = fetch_price

        # 기본 일간 수익률
        daily_ret = close.pct_change().dropna()

        # ── KRW 기준 수익률 전환 ─────────────────────────────────
        # XLSX_PRICE proxy(QQQ/SPY 등)는 실제로 한국 ETF → KRW 자산
        is_krw_asset = (ticker == 'XLSX_PRICE' or
                        fetch_ticker.endswith('.KS') or
                        fetch_ticker == '^KS11')

        # 인덱스 정규화 (날짜만, tz-naive)
        dr_base = daily_ret.copy()
        dr_base.index = (pd.to_datetime(dr_base.index).normalize().tz_localize(None)
                         if dr_base.index.tzinfo
                         else pd.to_datetime(dr_base.index).normalize())

        daily_ret_krw = dr_base  # KRW 자산은 그대로
        if not is_krw_asset and usdkrw_daily is not None and len(usdkrw_daily) > 0:
            # USD 자산: return_KRW ≈ return_USD + return_USDKRW
            common_fx = dr_base.index.intersection(usdkrw_daily.index)
            if len(common_fx) >= 10:
                daily_ret_krw = dr_base.loc[common_fx] + usdkrw_daily.loc[common_fx]

        # 연간 변동성 (KRW 기준)
        result['daily_ret'] = daily_ret_krw
        result['ann_vol']   = float(daily_ret_krw.std() * np.sqrt(252) * 100)

        # Beta (KRW 기준 SPY 대비)
        if spy_krw_returns is not None:
            common = daily_ret_krw.index.intersection(spy_krw_returns.index)
            if len(common) >= 20:
                dr_c = daily_ret_krw.loc[common].values
                sp_c = spy_krw_returns.loc[common].values
                cov  = np.cov(dr_c, sp_c)[0][1]
                var  = np.var(sp_c)
                result['beta'] = round(cov / var, 2) if var != 0 else None

        # Max Drawdown
        rolling_max    = close.cummax()
        dd             = (close - rolling_max) / rolling_max * 100
        result['max_dd'] = round(float(dd.min()), 2)

        # 52주 위치 (프록시 기준)
        ref_price = fetch_price  # 항상 프록시/실제 시세 기준
        high52 = float(close.max())
        low52  = float(close.min())
        if high52 != low52:
            result['pos_52w'] = round((ref_price - low52) / (high52 - low52) * 100, 1)

        # 시장 가치 (USD)
        curr_price = result['current_price']
        if currency == 'KRW':
            result['market_val'] = qty * curr_price / usdkrw
        else:
            result['market_val'] = qty * curr_price

    except Exception:
        pass

    return result

# ── 포트폴리오 종합 지표 ─────────────────────────────────────

def calc_portfolio_risk(metrics_list):
    total_val = sum(m['market_val'] for m in metrics_list)
    if total_val == 0:
        return {}

    # 리스크 지표 계산에서 현금 제외 (변동성, Beta, VaR)
    risky = [m for m in metrics_list if not m.get('is_cash')]
    risky_val = sum(m['market_val'] for m in risky)
    weights_all = [m['market_val'] / total_val for m in metrics_list]

    if not risky or risky_val == 0:
        return {'total_val': total_val, 'port_vol': 0, 'port_beta': 0,
                'var_95': 0, 'var_99': 0, 'sharpe': None, 'weights': weights_all}

    risky_weights = [m['market_val'] / risky_val for m in risky]

    # 가중 평균 변동성
    vols = [(w, m['ann_vol']) for w, m in zip(risky_weights, risky) if m['ann_vol'] is not None]
    if vols:
        w_sum    = sum(w for w, _ in vols)
        port_vol = sum(w * v for w, v in vols) / w_sum
    else:
        port_vol = None

    # 가중 평균 Beta
    betas = [(w, m['beta']) for w, m in zip(risky_weights, risky) if m['beta'] is not None]
    if betas:
        w_sum     = sum(w for w, _ in betas)
        port_beta = sum(w * b for w, b in betas) / w_sum
    else:
        port_beta = None

    # VaR (리스크 자산 기준)
    var_95 = var_99 = None
    if port_vol is not None:
        daily_vol = port_vol / 100 / np.sqrt(252)
        var_95 = -risky_val * 1.645 * daily_vol
        var_99 = -risky_val * 2.326 * daily_vol

    # Sharpe
    sharpe = None
    try:
        rets = []
        for w, m in zip(risky_weights, risky):
            dr = m.get('daily_ret')
            if dr is not None and len(dr) > 0:
                rets.append((w, float(dr.mean()) * 252 * 100))
        if rets:
            w_sum       = sum(w for w, _ in rets)
            port_ann_ret = sum(w * r for w, r in rets) / w_sum
            if port_vol and port_vol > 0:
                sharpe = round((port_ann_ret - RISK_FREE_RATE * 100) / port_vol, 2)
    except Exception:
        pass

    return {
        'total_val':  total_val,
        'risky_val':  risky_val,
        'port_vol':   port_vol,
        'port_beta':  port_beta,
        'var_95':     var_95,
        'var_99':     var_99,
        'sharpe':     sharpe,
        'weights':    weights_all,
    }

# ── 터미널 출력 ──────────────────────────────────────────────

def print_terminal(metrics_list, stats, usdkrw):
    tv     = stats.get('total_val', 0)
    pv     = stats.get('port_vol')
    pb     = stats.get('port_beta')
    v95    = stats.get('var_95')
    v99    = stats.get('var_99')
    sr     = stats.get('sharpe')
    rv     = stats.get('risky_val', tv)

    # 종목 먼저, 현금 나중에
    stocks = [m for m in metrics_list if not m.get('is_cash')]
    cashes = [m for m in metrics_list if m.get('is_cash')]

    print(f"\n  모드: 실제 포트폴리오  (환율 ₩{usdkrw:,.0f})")
    print(f"\n  [ 투자 종목 리스크 ]  ※ 변동성·Beta·VaR = KRW 기준")
    print(f"  {'─'*80}")
    print(f"  {'종목':<18} {'현재가':>12} {'비중':>6} {'변동성':>8} {'Beta':>6} {'MaxDD':>8} {'52주':>6}")
    print(f"  {'─'*80}")

    for m in stocks:
        cp    = f"${m['current_price']:,.2f}" if m['current_price'] else 'N/A'
        wt    = f"{m['market_val']/tv*100:.1f}%" if tv else ''
        vol_s = f"{m['ann_vol']:.1f}%" if m['ann_vol'] is not None else 'N/A'
        bet_s = f"{m['beta']:.2f}"   if m['beta']    is not None else 'N/A'
        mdd_s = f"{m['max_dd']:.1f}%" if m['max_dd']  is not None else 'N/A'
        pos_s = f"{m['pos_52w']:.0f}%" if m['pos_52w'] is not None else 'N/A'
        line  = f"  {m['name']:<18} {cp:>12} {wt:>6} {vol_s:>8} {bet_s:>6} {mdd_s:>8} {pos_s:>6}"
        if m['ann_vol'] and m['ann_vol'] > 40:
            line += alert_line('  ⚠높음')
        elif m['beta'] and m['beta'] > 1.5:
            line += alert_line('  ⚠높음')
        print(line)

    if cashes:
        print(f"  {'─'*80}")
        print(f"  {'현금 자산':<18} {'금액':>12} {'비중':>6} {'변동성':>8}")
        print(f"  {'─'*80}")
        for m in cashes:
            amt = m['avg_price']
            sym = '₩' if m['currency'] == 'KRW' else '$'
            cp  = f"{sym}{amt:,.0f}"
            wt  = f"{m['market_val']/tv*100:.1f}%" if tv else ''
            print(f"  {m['name']:<18} {cp:>12} {wt:>6}   0.0%   (무위험)")

    print(f"\n  [ 포트폴리오 종합 ]")
    print(f"  {'─'*55}")
    print(f"  총 평가금액 (현금 포함) : ${tv:,.0f}  /  ₩{tv*usdkrw:,.0f}")
    print(f"  투자 자산              : ${rv:,.0f}")
    cash_val = tv - rv
    if cash_val > 0:
        print(f"  현금                   : ${cash_val:,.0f}  /  ₩{cash_val*usdkrw:,.0f}")
    print(f"  연간 변동성 (투자자산) : {f'{pv:.1f}%' if pv else 'N/A'}")
    print(f"  포트폴리오 Beta        : {f'{pb:.2f}' if pb else 'N/A'}")
    if v95 is not None:
        pct95 = v95 / rv * 100 if rv else 0
        print(f"  1일 VaR 95%           : ${v95:,.0f}  ({pct95:.2f}%)")
        if abs(pct95) > 5:
            print(alert_line("  ⚠ VaR이 투자자산의 5% 초과 — 매우높음 리스크"))
    if v99 is not None:
        pct99 = v99 / rv * 100 if rv else 0
        print(f"  1일 VaR 99%           : ${v99:,.0f}  ({pct99:.2f}%)")
    print(f"  Sharpe Ratio           : {f'{sr:.2f}' if sr is not None else 'N/A'}")
    print()

# ── HTML 생성 ────────────────────────────────────────────────

def generate_html(metrics_list, stats, timestamp, usdkrw):
    tv    = stats.get('total_val', 0)
    rv    = stats.get('risky_val', tv)
    pv    = stats.get('port_vol')
    pb    = stats.get('port_beta')
    v95   = stats.get('var_95')
    v99   = stats.get('var_99')
    sr    = stats.get('sharpe')
    wts   = stats.get('weights', [1/max(len(metrics_list),1)] * len(metrics_list))

    pv_s  = f"{pv:.1f}%" if pv is not None else 'N/A'
    pb_s  = f"{pb:.2f}" if pb is not None else 'N/A'
    v95_s = f"${v95:,.0f}<br><small>({v95/rv*100:.2f}%)</small>" if v95 and rv else 'N/A'
    v99_s = f"${v99:,.0f}<br><small>({v99/rv*100:.2f}%)</small>" if v99 and rv else 'N/A'
    sr_s  = f"{sr:.2f}" if sr is not None else 'N/A'

    def vol_color(v):
        if v is None: return '#999'
        if v == 0:    return '#3498db'
        if v > 50:    return '#e74c3c'
        if v > 30:    return '#e67e22'
        if v > 15:    return '#f39c12'
        return '#2ecc71'

    def beta_color(b):
        if b is None: return '#999'
        if b == 0:    return '#3498db'
        if b > 1.5:   return '#e74c3c'
        if b > 1.0:   return '#e67e22'
        if b < 0:     return '#9b59b6'
        return '#27ae60'

    stocks = [m for m in metrics_list if not m.get('is_cash')]
    cashes = [m for m in metrics_list if m.get('is_cash')]

    # ── 투자 종목 카드 ──────────────────────────────────────
    stock_cards = []
    COLORS = ['#3498db','#2ecc71','#e67e22','#9b59b6','#e74c3c',
              '#1abc9c','#f39c12','#34495e','#e91e63','#00bcd4','#8bc34a','#ff5722']
    color_map = {m['name']: COLORS[i % len(COLORS)] for i, m in enumerate(metrics_list)}

    for m, w in zip(metrics_list, wts):
        if m.get('is_cash'):
            continue
        cp    = f"${m['current_price']:,.2f}" if m['current_price'] else 'N/A'
        cost  = m['qty'] * m['avg_price']
        curr_val_krw = m['market_val'] * usdkrw
        wt_s  = f"{w*100:.1f}%"
        mv_s  = f"₩{curr_val_krw:,.0f}"
        vol_v = m['ann_vol'] or 0
        vol_s = f"{vol_v:.1f}%"
        bet_s = f"{m['beta']:.2f}" if m['beta'] is not None else 'N/A'
        mdd_s = f"{m['max_dd']:.1f}%" if m['max_dd'] is not None else 'N/A'
        pos_v = m['pos_52w'] or 50
        pos_s = f"{pos_v:.0f}%"
        bar_w = min(vol_v, 100)
        accs  = ', '.join(m.get('accounts', []))
        qty_s = f"{m['qty']:.0f}주" if m['currency'] == 'KRW' else f"{m['qty']:.4f}주"

        warn = ''
        if m['ann_vol'] and m['ann_vol'] > 40:
            warn = '<div class="extreme-warn">⚠ 변동성 매우높음</div>'
        elif m['beta'] and m['beta'] > 1.5:
            warn = '<div class="extreme-warn">⚠ Beta 매우높음</div>'

        col = color_map.get(m['name'], '#3498db')
        stock_cards.append(f"""
  <div class="risk-card">
    <div class="card-head">
      <span class="asset-dot" style="background:{col}"></span>
      <span class="asset-name">{m['name']}</span>
      <span class="ticker-badge">{m['ticker'] if m['ticker'] not in ('XLSX_PRICE','GOLD_KRX') else m['name']}</span>
    </div>
    {warn}
    <div class="price-row">
      <span class="price">{cp}</span>
      <span class="weight-badge">{wt_s}</span>
    </div>
    <div class="mv-row">{mv_s} &nbsp;|&nbsp; {qty_s} &nbsp;|&nbsp; {accs}</div>
    <div class="metric-row">
      <span class="metric-label">연간변동성</span>
      <div class="bar-wrap"><div class="bar-fill" style="width:{bar_w:.0f}%;background:{vol_color(m['ann_vol'])}"></div></div>
      <span class="metric-val" style="color:{vol_color(m['ann_vol'])}">{vol_s}</span>
    </div>
    <div class="stat-grid">
      <div><span class="sl">Beta</span><span class="sv" style="color:{beta_color(m['beta'])}">{bet_s}</span></div>
      <div><span class="sl">Max DD</span><span class="sv" style="color:#e74c3c">{mdd_s}</span></div>
      <div style="grid-column:1/-1"><span class="sl">52주 위치</span>
        <div class="pos-track"><div class="pos-dot" style="left:calc({pos_v:.0f}% - 6px)"></div></div>
        <span class="sv">{pos_s}</span>
      </div>
    </div>
  </div>""")

    # ── 현금 카드 ──────────────────────────────────────────
    cash_cards = []
    for m, w in zip(metrics_list, wts):
        if not m.get('is_cash'):
            continue
        amt    = m['avg_price']
        sym    = '₩' if m['currency'] == 'KRW' else '$'
        amt_s  = f"{sym}{amt:,.0f}"
        wt_s   = f"{w*100:.1f}%"
        accs   = ', '.join(m.get('accounts', []))
        col    = color_map.get(m['name'], '#95a5a6')
        cash_cards.append(f"""
  <div class="cash-card">
    <div class="card-head">
      <span class="asset-dot" style="background:{col}"></span>
      <span class="asset-name">{m['name']}</span>
      <span class="cash-badge">현금</span>
    </div>
    <div class="price-row">
      <span class="price">{amt_s}</span>
      <span class="weight-badge">{wt_s}</span>
    </div>
    <div class="mv-row">{accs}</div>
    <div style="font-size:11px;color:#27ae60;font-weight:700;margin-top:8px">변동성 0% &nbsp;·&nbsp; Beta 0 &nbsp;·&nbsp; 무위험</div>
  </div>""")

    # ── 비중 바 ────────────────────────────────────────────
    weight_bars = ''
    weight_legends = ''
    for i, (m, w) in enumerate(zip(metrics_list, wts)):
        c = color_map.get(m['name'], '#888')
        weight_bars += f'<div class="wbar" style="width:{w*100:.2f}%;background:{c}" title="{m["name"]}: {w*100:.1f}%"></div>'
        weight_legends += f'<span class="wleg"><span class="wdot" style="background:{c}"></span>{m["name"]} {w*100:.1f}%</span>'

    var_warn_html = ''
    if v95 and rv and abs(v95 / rv) > 0.05:
        var_warn_html = '<div class="var-warn">⚠ VaR이 투자자산의 5% 초과 — 리스크 매우높음</div>'

    cash_total_krw = sum(m['market_val'] * usdkrw for m in cashes)
    cash_total_usd = sum(m['market_val'] for m in cashes)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Jason Market — 포트폴리오 리스크</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#222}}
.header{{background:#1a1a2e;color:#fff;padding:20px 28px}}
.header h1{{font-size:20px;font-weight:700}}
.header .sub{{font-size:12px;color:#aaa;margin-top:4px}}
.container{{max-width:1300px;margin:0 auto;padding:20px 16px 60px}}

/* 종합 지표 */
.summary-bar{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
.sbox{{background:#fff;border-radius:10px;padding:14px 16px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.sbox.highlight{{background:#1a1a2e;color:#fff}}
.sbox .sl{{font-size:11px;color:#999;margin-bottom:6px}}
.sbox.highlight .sl{{color:#aaa}}
.sbox .sv{{font-size:20px;font-weight:800;line-height:1.2}}
.sbox .sv2{{font-size:12px;color:#888;margin-top:3px}}
.sbox.highlight .sv2{{color:#aaa}}
.sbox.red{{background:#fde8e8}}
.sbox.red .sv{{color:#c0392b}}
.var-warn{{background:#c0392b;color:#fff;border-radius:8px;padding:10px 16px;
           font-size:13px;font-weight:700;margin-bottom:16px}}

/* 섹션 */
.sec-title{{font-size:15px;font-weight:700;color:#1a1a2e;margin:20px 0 12px}}

/* 종목 카드 그리드 */
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:20px}}
.risk-card{{background:#fff;border-radius:10px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.cash-card{{background:#f8fff8;border:1px solid #c3e6cb;border-radius:10px;padding:14px}}
.card-head{{display:flex;align-items:center;gap:6px;margin-bottom:6px}}
.asset-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.asset-name{{font-size:13px;font-weight:700;flex:1}}
.ticker-badge{{background:#eef;color:#336;padding:2px 7px;border-radius:6px;font-size:10px;font-weight:600}}
.cash-badge{{background:#d4edda;color:#155724;padding:2px 7px;border-radius:6px;font-size:10px;font-weight:600}}
.extreme-warn{{background:#fde8e8;color:#c0392b;border-radius:4px;padding:3px 8px;
               font-size:11px;font-weight:700;margin-bottom:6px}}
.price-row{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}}
.price{{font-size:17px;font-weight:700}}
.weight-badge{{background:#f0f0f0;padding:2px 8px;border-radius:10px;font-size:11px;color:#666;font-weight:600}}
.mv-row{{font-size:11px;color:#888;margin-bottom:8px}}
.metric-row{{display:flex;align-items:center;gap:6px;margin-bottom:8px}}
.metric-label{{font-size:11px;color:#888;width:60px;flex-shrink:0}}
.bar-wrap{{flex:1;background:#f0f0f0;border-radius:3px;height:7px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px}}
.metric-val{{font-size:12px;font-weight:700;width:42px;text-align:right;flex-shrink:0}}
.stat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
.stat-grid>div{{background:#f8f8f8;border-radius:6px;padding:6px 8px}}
.sl{{display:block;font-size:10px;color:#999;margin-bottom:1px}}
.sv{{font-size:13px;font-weight:700}}
.pos-track{{position:relative;height:4px;background:#e0e0e0;border-radius:2px;margin:4px 0}}
.pos-dot{{position:absolute;width:12px;height:12px;border-radius:50%;background:#3498db;top:-4px}}

/* 비중 바 */
.wbar-section{{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:20px}}
.wbar-track{{display:flex;height:22px;border-radius:6px;overflow:hidden;margin:10px 0}}
.wbar{{height:100%}}
.wleg-wrap{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}
.wleg{{font-size:11px;color:#555;display:flex;align-items:center;gap:4px}}
.wdot{{width:9px;height:9px;border-radius:50%;flex-shrink:0}}

/* 가이드 */
.guide{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:20px}}
.gitem{{background:#fff;border-radius:8px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.gitem h4{{font-size:12px;font-weight:700;margin-bottom:5px;color:#444}}
.gitem p{{font-size:11px;color:#666;line-height:1.55}}
.footer{{text-align:center;font-size:11px;color:#bbb;margin-top:30px}}
</style>
</head>
<body>
<div class="header">
  <h1>Jason Market — 포트폴리오 리스크 분석</h1>
  <div class="sub">업데이트: {timestamp} &nbsp;|&nbsp; 환율 ₩{usdkrw:,.0f}/USD &nbsp;|&nbsp; ※ 변동성·Beta·VaR = KRW 기준</div>
</div>
<div class="container">

  <!-- 종합 지표 -->
  {var_warn_html}
  <div class="summary-bar">
    <div class="sbox highlight">
      <div class="sl">총 평가금액</div>
      <div class="sv">₩{tv*usdkrw:,.0f}</div>
      <div class="sv2">${tv:,.0f} (현금 포함)</div>
    </div>
    <div class="sbox">
      <div class="sl">현금 보유</div>
      <div class="sv">₩{cash_total_krw:,.0f}</div>
      <div class="sv2">${cash_total_usd:,.0f} · {cash_total_krw/(tv*usdkrw)*100:.1f}%</div>
    </div>
    <div class="sbox">
      <div class="sl">연간변동성 (투자)</div>
      <div class="sv">{pv_s}</div>
    </div>
    <div class="sbox">
      <div class="sl">Beta</div>
      <div class="sv">{pb_s}</div>
    </div>
    <div class="sbox red">
      <div class="sl">1일 VaR 95%</div>
      <div class="sv">{v95_s}</div>
    </div>
    <div class="sbox red">
      <div class="sl">1일 VaR 99%</div>
      <div class="sv">{v99_s}</div>
    </div>
    <div class="sbox">
      <div class="sl">Sharpe Ratio</div>
      <div class="sv">{sr_s}</div>
    </div>
  </div>

  <!-- 자산 비중 -->
  <div class="wbar-section">
    <div style="font-size:13px;font-weight:700;color:#333">자산 비중 (현금 포함)</div>
    <div class="wbar-track">{weight_bars}</div>
    <div class="wleg-wrap">{weight_legends}</div>
  </div>

  <!-- 투자 종목 카드 -->
  <div class="sec-title">투자 종목 리스크 &nbsp;<span style="font-size:12px;color:#888;font-weight:400">(계좌 통합 합산)</span></div>
  <div class="cards-grid">{''.join(stock_cards)}</div>

  <!-- 현금 -->
  {'<div class="sec-title">현금 보유 현황</div><div class="cards-grid">' + "".join(cash_cards) + "</div>" if cash_cards else ''}

  <!-- 리스크 가이드 -->
  <div class="guide">
    <div class="gitem"><h4>연간 변동성</h4><p>&lt;15%: 안정 &nbsp;|&nbsp; 15~30%: 보통<br>30~50%: 높음 &nbsp;|&nbsp; &gt;50%: 매우높음</p></div>
    <div class="gitem"><h4>Beta</h4><p>&lt;0.5: 저위험 &nbsp;|&nbsp; 0.5~1: 시장 수준<br>1~1.5: 높음 &nbsp;|&nbsp; &gt;1.5: 매우높음</p></div>
    <div class="gitem"><h4>VaR (투자자산 기준)</h4><p>1일 최대 손실 추정치 (정규분포 가정)<br>5% 초과 시 리스크 경고</p></div>
    <div class="gitem"><h4>Sharpe Ratio</h4><p>&lt;0: 손실 &nbsp;|&nbsp; 0~1: 보통<br>1~2: 양호 &nbsp;|&nbsp; &gt;2: 우수</p></div>
  </div>

  <div class="footer">Jason Market · {timestamp}</div>
</div>
<button id="copy-btn" onclick="copyReport()" style="position:fixed;bottom:22px;right:22px;z-index:9999;padding:10px 20px;background:#1a5fa8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;box-shadow:0 3px 12px rgba(0,0,0,.3)">📋 전체 복사</button>
<script>
function copyReport(){{var el=document.querySelector('.page,.main-content,main')||document.body;navigator.clipboard.writeText(el.innerText).then(function(){{var b=document.getElementById('copy-btn');b.textContent='✅ 복사 완료!';b.style.background='#2e7d32';setTimeout(function(){{b.textContent='📋 전체 복사';b.style.background='#1a5fa8';}},2500);}}).catch(function(){{var t=document.createElement('textarea');t.value=el.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);}});}}
</script>
</body>
</html>"""
    return html

# ── 메인 ─────────────────────────────────────────────────────

def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'━'*60}")
    print(f"  Jason 포트폴리오 리스크 분석   {timestamp}")
    print(f"{'━'*60}")
    print("  데이터 수집 중 (약 20초)...")

    holdings, mode = load_holdings()
    if mode == 'empty' or not holdings:
        print("  xlsx 데이터 없음. 구글드라이브 연결을 확인하세요.")
        return

    usdkrw                   = get_usdkrw()
    spy_krw_rets, usdkrw_daily = get_benchmark_returns()

    results = [None] * len(holdings)

    def fetch(i, h):
        results[i] = get_risk_metrics(h, spy_krw_rets, usdkrw_daily, usdkrw)

    threads = [threading.Thread(target=fetch, args=(i, h), daemon=True) for i, h in enumerate(holdings)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=60)

    metrics_list = [r for r in results if r is not None]
    if not metrics_list:
        print("  데이터 수집 실패")
        return

    stats = calc_portfolio_risk(metrics_list)
    print_terminal(metrics_list, stats, usdkrw)

    html = generate_html(metrics_list, stats, timestamp, usdkrw)
    tmp  = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False,
        prefix='portfolio_risk_', encoding='utf-8'
    )
    tmp.write(html)
    tmp.close()
    print(f"  HTML 저장: {tmp.name}")
    webbrowser.open(f'file://{tmp.name}')
    print("  브라우저 오픈 완료\n")

if __name__ == '__main__':
    main()
