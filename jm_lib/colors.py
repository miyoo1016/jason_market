"""ANSI 색상 코드 — Jason Market 통합 색상 정의

CLAUDE.md 색상 규칙 준수:
- 원색 노란 (#f1c40f, 38;5;226) 금지 → 눈 아픔
- 원색 초록 (#2ecc71, 38;5;82) 금지 → 눈 아픔
- 사용 색상: CYAN (긍정), AMBER (경고), ALERT (위험)
"""

# ═══ 신호 색상 (CLAUDE.md 규칙) ═══
CYAN = '\033[36m'            # 좋음/긍정 신호 (밝은 파랑)
AMBER = '\033[38;5;214m'     # 경고 신호 (주황)
ALERT = '\033[38;5;203m'     # 위험 신호 (연한 빨간)

# ═══ 보조 색상 ═══
GRAY = '\033[38;5;243m'      # 부가 정보 (회색)
DIM = '\033[2m'              # 약화 (어두운)
BOLD = '\033[1m'             # 강조 (굵게)
RESET = '\033[0m'            # 색상 초기화

# ═══ 호환성 별칭 (기존 코드 호환) ═══
GREEN = CYAN                 # 기존 코드에서 GREEN 사용 → CYAN으로 매핑
RED = ALERT                  # 기존 코드에서 RED 사용 → ALERT로 매핑
WARN = AMBER                 # 기존 코드에서 WARN 사용 → AMBER로 매핑

__all__ = [
    'CYAN', 'AMBER', 'ALERT',
    'GRAY', 'DIM', 'BOLD', 'RESET',
    'GREEN', 'RED', 'WARN',
]
