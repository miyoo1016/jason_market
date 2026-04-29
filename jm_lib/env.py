"""환경변수 및 API 키 통합 관리

.env 파일에서 로드되는 모든 API 키 및 환경 설정을 중앙화.
"""

import os
from dotenv import load_dotenv

# .env 파일 자동 로드 (최초 import 시 1회만)
load_dotenv()

# ═══ API 키 ═══
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ═══ 헬퍼 함수 ═══
def require_api_key(name: str) -> str:
    """필수 API 키 검증

    Args:
        name: 환경변수 이름

    Returns:
        API 키 값

    Raises:
        ValueError: 환경변수가 설정되지 않았을 때
    """
    key = os.getenv(name)
    if not key:
        raise ValueError(
            f"환경변수 '{name}'이 설정되지 않았습니다.\n"
            f".env 파일을 확인하거나 직접 설정하세요."
        )
    return key


__all__ = [
    'ANTHROPIC_API_KEY',
    'TELEGRAM_BOT_TOKEN',
    'TELEGRAM_CHAT_ID',
    'require_api_key',
]
