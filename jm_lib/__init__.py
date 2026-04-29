"""Jason Market Library — 공용 유틸리티 및 헬퍼

각 모듈의 중복 코드를 통합하는 라이브러리.
CLAUDE.md 규칙 자동 준수 (색상, 가격 로직, 환경변수).
"""

from .colors import ALERT, AMBER, CYAN, GRAY, DIM, BOLD, RESET, GREEN, RED, WARN
from .env import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, require_api_key
from .yf_helpers import (
    classify_ticker, get_current_price, get_prev_close,
    get_open_today_utc, get_price_data,
)

__all__ = [
    # Colors
    'ALERT', 'AMBER', 'CYAN', 'GRAY', 'DIM', 'BOLD', 'RESET',
    'GREEN', 'RED', 'WARN',
    # Environment
    'ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'require_api_key',
    # YFinance helpers
    'classify_ticker', 'get_current_price', 'get_prev_close',
    'get_open_today_utc', 'get_price_data',
]

__version__ = '1.0.0'
