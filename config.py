"""설정 파일 - Jason Market"""

import os
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

# API 키
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '').strip()

# 모니터링 자산 (main.py 자동화용)
MONITORED_ASSETS = {
    'VIX':     '^VIX',
    '금':      'GC=F',
    'BTC':     'BTC-USD',
    'USD/KRW': 'USDKRW=X',
    'S&P500':  '^GSPC',
    'NASDAQ':  '^IXIC',
}

# 알림 조건
ALERT_VIX_HIGH      = 25
ALERT_VIX_CRITICAL  = 30
ALERT_GOLD_DROP_PCT = -3.0
ALERT_BTC_SUPPORT   = 69000
ALERT_BTC_RESIST    = 72000

# 자동화 시간
TRADING_START_HOUR = 8
TRADING_END_HOUR   = 22

# 인터벌 (초)
DATA_COLLECTION_INTERVAL = 60
ANALYSIS_INTERVAL        = 900   # 15분

# Claude 모델
CLAUDE_MODEL      = 'claude-haiku-4-5-20251001'
CLAUDE_MAX_TOKENS = 1200

# 로그
LOG_FILE  = 'trading_automation.log'
LOG_LEVEL = 'INFO'
