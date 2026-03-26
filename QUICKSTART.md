# ⚡ 빠른 시작 가이드 (10분)

Jason이 30분 안에 시작하는 방법입니다.

---

## 1️⃣ 설정 (5분)

### 1.1 패키지 설치

```bash
pip install -r requirements.txt
```

### 1.2 환경변수 설정

```bash
cp .env.example .env
```

**필수 입력 (.env 파일):**
```
ANTHROPIC_API_KEY=sk-ant-...  # 여기에 YOUR 키 입력
FRED_API_KEY=...              # 선택사항
NEWSAPI_KEY=...               # 선택사항
```

---

## 2️⃣ 테스트 실행 (3분)

```bash
python main.py --test
```

**예상 출력:**
```
✅ 설정 로드 완료
📊 자산 가격 수집 중...
📈 VIX: 18.52 (-2.31%)
📈 금: 2045.50 (+0.45%)
⛽ 브렌트유: 87.23 (-1.12%)
...
📊 시장 분석 결과
="분석 내용"=
```

**실패하면:**
```
❌ API 키 오류 → .env 파일 확인
❌ 네트워크 오류 → 인터넷 연결 확인
```

---

## 3️⃣ 자동화 시작 (2분)

### 옵션 A: 자동 스케줄러 (추천)

```bash
python main.py
```

**실행 내용:**
- 오전 8시 ~ 오후 10시만 활성
- 1분마다 가격 수집
- 5분마다 조건 확인
- 알림 발생 시 즉시

**중지:** `Ctrl+C`

### 옵션 B: 대화형 분석

```bash
python main.py --interactive
```

메뉴에서 선택:
```
1. 시장 스냅샷 분석
2. 자산 상관관계
3. 경제 캘린더
...
```

---

## 4️⃣ 매일 아침 작업 (5분)

### 경제 캘린더 업데이트

파일 열기: `calendar_today.json`

```json
[
  {
    "time": "14:30",
    "event": "ISM Manufacturing",
    "importance": "high"
  }
]
```

**작업 순서:**
1. 오전 8시 이전에 `calendar_today.json` 업데이트
2. `python main.py` 실행
3. 끝!

---

## 📊 실제 사용 예제

### 예제 1: 금이 급락했을 때

```bash
python main.py --interactive
```

선택 → `1. 시장 스냅샷 분석` → Enter

**Claude가 분석:**
```
가정:
- USD 강세
- Risk-off 심화

영향:
- 금: 단기 약세
- 채권: 매력도 상승

판단: 60% 계속 약세, 40% 바닥 신호
```

---

### 예제 2: Fed 성명 발표 예정

```
1. calendar_today.json 에 추가:
   "time": "16:00",
   "event": "Fed Powell 발언",
   "importance": "high"

2. python main.py 실행

3. 16:00 발표 → 자동 분석 → 즉시 알림
```

---

## 🔔 알림 예제

자동으로 다음과 같이 알림:

```
🚨 [극도의 공포] VIX 32.5 - 시장 극심한 불안정
시간: 14:32:15
권장사항:
• 포지션 헤징 검토
• 유동성 확보
```

---

## 📁 핵심 파일 3개

| 파일 | 역할 | 수정 빈도 |
|------|------|---------|
| `.env` | API 키 | 처음만 |
| `calendar_today.json` | 경제 캘린더 | **매일** |
| `config.py` | 알림 조건 | 1-2개월 |

---

## 🚨 자주 묻는 질문

### Q1: 항상 켜져 있어야 하나?
**A:** 아니요. 
- 지정된 시간(8:00~22:00)만 실행
- 그 외 시간에는 자동 중지

### Q2: 비용이 드나?
**A:** 거의 없음.
- 데이터 수집: 무료 (yfinance)
- 분석: ~$5-10/월 (Claude API)
- 총: **월 $5-10**

### Q3: 인터넷이 끊기면?
**A:** 자동 재연결
- 3번 재시도
- 실패 시 로그 기록

### Q4: 다른 자산도 모니터링할 수 있나?
**A:** 네, config.py 수정
```python
MONITORED_ASSETS = {
    'VIX': '^VIX',
    '당신의자산': 'TICKER_CODE',
}
```

### Q5: 분석 결과를 카톡으로 받으려면?
**A:** 향후 지원 (현재 로그 파일)
- Telegram Bot (쉬움)
- KakaoTalk API (중간)
- Email (쉬움)

---

## 🎯 체크리스트

- [ ] Python 3.8+ 설치 확인
- [ ] `pip install -r requirements.txt` 실행
- [ ] `.env` 파일에 API 키 입력
- [ ] `python main.py --test` 성공 확인
- [ ] `calendar_today.json` 업데이트 확인
- [ ] `python main.py` 실행
- [ ] 로그 파일 확인

---

## 📞 문제 발생 시

```bash
# 로그 확인
tail -f trading_automation.log

# 특정 문제 검색
grep "ERROR" trading_automation.log
```

---

## 🚀 다음 단계

1. **현재:** 기본 실시간 모니터링 완료 ✅
2. **1주일:** 경제 캘린더 패턴 파악
3. **2주일:** 알림 조건 커스터마이징
4. **1개월:** 분석 프롬프트 최적화

---

**축하합니다! 자동화 시스템이 준비되었습니다.** 🎉

처음 실행: `python main.py --test`

매일 아침: `python main.py`
