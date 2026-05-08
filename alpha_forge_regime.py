"""AlphaForge — Market Regime Detection Module
Classifies market into Strong, Normal, Weak, or Mixed based on VIX, S&P500 200DMA, and Korean indices.
"""

import numpy as np
from datetime import datetime
from jm_lib.yf_helpers import get_price_data, _chart, _daily_closes
from jm_lib.colors import GREEN, RED, AMBER, CYAN, RESET, ALERT

def get_spx_200dma():
    """Calculate S&P 500 200-day Moving Average"""
    res = _chart('^GSPC', interval='1d', range_='1y')
    if not res:
        return None
    closes = _daily_closes(res)
    if len(closes) < 200:
        return None
    return np.mean(closes[-200:])

def get_market_status():
    """Fetch all necessary macro indicators"""
    status = {}
    
    # 1. VIX
    vix_data = get_price_data('^VIX', is_global=True)
    status['vix'] = vix_data['curr'] if vix_data else None
    
    # 2. S&P 500 vs 200DMA
    spx_data = get_price_data('^GSPC')
    status['spx_curr'] = spx_data['curr'] if spx_data else None
    status['spx_200dma'] = get_spx_200dma()
    
    # 3. KOSPI & KOSDAQ
    kospi_data = get_price_data('^KS11')
    kosdaq_data = get_price_data('^KQ11')
    
    status['kospi_chg'] = kospi_data['pct'] if kospi_data else 0
    status['kosdaq_chg'] = kosdaq_data['pct'] if kosdaq_data else 0
    
    return status

def detect_regime(s: dict):
    """
    Classify regime based on Perplexity's criteria + some logic
    - Strong: VIX < 18 AND SPX > 200DMA AND Kospi > +0.5%
    - Normal: VIX 18~25 OR Kospi ±0.5%
    - Weak: VIX > 25 OR Kospi < -1.5%
    - Mixed: Kospi/Kosdaq opposite directions
    """
    vix = s.get('vix')
    spx = s.get('spx_curr')
    ma200 = s.get('spx_200dma')
    kp = s.get('kospi_chg', 0)
    kd = s.get('kosdaq_chg', 0)
    
    # Mixed check first
    if kp * kd < -0.01: # Significant opposite move
        return "⚠️ 혼조장", "코스닥 종목 필터링, RS 90+ 상향", "mixed"
    
    # Weak check
    if (vix and vix > 25) or kp < -1.5:
        return "🔴 약세장", "AND=진입 없음, 관심 목록만 표시", "weak"
    
    # Strong check
    if (vix and vix < 18) and (spx and ma200 and spx > ma200) and kp > 0.5:
        return "🟢 강세장", "RS 85점, VCP 70+, AND 모드", "strong"
    
    # Default to Normal
    return "🟡 보통장", "RS 88점, VCP 80+, AND 모드", "normal"

def get_tactical_advice(regime_key, results_count):
    """Returns a premium tactical message for Jason"""
    if results_count > 0:
        return f"현재 {results_count}종목이 감지되었습니다. 원칙에 따른 분할 매수를 검토하세요."
    
    if regime_key == 'weak':
        return "🚫 시스템이 당신의 자산을 지켰습니다. 하락장에서 0종목은 가장 수익률 높은 결과입니다."
    elif regime_key == 'mixed':
        return "⚠️ 개별주 장세입니다. 지수보다 강한 '생존자'들만 관심 목록에 넣으세요."
    else:
        return "🔍 조건에 딱 맞는 종목이 아직 없습니다. 무리한 진입보다 기준을 기다리는 인내가 수익입니다."

def print_regime_header():
    """Print the professional header as requested"""
    s = get_market_status()
    regime_name, preset_desc, regime_key = detect_regime(s)
    
    color = GREEN if regime_key == 'strong' else (RED if regime_key == 'weak' else (AMBER if regime_key == 'normal' else CYAN))
    
    print(f"\n{RESET}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  {color}{regime_name}{RESET}")
    print(f"   코스피 {s['kospi_chg']:+.2f}% / 코스닥 {s['kosdaq_chg']:+.2f}% / VIX {s['vix'] or 0:.2f}")
    print(f"   → 적용 모드: {preset_desc}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    return regime_key, s

if __name__ == "__main__":
    print_regime_header()
