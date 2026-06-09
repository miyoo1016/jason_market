"""포트폴리오 트래커 — 가격 조회 모듈
Yahoo Finance v8 curl 기반 (yfinance 완전 제거)
"""

import threading
import subprocess
import json
import logging
import os
import re
from datetime import datetime

from jm_lib.yf_helpers import get_price_data, _chart

logging.getLogger('yfinance').setLevel(logging.CRITICAL)


def normalize_price_key(name: str = '', ticker: str = '') -> str:
    """종목명/티커 차이를 흡수하는 canonical price key."""
    ticker = str(ticker or '').strip()
    if ticker and ticker not in ('XLSX_PRICE',):
        return ticker.upper()
    key = re.sub(r'[\s()（）·/\-]+', '', str(name or '')).upper()
    return key


def _positive_float(value):
    try:
        f = float(value)
        if f > 0 and f == f:
            return f
    except Exception:
        pass
    return None


def _num(value):
    try:
        s = str(value).replace(',', '').replace('%', '').strip()
        if not s:
            return None
        return float(re.sub(r'[^0-9.\-]', '', s))
    except Exception:
        return None


def _is_kr_listed(ticker: str) -> bool:
    return str(ticker or '').endswith(('.KS', '.KQ'))


def _kr_code(ticker: str) -> str:
    return str(ticker or '').split('.')[0].strip()


def _direction_sign(info) -> int:
    if not isinstance(info, dict):
        return 0
    text = f"{info.get('name', '')} {info.get('text', '')} {info.get('code', '')}".upper()
    if any(x in text for x in ('FALL', '하락', 'MINUS', '5')):
        return -1
    if any(x in text for x in ('RISING', 'RISE', '상승', 'PLUS', '2')):
        return 1
    return 0


def _price_source_label(entry: dict) -> str:
    source = entry.get('source') or ''
    if source == 'GoogleSheetFallback':
        return 'GoogleSheetFallback'
    if source == 'naver_live':
        return 'naver_live'
    if source == 'naver_krx_gold':
        return 'NaverKRX'
    return source or 'unknown'

# ═══ 환율 ═══

def get_usdkrw() -> tuple:
    """실시간 환율 + 전일종가 → (현재, 전일)"""
    try:
        data = get_price_data('USDKRW=X', is_global=True)
        if data and data.get('curr'):
            curr = float(data['curr'])
            prev = float(data.get('prev') or curr)
            return curr, prev
    except Exception:
        pass
    return 1450.0, 1450.0


# ═══ KRX 금현물 ═══

def _fetch_naver_kr_live(ticker: str) -> dict | None:
    """국내 상장 주식/ETF/ETN 현재가 — Naver 모바일 증권 API."""
    code = _kr_code(ticker)
    if not code:
        return None

    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '-A', 'Mozilla/5.0',
             f'https://m.stock.naver.com/api/stock/{code}/basic'],
            capture_output=True, timeout=8
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        if not isinstance(d, dict) or d.get('code') == 'StockConflict':
            return None

        over = d.get('overMarketPriceInfo') if isinstance(d.get('overMarketPriceInfo'), dict) else {}
        price = _num(over.get('overPrice')) or _num(d.get('closePrice')) or _num(d.get('currentPrice'))
        if not price or price <= 0:
            return None

        sign = _direction_sign(over.get('compareToPreviousPrice')) or _direction_sign(d.get('compareToPreviousPrice')) or 1
        diff_raw = _num(over.get('compareToPreviousClosePrice')) or _num(d.get('compareToPreviousClosePrice'))
        ratio_raw = _num(over.get('fluctuationsRatio')) or _num(d.get('fluctuationsRatio'))
        diff = diff_raw * sign if diff_raw is not None else None
        ratio = ratio_raw * sign if ratio_raw is not None else None

        prev = price - diff if diff is not None else None
        if (not prev or prev <= 0) and ratio is not None and ratio > -99:
            prev = price / (1 + ratio / 100)
        if not prev or prev <= 0:
            prev = price

        quote_time = over.get('localTradedAt') or d.get('localTradedAt')
        market_state = over.get('overMarketStatus') or d.get('marketStatus')
        read_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return {
            'curr': float(price),
            'prev': float(prev),
            'price_diag': {
                'symbol': ticker,
                'selected_price': float(price),
                'selected_field': 'naver_live.overPrice' if over.get('overPrice') else 'naver_live.closePrice',
                'market_state': market_state,
                'source': 'naver_live',
                'provider': 'naver_live',
                'quote_time': quote_time,
                'read_time': read_time,
                'is_live': True,
                'is_fallback': False,
                'stale_warning': '',
                'fallback_reason': '',
                'live_change_pct': ratio,
            }
        }
    except Exception:
        return None


def _fetch_gold_krx(usdkrw: float) -> dict:
    """KRX 금현물 — 네이버 증권 API (M04020000, 한국거래소 공식)"""
    res = {'curr': None, 'prev': None}

    def _num(v):
        try:
            return float(str(v).replace(',', '').strip())
        except Exception:
            return None

    try:
        r = subprocess.run(
            ['curl', '-s', '-A', 'Mozilla/5.0',
             'https://api.stock.naver.com/marketindex/metals/M04020000'],
            capture_output=True, timeout=10
        )
        d = json.loads(r.stdout.decode('utf-8', errors='replace'))
        price_str = d.get('closePrice') or d.get('currentPrice') or ''
        price = _num(price_str)
        if price and price > 0:
            res['curr'] = price
            prev = None
            for item in d.get('marketIndexTotalInfos') or []:
                if item.get('code') == 'lastClosePrice':
                    prev = _num(item.get('value'))
                    break
            if not prev:
                diff = _num(d.get('fluctuations')) or 0
                prev = price - diff
            if prev and prev > 0:
                res['prev'] = prev
            if os.environ.get('JM_DEBUG_PRICE') == '1':
                print(
                    "PRICE_DIAG "
                    f"symbol=GOLD_KRX selected_price={res['curr']} "
                    f"prev_close={res['prev']} source=naver_krx_gold"
                )
            res['price_diag'] = {
                'symbol': 'GOLD_KRX',
                'selected_price': res['curr'],
                'selected_field': 'naver_krx_gold.closePrice',
                'market_state': d.get('marketStatus'),
                'source': 'naver_krx_gold',
                'provider': 'naver_krx_gold',
                'quote_time': d.get('localTradedAt') or d.get('baseDate') or d.get('date'),
                'read_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_live': True,
                'is_fallback': False,
                'stale_warning': '',
                'fallback_reason': '',
            }
            return res
    except Exception:
        pass

    # fallback: GC=F curl
    try:
        r2 = _chart('GC=F')
        if r2:
            meta = r2.get('meta', {})
            gc_curr = meta.get('regularMarketPrice')
            gc_prev = meta.get('chartPreviousClose') or meta.get('previousClose')
            if gc_curr and usdkrw:
                res['curr'] = round(float(gc_curr) * usdkrw / 31.1035, 0)
                if gc_prev:
                    res['prev'] = round(float(gc_prev) * usdkrw / 31.1035, 0)
                return res
    except Exception:
        pass

    return res


# ═══ 전체 가격 조회 ═══

def fetch_all_prices(holdings: list, usdkrw: float) -> dict:
    """병렬로 모든 종목 현재가+전일종가 조회"""
    tickers = set()
    for h in holdings:
        t = h.get('ticker', '')
        if t and t not in ('CASH', 'GOLD_KRX', ''):
            tickers.add(t)

    cache = {}  # ticker -> {'curr': float, 'prev': float}
    lock = threading.Lock()

    def _store(t, curr, prev, meta=None):
        if curr is None:
            return
        with lock:
            cache[t] = {'curr': float(curr), 'prev': float(prev) if prev else float(curr)}
            if meta:
                cache[t]['price_diag'] = meta

    def _mark_failure(t, reason):
        with lock:
            cache[f'_failure_{t}'] = reason

    def _fetch_one(t):
        try:
            is_kr = _is_kr_listed(t)
            if is_kr:
                naver = _fetch_naver_kr_live(t)
                if naver and naver.get('curr'):
                    diag = naver.get('price_diag', {})
                    _store(t, naver['curr'], naver.get('prev'), diag)
                    if os.environ.get('JM_DEBUG_PRICE') == '1':
                        print(
                            "PRICE_DIAG "
                            f"symbol={diag.get('symbol')} "
                            f"selected_price={diag.get('selected_price')} "
                            f"selected_field={diag.get('selected_field')} "
                            f"market_state={diag.get('market_state')} "
                            f"source={diag.get('source')} "
                            f"quote_time={diag.get('quote_time')}"
                        )
                    return
                _mark_failure(t, 'naver_live_failed')

            data = get_price_data(t, is_global=False)
            if data and data.get('curr'):
                diag = {
                    'symbol': data.get('symbol', t),
                    'selected_price': data.get('selected_price', data.get('curr')),
                    'selected_field': data.get('selected_field'),
                    'market_state': data.get('market_state'),
                    'source': data.get('source'),
                    'quote_time': data.get('quote_time'),
                    'overnight_price_supported': data.get('overnight_price_supported'),
                    'overnight_warning': data.get('overnight_warning'),
                    'last_extended_price': data.get('last_extended_price'),
                    'last_extended_timestamp': data.get('last_extended_timestamp'),
                    'last_extended_age_sec': data.get('last_extended_age_sec'),
                    'provider': data.get('source') or 'yahoo_quote',
                    'read_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'is_live': True,
                    'is_fallback': False,
                    'stale_warning': '',
                    'fallback_reason': 'naver_live_failed; yahoo_quote_used' if is_kr else '',
                }
                _store(t, data['curr'], data.get('prev'), diag)
                if os.environ.get('JM_DEBUG_PRICE') == '1':
                    print(
                        "PRICE_DIAG "
                        f"symbol={diag['symbol']} "
                        f"selected_price={diag['selected_price']} "
                        f"selected_field={diag['selected_field']} "
                        f"market_state={diag['market_state']} "
                        f"source={diag['source']} "
                        f"quote_time={diag['quote_time']} "
                        f"overnight_price_supported={diag['overnight_price_supported']} "
                        f"overnight_warning={diag['overnight_warning']} "
                        f"last_extended_price={diag['last_extended_price']} "
                        f"last_extended_timestamp={diag['last_extended_timestamp']} "
                        f"last_extended_age_sec={diag['last_extended_age_sec']}"
                    )
        except Exception:
            _mark_failure(t, 'live_quote_exception')

    # 병렬 스레드로 모든 티커 조회
    threads = [threading.Thread(target=_fetch_one, args=(t,), daemon=True) for t in tickers]
    for th in threads:
        th.start()

    gold_result = {'curr': None, 'prev': None}
    def _gold():
        res = _fetch_gold_krx(usdkrw)
        gold_result.update(res)

    gt = threading.Thread(target=_gold, daemon=True)
    gt.start()

    for th in threads:
        th.join(timeout=20)
    gt.join(timeout=20)

    cache['GOLD_KRX_PRICE'] = gold_result
    _apply_canonical_prices(cache, holdings)
    return cache


def _apply_canonical_prices(cache: dict, holdings: list) -> None:
    """Google Sheet holdings 기준 canonical price map을 cache에 부착한다."""
    canonical = {}
    audit = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for h in holdings:
        ticker = h.get('ticker', '')
        if not ticker or ticker == 'CASH':
            continue

        name = h.get('name', ticker)
        key = normalize_price_key(name, ticker)
        cache_key = 'GOLD_KRX_PRICE' if ticker == 'GOLD_KRX' else ticker
        live = cache.get(cache_key, {})
        sheet_price = _positive_float(h.get('xlsx_price'))

        curr = live.get('curr')
        prev = live.get('prev')
        diag = live.get('price_diag', {})
        source = diag.get('source') or live.get('source') or ('yahoo_chart' if curr is not None else '')
        provider = diag.get('provider') or live.get('provider') or source
        selected_field = diag.get('selected_field') or live.get('selected_field')
        quote_time = diag.get('quote_time') or live.get('quote_time')
        read_time = diag.get('read_time') or live.get('read_time') or now
        is_live = bool(diag.get('is_live', live.get('is_live', curr is not None)))
        is_fallback = bool(diag.get('is_fallback', live.get('is_fallback', False)))
        stale_warning = diag.get('stale_warning') or live.get('stale_warning') or ''
        fallback_reason = diag.get('fallback_reason') or live.get('fallback_reason') or ''

        if curr is None and sheet_price:
            curr = sheet_price
            prev = sheet_price
            source = 'GoogleSheetFallback'
            provider = 'GoogleSheet'
            selected_field = 'xlsx_price'
            quote_time = None
            read_time = now
            is_live = False
            is_fallback = True
            stale_warning = 'LIVE_QUOTE_FAILED'
            fallback_reason = cache.get(f'_failure_{ticker}') or 'live_price_missing'

        if curr is None:
            audit.append(
                f"PRICE_MISSING key={key} name={name} ticker={ticker} "
                f"source_row={h.get('source_row', '')}"
            )
            continue

        if prev is None:
            prev = curr

        computed_pct = ((float(curr) - float(prev)) / float(prev) * 100) if prev else 0.0
        if _is_kr_listed(ticker) and source == 'GoogleSheet':
            audit.append(
                f"PRICE_SOURCE_WRONG key={key} name={name} ticker={ticker} "
                "source=GoogleSheet"
            )
        if is_fallback:
            audit.append(
                f"LIVE_QUOTE_FAILED_FALLBACK key={key} name={name} ticker={ticker} "
                f"fallback_reason={fallback_reason}"
            )
        live_pct = diag.get('live_change_pct')
        if live_pct is not None and abs(computed_pct - float(live_pct)) > 0.2:
            audit.append(
                f"CHANGE_PCT_MISMATCH key={key} name={name} ticker={ticker} "
                f"computed={computed_pct:.2f} live={float(live_pct):.2f}"
            )

        entry = {
            'canonical_key': key,
            'name': name,
            'display_name': name,
            'ticker': ticker,
            'code': _kr_code(ticker) if _is_kr_listed(ticker) else ticker,
            'asset_type': h.get('asset_type', ''),
            'price': float(curr),
            'curr': float(curr),
            'prev': float(prev),
            'prev_close': float(prev),
            'change_pct': computed_pct,
            'currency': h.get('currency', 'KRW'),
            'source': source,
            'provider': provider,
            'selected_field': selected_field,
            'quote_time': quote_time,
            'read_time': read_time,
            'is_live': is_live,
            'is_fallback': is_fallback,
            'stale_warning': stale_warning,
            'fallback_reason': fallback_reason,
            'updated_at': quote_time or read_time,
            'raw_key': h.get('source_row'),
            'raw_name': h.get('name', ''),
            'source_sheet': h.get('source_sheet'),
        }

        if key in canonical:
            old = canonical[key]
            if abs(old['price'] - entry['price']) > 1e-9:
                audit.append(
                    f"DUPLICATE_PRICE_KEY key={key} old_price={old['price']} "
                    f"new_price={entry['price']} old_name={old['name']} new_name={name}"
                )
                continue
        canonical[key] = entry

        cache[cache_key] = {
            'curr': entry['curr'],
            'prev': entry['prev'],
            'source': entry['source'],
            'provider': entry['provider'],
            'selected_field': entry['selected_field'],
            'quote_time': entry['quote_time'],
            'read_time': entry['read_time'],
            'is_live': entry['is_live'],
            'is_fallback': entry['is_fallback'],
            'stale_warning': entry['stale_warning'],
            'fallback_reason': entry['fallback_reason'],
            'updated_at': entry['updated_at'],
        }

    cache['_canonical'] = canonical
    cache['_audit'] = audit


# ═══ 단일 종목 가격 ═══

def get_price(h: dict, price_cache: dict, usdkrw: float) -> tuple:
    """단일 종목 가격 조회 → (현재가, 전일종가)"""
    ticker = h.get('ticker', '')
    if ticker == 'CASH':
        return None, None

    if ticker == 'GOLD_KRX':
        data = price_cache.get('GOLD_KRX_PRICE', {})
    else:
        data = price_cache.get(ticker, {})

    curr = data.get('curr')
    prev = data.get('prev')

    if curr is None or curr != curr:
        curr = h.get('xlsx_price')

    return curr, prev


def get_price_entry(h: dict, price_cache: dict) -> dict:
    """holding에 대응하는 canonical price entry."""
    ticker = h.get('ticker', '')
    if not ticker or ticker == 'CASH':
        return {}
    key = normalize_price_key(h.get('name', ''), ticker)
    entry = price_cache.get('_canonical', {}).get(key)
    if entry:
        return entry
    cache_key = 'GOLD_KRX_PRICE' if ticker == 'GOLD_KRX' else ticker
    data = price_cache.get(cache_key, {})
    if not data:
        return {}
    return {
        'name': h.get('name', ticker),
        'ticker': ticker,
        'price': data.get('curr'),
        'curr': data.get('curr'),
        'prev': data.get('prev'),
        'source': data.get('source') or data.get('price_diag', {}).get('source'),
        'provider': data.get('provider') or data.get('price_diag', {}).get('provider'),
        'selected_field': data.get('selected_field') or data.get('price_diag', {}).get('selected_field'),
        'quote_time': data.get('quote_time') or data.get('price_diag', {}).get('quote_time'),
        'read_time': data.get('read_time') or data.get('price_diag', {}).get('read_time'),
        'is_fallback': data.get('is_fallback') or data.get('price_diag', {}).get('is_fallback'),
        'stale_warning': data.get('stale_warning') or data.get('price_diag', {}).get('stale_warning'),
        'updated_at': data.get('updated_at'),
        'fallback_reason': data.get('fallback_reason', ''),
    }


def describe_price_basis(price_cache: dict) -> str:
    """사용 중인 canonical price map 요약."""
    canonical = price_cache.get('_canonical', {})
    sources = sorted({_price_source_label(v) for v in canonical.values() if v})
    source_s = '+'.join(sources) if sources else 'unknown'
    return (
        f"canonical live price map / {len(canonical)} items "
        f"(국내주식/ETF: naver_live 우선, 미국주식/ETF: yahoo_quote, "
        f"수동/현금: GoogleSheet; active_sources={source_s})"
    )


def print_price_audit(price_cache: dict) -> None:
    """가격 정합성 audit 결과 출력."""
    issues = price_cache.get('_audit') or []
    if issues:
        print(f"  ⚠ price audit issues={len(issues)}")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  ✅ price audit issues=0")


__all__ = [
    'get_usdkrw',
    'fetch_all_prices',
    'get_price',
    'get_price_entry',
    'describe_price_basis',
    'print_price_audit',
    'normalize_price_key',
]
