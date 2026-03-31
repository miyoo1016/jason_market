"""데이터 수집 모듈 - Jason Market"""

import json
import logging
import yfinance as yf
from datetime import datetime
from config import MONITORED_ASSETS

logger = logging.getLogger(__name__)

class DataCollector:
    def __init__(self):
        self.assets_data      = {}
        self.calendar_events  = []
        self.last_update      = None

    def collect_asset_prices(self):
        logger.info("📊 자산 가격 수집 중...")
        for name, ticker in MONITORED_ASSETS.items():
            try:
                t    = yf.Ticker(ticker)
                fi   = t.fast_info

                is_kr     = ticker.endswith('.KS') or ticker in ('^KS11',)
                is_equity = (not is_kr
                             and not ticker.endswith('=F')
                             and not ticker.endswith('=X')
                             and not ticker.startswith('^')
                             and ticker not in ('BTC-USD',))

                # 현재가
                if is_kr:
                    curr = fi.get('last_price') or fi.get('lastPrice')
                elif is_equity:
                    try:
                        h1m  = t.history(period='1d', interval='1m', prepost=True)
                        curr = float(h1m['Close'].iloc[-1]) if not h1m.empty else None
                    except Exception:
                        curr = None
                    if not curr:
                        curr = fi.get('last_price') or fi.get('lastPrice')
                else:
                    # 선물/FX/지수/크립토: fast_info 24H 실시간
                    curr = fi.get('last_price') or fi.get('lastPrice')

                curr = float(curr) if curr else None
                if not curr:
                    logger.warning(f"⚠ {name}: 현재가 없음")
                    continue

                # 전일 종가
                if is_kr or is_equity:
                    prev_fi = fi.get('previous_close') or fi.get('previousClose')
                    prev    = float(prev_fi) if prev_fi else None
                    if not prev:
                        hist = t.history(period='5d')
                        prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else None
                else:
                    hist = t.history(period='5d')
                    if hist.empty or len(hist) < 2:
                        prev_fi = fi.get('previous_close') or fi.get('previousClose')
                        prev    = float(prev_fi) if prev_fi else None
                    else:
                        daily_last = float(hist['Close'].iloc[-1])
                        if abs(curr - daily_last) / daily_last < 0.001:
                            prev = float(hist['Close'].iloc[-2])
                        else:
                            prev = daily_last

                if not prev:
                    logger.warning(f"⚠ {name}: 전일종가 없음")
                    continue

                pct = (curr - prev) / prev * 100

                self.assets_data[name] = {
                    'ticker':           ticker,
                    'current_price':    curr,
                    'prev_close':       prev,
                    'daily_change_pct': round(pct, 2),
                    'timestamp':        datetime.now().isoformat(),
                }

                arrow = '📈' if pct >= 0 else '📉'
                logger.info(f"{arrow} {name}: {curr:.2f} ({pct:+.2f}%)")

            except Exception as e:
                logger.warning(f"⚠ {name} 수집 실패: {e}")

        self.last_update = datetime.now()
        return self.assets_data

    def load_calendar_from_file(self, filepath='calendar_today.json'):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.calendar_events = json.load(f)
            logger.info(f"📅 캘린더 로드: {len(self.calendar_events)}개 이벤트")
        except FileNotFoundError:
            logger.warning("⚠ calendar_today.json 없음")
            self.calendar_events = []
        except json.JSONDecodeError as e:
            logger.warning(f"⚠ 캘린더 JSON 오류: {e}")
            self.calendar_events = []
        except Exception as e:
            logger.warning(f"⚠ 캘린더 로드 실패: {e}")
            self.calendar_events = []
        return self.calendar_events

    def get_all_data(self):
        return {
            'assets':          self.assets_data,
            'calendar':        self.calendar_events,
            'collection_time': self.last_update.isoformat() if self.last_update else None,
        }

    def collect_all(self):
        self.collect_asset_prices()
        self.load_calendar_from_file()
        return self.get_all_data()
