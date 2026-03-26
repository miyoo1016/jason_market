"""
data_collector.py - 실시간 데이터 수집
"""

import yfinance as yf
import logging
from datetime import datetime
from config import MONITORED_ASSETS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataCollector:
    def __init__(self):
        self.assets_data = {}
        self.news_data = []
        self.calendar_events = []
        self.last_collection_time = None
    
    def collect_asset_prices(self):
        logger.info("📊 자산 가격 수집 중...")
        
        for asset_name, ticker in MONITORED_ASSETS.items():
            try:
                data = yf.download(ticker, period='10d', progress=False)
                
                if data.shape[0] > 0:
                    current_price = data['Close'].iloc[-1].item()
                    prev_close = data['Close'].iloc[-2].item() if data.shape[0] > 1 else current_price
                    first_close = data['Close'].iloc[0].item()
                    
                    daily_change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close != 0 else 0
                    five_day_change = ((current_price - first_close) / first_close * 100) if first_close != 0 else 0
                    ma_5 = data['Close'].tail(5).mean().item()
                    
                    self.assets_data[asset_name] = {
                        'ticker': ticker,
                        'current_price': current_price,
                        'prev_close': prev_close,
                        'daily_change_pct': round(daily_change_pct, 2),
                        'five_day_change_pct': round(five_day_change, 2),
                        'ma_5': ma_5,
                        'timestamp': datetime.now().isoformat(),
                    }
                    
                    symbol = "📈" if daily_change_pct >= 0 else "📉"
                    logger.info(f"{symbol} {asset_name}: {current_price:.2f} ({daily_change_pct:+.2f}%)")
                    
            except Exception as e:
                logger.warning(f"❌ {asset_name} 수집 실패: {str(e)}")
        
        self.last_collection_time = datetime.now()
        return self.assets_data
    
    def load_calendar_from_file(self, filepath='calendar_today.json'):
        import json
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.calendar_events = json.load(f)
            return self.calendar_events
        except:
            return []
    
    def get_all_data(self):
        return {
            'assets': self.assets_data,
            'news': self.news_data,
            'calendar': self.calendar_events,
            'collection_time': self.last_collection_time.isoformat() if self.last_collection_time else None,
        }
    
    def collect_all(self, include_economic=False):
        logger.info("=" * 50)
        logger.info("🚀 전체 데이터 수집 시작")
        logger.info("=" * 50)
        
        self.collect_asset_prices()
        self.load_calendar_from_file()
        
        logger.info("=" * 50)
        logger.info("✅ 데이터 수집 완료")
        logger.info("=" * 50)
        
        return self.get_all_data()
