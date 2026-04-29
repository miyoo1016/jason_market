"""Jason Market Library — 공용 유틸리티 및 헬퍼

각 모듈의 중복 코드를 통합하는 라이브러리.
CLAUDE.md 규칙 자동 준수 (색상, 가격 로직, 환경변수).
"""

from .colors import ALERT, AMBER, CYAN, GRAY, DIM, BOLD, RESET, GREEN, RED, WARN

__all__ = [
    'ALERT', 'AMBER', 'CYAN', 'GRAY', 'DIM', 'BOLD', 'RESET',
    'GREEN', 'RED', 'WARN',
]

__version__ = '1.0.0'
