# 🚀 Jason의 투자 자동화 시스템

60년 펀드매니저 수준의 팩트 기반 분석을 자동화한 시스템입니다.

---

## 📋 개요

### 기능
- ✅ **실시간 시장 모니터링** (VIX, 금, 유가, BTC, 환율)
- ✅ **자동 뉴스 수집** (시장 관련 최신 뉴스)
- ✅ **경제 캘린더 통합** (Jason의 수동 입력)
- ✅ **실시간 알림** (조건 충족 시 즉시)
- ✅ **Claude AI 분석** (팩트 기반 분석)
- ✅ **24시간 모니터링** (자동 스케줄)

### 비용
- **월간**: $0 (데이터 수집)
- **분석**: ~$5-10/월 (Claude API 호출, 선택사항)

---

## 🛠️ 설치 가이드

### 1단계: 저장소 클론 및 디렉토리 이동

```bash
cd trading_automation
```

### 2단계: Python 패키지 설치

```bash
pip install -r requirements.txt
```

**필요한 Python 버전**: 3.8 이상

### 3단계: API 키 발급 및 설정

#### A. Anthropic Claude API (필수)
```
1. https://console.anthropic.com 방문
2. API Keys 생성
3. 복사한 키를 .env에 저장
```

#### B. FRED API (권장 - 경제지표)
```
1. https://fred.stlouisfed.org 방문
2. 무료 가입
3. API Key 발급
4. .env에 저장
```

#### C. NewsAPI (권장 - 뉴스)
```
1. https://newsapi.org 방문
2. 무료 플랜 가입
3. API Key 발급
4. .env에 저장
```

### 4단계: 환경변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일을 텍스트 에디터로 열어 API 키 입력
# ANTHROPIC_API_KEY=sk-ant-...
# FRED_API_KEY=...
# NEWSAPI_KEY=...
```

---

## 📖 사용법

### 모드 1: 자동 스케줄러 (24시간 모니터링)

```bash
python main.py
```

**실행:**
- 오전 8시: 자동 시작
- 1분마다: 시장 가격 수집
- 5분마다: 조건 확인 및 알림
- 10분마다: 뉴스 수집
- 15분마다: 분석 리포트
- 오후 10시: 자동 종료

**로그 파일:**
```
trading_automation.log  # 모든 기록 저장
```

### 모드 2: 일회성 테스트

```bash
python main.py --test
```

**실행 내용:**
1. 실시간 가격 수집
2. 뉴스 수집
3. 조건 확인
4. Claude 분석
5. 결과 출력

**용도:** 초기 설정 확인, 트러블슈팅

### 모드 3: 인터랙티브 분석

```bash
python main.py --interactive
```

**메뉴:**
```
1. 시장 스냅샷 분석
2. 자산 상관관계 분석
3. 경제 캘린더 분석
4. 시나리오 분석
5. 특정 자산 분석
6. 알림 요약
0. 종료
```

**용도:** 수동으로 특정 분석 요청

---

## 📅 매일 아침 작업 (5분)

### 1단계: 경제 캘린더 업데이트

파일: `calendar_today.json`

```json
[
  {
    "time": "14:30",
    "event": "ISM Manufacturing PMI",
    "importance": "high",
    "expected": 50.5,
    "previous": 50.2
  },
  {
    "time": "16:00",
    "event": "Fed Powell 발언",
    "importance": "high"
  }
]
```

**업데이트 방법:**
1. `calendar_today.json` 파일 열기
2. 오늘의 중요 경제 지표 추가
3. 저장

**언제:** 오전 8시 이전

### 2단계: 자동화 시작

```bash
python main.py
```

이제 자동으로 모니터링됩니다.

---

## 🔔 알림 시스템

### 자동 알림 조건

| 자산 | 조건 | 심각도 | 동작 |
|------|------|--------|------|
| VIX | > 30 | 🔴 Critical | 극도의 공포 알림 |
| VIX | > 25 | 🟠 Warning | 높은 변동성 알림 |
| 금 | -3% 이상 | 🟠 Warning | 마진콜 경보 |
| 유가 | > $100 | 🟡 Info | 유가 상승 알림 |
| BTC | < $69,000 | 🟠 Warning | 지지선 이탈 |
| BTC | > $72,000 | 🟡 Info | 저항선 돌파 |

### 알림 방식 (현재)

로그 출력 (터미널에 표시)

### 알림 방식 (향후)

다음 중 하나 선택:
- Telegram Bot
- KakaoTalk Bot
- Email

---

## 📊 데이터 수집 소스

| 데이터 | 소스 | 지연 | 비용 |
|--------|------|------|------|
| 실시간 가격 | yfinance | 5-15분 | 무료 |
| 뉴스 | NewsAPI | 실시간 | 무료 |
| 경제지표 | FRED API | 1-2일 | 무료 |
| 분석 | Claude API | 즉시 | ~$5-10/월 |

---

## 📈 분석 방식

### Layer 1: 실시간 수치 (자동)
```
VIX → 공포도 판단
금 → 피난 수요
유가 → 인플레이션 신호
BTC → Risk-on/off
```

### Layer 2: 경제 캘린더 (Jason 입력)
```
경제 지표 발표 → 시장 반응 예측
Fed 성명 → 금리 신호 해석
기업 실적 → 섹터 영향 분석
```

### Layer 3: Claude 분석
```
가정 → 현재 가정
영향 → 각 자산에 미치는 영향
반증 → 반대 시나리오

결론 → 확률 기반 투자 판단
```

---

## 🎯 분석 예제

### 시나리오: 금이 2% 급락

**데이터:**
```
금: -2.74% (15:01)
유가: -1.47% (14:30)
VIX: +3.2%
```

**Claude 분석:**
```
가정:
- USD 강세 (금과 역상관)
- Risk-off 심화 (VIX 상승)
- 인플레이션 우려 (유가 하락)

영향:
- 금: 단기 약세 (-2.74%)
- 안전자산: 채권 매력도 상승
- 주식: 이익률 압박

판단:
확률 가중치
- 기본값 (Base): 60% → 계속 약세
- 상승장 (Bull): 20% → 바닥 신호
- 약세 (Bear): 20% → 추가 급락

권장:
- 6개월 직투: 금 헤징 유지
- 3년+ ISA: 금 비중 유지 (장기 인플레 방어)
```

---

## 🚨 트러블슈팅

### 문제 1: "API 키 오류"
```
Error: ANTHROPIC_API_KEY not found
```

**해결:**
```bash
# .env 파일 확인
cat .env

# API 키가 정확한지 확인
# https://console.anthropic.com에서 재발급
```

### 문제 2: "네트워크 오류"
```
Error: Connection timeout
```

**해결:**
```bash
# 인터넷 연결 확인
ping google.com

# 방화벽 확인
# VPN 사용 중이면 해제
```

### 문제 3: "데이터 수집 실패"
```
Warning: VIX collection failed
```

**해결:**
```bash
# yfinance 업데이트
pip install --upgrade yfinance

# 종목코드 확인
python -c "import yfinance as yf; print(yf.Ticker('^VIX').info)"
```

### 문제 4: "스케줄이 실행 안 됨"
```
No scheduled tasks running
```

**해결:**
```bash
# 거래 시간 확인 (config.py)
# TRADING_START_HOUR = 8
# TRADING_END_HOUR = 22
# (오전 8시 ~ 오후 10시만 실행)

# 현재 시간에 맞춰 테스트 모드로 확인
python main.py --test
```

---

## 📁 파일 구조

```
trading_automation/
├── main.py                 # 메인 실행 파일
├── config.py              # 설정값
├── data_collector.py      # 데이터 수집
├── analyzer.py            # Claude 분석
├── alerter.py             # 알림 시스템
├── requirements.txt       # 패키지 목록
├── .env.example          # 환경변수 예제
├── .env                  # 환경변수 (자신의 API 키)
├── calendar_today.json   # 경제 캘린더 (매일 업데이트)
├── trading_automation.log # 로그 파일
└── README.md             # 이 문서
```

---

## 🔧 커스터마이징

### 모니터링 대상 추가 (config.py)

```python
MONITORED_ASSETS = {
    'VIX': '^VIX',
    '금': 'GC=F',
    '마이자산': 'TICKER_CODE',  # 추가
}
```

### 알림 조건 변경 (config.py)

```python
ALERT_CONDITIONS = {
    'VIX': {
        'high': 25,        # 25에서 30으로 변경
        'very_high': 30,   # 30에서 40으로 변경
    }
}
```

### 스케줄 변경 (main.py)

```python
# 2분마다 실행으로 변경
schedule.every(2).minutes.do(job_collect_prices)
```

### 분석 프롬프트 커스터마이징 (analyzer.py)

```python
# analyze_market_snapshot() 함수의 prompt 변경
prompt = f"""
당신은 Jason의 투자 분석가입니다.
[커스텀 지시사항 추가]
"""
```

---

## 💡 팁

### 팁 1: 로그 파일 모니터링

```bash
# 실시간 로그 보기
tail -f trading_automation.log

# 특정 키워드 검색
grep "ERROR" trading_automation.log
grep "ALERT" trading_automation.log
```

### 팁 2: 백그라운드 실행 (Linux/Mac)

```bash
# 스크린 세션에서 실행
screen -S trading
python main.py

# 분리: Ctrl+A, D
# 복귀: screen -r trading
```

### 팁 3: 포트 포워딩 (원격 서버)

```bash
# 로컬에서 서버의 로그 실시간 보기
ssh user@server "tail -f ~/trading_automation/trading_automation.log"
```

### 팁 4: 정기 백업

```bash
# 매일 자동 백업
# crontab -e
0 23 * * * cp ~/trading_automation/trading_automation.log ~/backup/log_$(date +\%Y\%m\%d).log
```

---

## 📞 지원

### 문제 발생 시
1. `trading_automation.log` 확인
2. `--test` 모드로 개별 모듈 테스트
3. API 키 및 인터넷 연결 확인

### 기능 추가 요청
- alerter.py 수정: 새로운 조건 추가
- analyzer.py 수정: 새로운 분석 추가
- config.py 수정: 파라미터 조정

---

## 📋 라이선스 및 면책

**면책사항:**
- 이 도구는 교육 목적입니다.
- 실제 투자 결정은 전문가와 상담하세요.
- 모든 투자에는 손실 위험이 있습니다.
- 과거 성과는 미래를 보장하지 않습니다.

---

**마지막 업데이트**: 2026년 3월 26일
**버전**: 1.0 (베타)
