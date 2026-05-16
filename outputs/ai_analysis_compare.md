# Jason AI 분석 — 삼파전 비교 리포트
생성 시각: 2026년 05월 16일 23:23:35

## 실행 결과

| 항목 | gemma4:26b | gemma4:31b | qwen3.6:latest |
|------|----------|----------|----------|
| 성공 여부 | ✅ 성공 | ✅ 성공 | ✅ 성공 |
| 실행 시간 | 44.9s | 232.8s | 196.7s |
| 출력 길이(자) | 785 | 1301 | 1437 |
| 금지 표현 | 없음 | 없음 | 없음 |
| 숫자 왜곡 의심 | 정상 | 정상 | 정상 |
| 한 줄 판정 | 주의 / 주요 지수 ETF의 기술적 과열과 거시 지표(금리, 환율)의 상승 압력이 동시에  | 주의: 월간 강세 흐름은 유지되고 있으나, 일간 급락과 거시지표(VIX, US10Y, US | 주의: 월간 기준 강세 자산의 일간 급락과 주요 지수의 과매수권 진입, 금리 상승 부담이  |
| 장점 | 기본 검증 통과 | 기본 검증 통과 | 기본 검증 통과 |
| 단점 |  |  |  |

## 저장 파일
- 26b MD : `outputs/ai_analysis_26b.md`
- 26b HTML: `outputs/ai_analysis_26b.html`
- 31b MD : `outputs/ai_analysis_31b.md`
- 31b HTML: `outputs/ai_analysis_31b.html`
- qwen36 MD : `outputs/ai_analysis_qwen36.md`
- qwen36 HTML: `outputs/ai_analysis_qwen36.html`

## 동일 DATA FACTS 확인
세 모델 모두 완전히 동일한 DATA FACTS와 동일한 프롬프트를 사용했습니다.

---
*비교 리포트는 Ollama 없이 Python 코드로 생성 (deterministic)*