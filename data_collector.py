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
        logger.info("📊 자산 가격 수집 중 (인베스팅닷컴 기준)...")
        from datetime import timezone
        for name, ticker in MONITORED_ASSETS.items():
            try:
                t    = yf.Ticker(ticker)
                fi   = t.fast_info

                # ── 기초 데이터 추출 (GMT 00:00 기준점 찾기) ──────────────
                prev = getattr(fi, 'previous_close', None)
                open_val = getattr(fi, 'open', None)
                
                # 글로벌 자산은 GMT 00:00 시가를 baseline으로 함
                is_global = ticker in ('GC=F', 'CL=F', 'BZ=F', 'USDKRW=X', 'BTC-USD', 'DIA', 'SPY', 'QQQM', 'IWM', '^VIX', '^TNX')
                if is_global:
                    try:
                        h_int = t.history(period='2d', interval='1h')
                        if not h_int.empty:
                            h_int.index = h_int.index.tz_convert('UTC')
                            today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                            today_data = h_int.loc[h_int.index >= today_utc]
                            if not today_data.empty:
                                open_val = float(today_data['Open'].iloc[0])
                    except: pass

                if not prev:
                    hist = t.history(period='5d')
                    if len(hist) >= 2: prev = float(hist['Close'].iloc[-2])
                    else:
                        logger.warning(f"⚠ {name}: 전일종가 없음")
                        continue

                # ── 현재가 추출 ────────────────────────────────────────────
                is_equity = ticker in ('DIA', 'SPY', 'QQQM', 'IWM', 'GOOGL') or ticker.endswith('.KS')
                curr = None
                if is_equity:
                    try:
                        h1m  = t.history(period='1d', interval='1m', prepost=True)
                        if not h1m.empty: curr = float(h1m['Close'].iloc[-1])
                    except Exception: pass
                        
                if not curr:
                    curr = getattr(fi, 'last_price', None)

                if not curr:
                    logger.warning(f"⚠ {name}: 현재가 없음")
                    continue

                # ── 스케일링 (지수 프록시) ──────────────────────
                scale = 1.0
                if ticker == 'SPY' or name == 'S&P500': scale = 10.0
                elif ticker == 'QQQM' or name == 'NASDAQ': scale = 41.15
                
                curr *= scale
                prev *= scale
                if open_val: open_val *= scale

                # ── 등락률 계산 (인베스팅 스타일) ────────────────────
                if is_global and open_val:
                    pct = (curr - open_val) / open_val * 100
                else:
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
