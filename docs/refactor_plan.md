# Jason Market — 리팩토링 설계도

> **작성일**: 2026-04-29
> **목표**: 17개 모듈에 산재된 중복 코드를 `jm_lib/` 공용 패키지로 통합
> **원칙**: 기능 변경 없음 (오직 구조 정리)

---

## 1. 중복 코드 분석 결과

### 1-1. ANSI 색상 정의 (16개 모듈에서 중복) 🔴 최우선

**현재 상태**:
```python
# 각 모듈마다 반복되는 패턴
ALERT = '\033[38;5;203m'  # 연한 빨간색
AMBER = '\033[38;5;214m'
CYAN  = '\033[36m'
RESET = '\033[0m'
```

**중복 모듈 (16개)**:
- alpha_hunter, auto_analysis, chart_viewer, correlation_matrix
- fear_greed, macro_dashboard, market_stress, multi_agent_analyst
- options_monitor, portfolio_risk, portfolio_tracker, returns_comparison
- sector_flow, support_resistance, technical_analysis_with_ai, view_prices

**문제점**:
- 일부 모듈은 색상이 누락되거나 부정확
- 색상 변경 시 16개 파일 수정 필요
- `\033[38;5;82m` (원색 초록) 같은 금지된 색상이 일부 파일에 잔존

---

### 1-2. yfinance 가격 로직 (10개 모듈에서 중복) 🔴 최우선

**현재 상태**:
```python
# 각 모듈마다 자체 구현된 분류 로직
is_kr = ticker.endswith('.KS')
is_equity = (not is_kr
             and not ticker.endswith('=F')
             and not ticker.endswith('=X')
             and not ticker.startswith('^'))

if is_kr:
    curr = fi.last_price
elif is_equity:
    curr = t.history(period='1d', interval='1m', prepost=True)['Close'][-1]
else:
    curr = fi.last_price
```

**중복 모듈 (10개)**:
- chart_viewer, auto_analysis, data_collector, portfolio_tracker
- technical_analysis_with_ai, portfolio_risk, returns_comparison
- support_resistance, multi_agent_analyst, view_prices

**문제점**:
- 모듈마다 미묘한 차이 → **가격 일관성 문제** (CLAUDE.md에 이미 명시된 핵심 로직)
- 한 곳 버그 수정 시 다른 모듈에 전파 안 됨
- 새 자산 추가 시 10개 모듈 모두 수정 필요

---

### 1-3. dotenv 로딩 (6개 모듈) 🟡 중간

**현재 상태**:
```python
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('ANTHROPIC_API_KEY')
```

**중복 모듈 (6개)**: auto_analysis, config, multi_agent_analyst, options_monitor, portfolio_risk, technical_analysis_with_ai

**참고**: `config.py`가 일부 역할 수행 중 → 통합 강화 필요

---

### 1-4. Black-Scholes / 옵션 계산 (2개 모듈) 🟢 낮음

**중복 모듈**: options_monitor, portfolio_risk

**문제점**: 모듈 수는 적지만 코드 양 많음 (수백 줄)

---

### 1-5. HTML 생성 (14개 모듈) 🟡 중간 (Phase 3-D 이후)

**중복 모듈**: 14개 모듈 모두 자체 HTML 생성
- 공통 헤더/푸터/카드 템플릿
- 색상 규칙 (CLAUDE.md HTML 색상 규칙)
- 반응형 레이아웃

**판단**: Phase 3 추후 작업 (지금은 범위 제외)

---

## 2. `jm_lib/` 패키지 구조 설계

```
jm_lib/
├── __init__.py
├── colors.py          # ANSI 색상 통합 → 16개 모듈
├── env.py             # 환경변수·API 키 관리 → 6개 모듈
├── yf_helpers.py      # yfinance 가격 로직 → 10개 모듈
└── options.py         # Black-Scholes·GEX → 2개 모듈
```

### 2-1. `jm_lib/colors.py` (Phase 3-A)

```python
"""ANSI 색상 코드 — Jason Market 통합 색상 정의
   CLAUDE.md 색상 규칙 준수: 원색 노란/초록 금지
"""

# ═══ 신호 색상 (CLAUDE.md 규칙) ═══
CYAN  = '\033[36m'           # 좋음 (긍정 신호)
AMBER = '\033[38;5;214m'     # 경고
ALERT = '\033[38;5;203m'     # 위험 (연한 빨간)

# ═══ 보조 색상 ═══
GRAY  = '\033[38;5;243m'     # 부가 정보
DIM   = '\033[2m'            # 약화
BOLD  = '\033[1m'            # 강조
RESET = '\033[0m'            # 초기화

# ═══ 호환성 별칭 (기존 코드 호환) ═══
GREEN = CYAN                  # 기존 GREEN 별칭
RED   = ALERT                 # 기존 RED 별칭
WARN  = AMBER                 # 기존 WARN 별칭
```

### 2-2. `jm_lib/env.py` (Phase 3-B)

```python
"""환경변수 및 API 키 통합 관리"""
import os
from dotenv import load_dotenv

load_dotenv()  # .env 자동 로드

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def require_api_key(name: str) -> str:
    """필수 API 키 검증"""
    key = os.getenv(name)
    if not key:
        raise ValueError(f"환경변수 {name}이 설정되지 않았습니다 (.env 확인)")
    return key
```

### 2-3. `jm_lib/yf_helpers.py` (Phase 3-C) ⭐ 핵심

```python
"""yfinance 가격 데이터 통합 헬퍼
   CLAUDE.md 가격 데이터 로직 준수
"""
import yfinance as yf

def classify_ticker(ticker: str) -> dict:
    """티커 분류 (is_kr, is_equity, is_futures, is_fx, is_index, is_crypto)"""
    is_kr = ticker.endswith('.KS')
    is_futures = ticker.endswith('=F')
    is_fx = ticker.endswith('=X')
    is_index = ticker.startswith('^')
    is_crypto = ticker in ('BTC-USD', 'ETH-USD')
    is_equity = not (is_kr or is_futures or is_fx or is_index or is_crypto)

    return {
        'is_kr': is_kr,
        'is_equity': is_equity,
        'is_futures': is_futures,
        'is_fx': is_fx,
        'is_index': is_index,
        'is_crypto': is_crypto,
    }

def get_current_price(ticker: str) -> float:
    """현재가 조회 (CLAUDE.md 로직 준수)"""
    cls = classify_ticker(ticker)
    t = yf.Ticker(ticker)
    fi = t.fast_info

    if cls['is_kr']:
        return fi.last_price  # 한국 정규장
    elif cls['is_equity']:
        # 미국 주식/ETF: 프리·애프터 포함
        h = t.history(period='1d', interval='1m', prepost=True)
        return float(h['Close'].iloc[-1]) if not h.empty else fi.last_price
    else:
        return fi.last_price  # 선물/FX/지수/크립토: 24H

def get_prev_close(ticker: str, curr: float = None) -> float:
    """전일 종가 (선물/FX/지수 특수 로직 포함)"""
    cls = classify_ticker(ticker)
    t = yf.Ticker(ticker)

    if cls['is_kr'] or cls['is_equity']:
        return float(t.fast_info.previous_close)

    # 선물/FX/지수/크립토: 마감 vs 거래 중 판단
    h = t.history(period='5d')
    if h.empty:
        return None

    daily_last = float(h['Close'].iloc[-1])
    if curr and abs(curr - daily_last) / daily_last < 0.001:
        # 마감 상태 → 전일 종가는 [-2]
        return float(h['Close'].iloc[-2])
    else:
        return daily_last  # 거래 중
```

### 2-4. `jm_lib/options.py` (Phase 3-D)

```python
"""Black-Scholes 및 옵션 그릭 통합"""
import math
from scipy.stats import norm

def black_scholes_gamma(S, K, T, r, sigma):
    """Black-Scholes Gamma 계산"""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S/K) + (r + sigma**2/2) * T) / (sigma * math.sqrt(T))
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))

def compute_gex(strike, gamma, oi, contract_size=100):
    """GEX (Gamma Exposure) 계산"""
    return gamma * oi * contract_size * (strike ** 2) * 0.01
```

---

## 3. 모듈별 마이그레이션 매핑

### Phase 3-A: colors.py 적용 (16개 모듈)

| 모듈 | 변경 전 | 변경 후 |
|------|--------|--------|
| 모든 모듈 | `ALERT = '\033[38;5;203m'` | `from jm_lib.colors import ALERT` |
| 모든 모듈 | `RESET = '\033[0m'` | `from jm_lib.colors import RESET` |

### Phase 3-B: env.py 적용 (6개 모듈)

| 모듈 | 변경 전 | 변경 후 |
|------|--------|--------|
| auto_analysis | `load_dotenv()` + `os.getenv(...)` | `from jm_lib.env import ANTHROPIC_API_KEY` |
| multi_agent_analyst | (동일) | (동일) |
| portfolio_risk | (동일) | (동일) |
| technical_analysis_with_ai | (동일) | (동일) |
| options_monitor | (동일) | (동일) |
| config | dotenv 로딩 | `jm_lib.env`에 위임 |

### Phase 3-C: yf_helpers.py 적용 (10개 모듈) ⭐

| 모듈 | 변경 전 | 변경 후 |
|------|--------|--------|
| view_prices | 직접 yfinance 호출 + is_equity 분류 | `from jm_lib.yf_helpers import get_current_price, get_prev_close` |
| portfolio_tracker | (동일 패턴) | (동일) |
| portfolio_risk | (동일) | (동일) |
| chart_viewer | (동일) | (동일) |
| auto_analysis | (동일) | (동일) |
| data_collector | (동일) | (동일) |
| technical_analysis_with_ai | (동일) | (동일) |
| returns_comparison | (동일) | (동일) |
| support_resistance | (동일) | (동일) |
| multi_agent_analyst | (동일) | (동일) |

### Phase 3-D: options.py 적용 (2개 모듈)

| 모듈 | 변경 전 | 변경 후 |
|------|--------|--------|
| options_monitor | 자체 BS 계산 | `from jm_lib.options import black_scholes_gamma, compute_gex` |
| portfolio_risk | 자체 BS 계산 | (동일) |

---

## 4. 작업 순서 (Phase 3)

| 단계 | 작업 | 영향 모듈 | 위험도 |
|------|------|----------|-------|
| 3-A | colors.py 추출 + 16개 모듈 import 변경 | 16개 | 낮음 |
| 3-B | env.py 추출 + 6개 모듈 import 변경 | 6개 | 낮음 |
| 3-C | yf_helpers.py 추출 + 10개 모듈 적용 | 10개 | **높음** ⚠️ |
| 3-D | options.py 추출 + 2개 모듈 적용 | 2개 | 중간 |

**3-C가 가장 위험**: 가격 데이터는 모든 분석의 기반 → 회귀 테스트 필수

---

## 5. 안전장치

### 각 단계 후 필수 검증
1. `python3 tests/smoke_test.py` 실행 (33/33 통과 확인)
2. `python3 menu.py` → 1번 (가격 조회) 실행해서 가격 정확성 확인
3. `git commit` 후 다음 단계로

### 롤백 계획
- 각 Phase 단위로 git commit → 문제 발생 시 `git revert`
- 변경 전후 동일한 출력 보장 (특히 가격 데이터)

---

## 6. 예상 결과

### 정량적 효과
- **코드 라인 감소**: 약 800~1,000줄 (중복 제거)
- **모듈 평균 크기**: 17개 모듈 평균 -50줄
- **유지보수성**: 색상/가격 로직 변경 시 1곳만 수정

### 정성적 효과
- **가격 정확도 일관성**: yfinance 로직 통일 → CLAUDE.md 규칙 자동 준수
- **색상 규칙 통일**: 원색 금지 자동화
- **신규 모듈 추가 용이**: jm_lib import만으로 표준 동작 확보

---

## 7. 다음 단계

이 설계도 검토 후 → **Phase 3-A부터 순차 실행** (Haiku 4.5)
