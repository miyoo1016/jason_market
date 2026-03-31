# Jason Market — Claude Code 프로젝트 컨텍스트

이 파일은 어느 기기에서 Claude Code를 열든 자동으로 읽힙니다.
새 세션 시작 시 아래 내용을 기반으로 대화를 이어가면 됩니다.

---

## 프로젝트 개요

- **프로젝트명**: Jason Market
- **목적**: 개인투자자 Jason의 포트폴리오 관리 + 시장 모니터링 터미널 프로그램
- **실행**: `python3 menu.py`
- **GitHub**: https://github.com/miyoo1016/jason_market
- **언어**: Python 3.11+

---

## 포트폴리오 구성 (Jason)

- 미국 ETF: QQQM, SPY
- 미국 개별주: GOOGL
- 국내 ETF: KODEX 나스닥100(379810.KS), KODEX S&P500(379800.KS), KODEX 반도체(390390.KS), TIGER CD금리(357870.KS)
- 실물자산: KRX 금현물
- 예금계좌: 약 4,340만원 (현금성 자산)
- 포트폴리오 데이터: Google Drive 스프레드시트 ↔ `xlsx_sync.py` ↔ `portfolio.json` 자동 동기화

---

## 메뉴 구조 (menu.py)

| 번호 | 항목 | 파일 | HTML |
|------|------|------|------|
| s | xlsx 동기화 — 구글드라이브 연동 | xlsx_sync.py | - |
| 1 | 가격 조회 — 주요 자산 현재가 | view_prices.py | - |
| 2 | 포트폴리오 손익 — 실시간 수익률 | portfolio_tracker.py | ✓ |
| 3 | 공포탐욕지수 — 시장 심리 0~100 | fear_greed.py | - |
| 4 | 거시경제 대시보드 — 금리·달러·유가·환율 | macro_dashboard.py | - |
| 5 | 뉴스 AI 요약 — Claude 한국어 정리 [API 1회] | news_summary.py | - |
| 6 | 가격 알리미 — 목표가 도달 알림 | price_alert.py | - |
| 7 | 기술적 분석 — RSI·MACD·볼린저·스토캐스틱·ATR | technical_analysis_with_ai.py | ✓ |
| 8 | 지지·저항선 — 주요 가격대 분석 | support_resistance.py | ✓ |
| 9 | 수익률 비교 — 자산별 성과 비교 | returns_comparison.py | ✓ |
| 10 | 상관관계 매트릭스 — 자산 간 연관성 | correlation_matrix.py | ✓ |
| 11 | 자동 전체 분석 — 일괄 실행 [API 다수] | auto_analysis.py | ✓ |
| 12 | 멀티 에이전트 AI — Claude 6개 토론 [API 6회] | multi_agent_analyst.py | ✓ |
| 13 | 차트 대시보드 — 16종목 5분봉/일봉 | chart_viewer.py | ✓ |
| 14 | 옵션 모니터 — QQQ/GLD 1개월 배팅 | options_monitor.py | ✓ |
| 15 | 섹터 흐름 — S&P500 11개 섹터 자금흐름 | sector_flow.py | ✓ |
| 16 | 포트폴리오 리스크 — VaR·Beta·변동성 | portfolio_risk.py | ✓ |
| 17 | 시장 스트레스 — VIX구조·금리역전·신용스프레드 | market_stress.py | ✓ |

---

## 핵심 기술 결정사항

### 가격 데이터 로직
```python
is_equity = (not is_kr
             and not ticker.endswith('=F')   # 선물
             and not ticker.endswith('=X')   # FX
             and not ticker.startswith('^')  # 지수
             and ticker not in ('BTC-USD',)) # 크립토

# 현재가
if is_kr:      curr = fast_info['last_price']          # 한국 정규장
elif is_equity: curr = history(1d, 1m, prepost=True)[-1] # 미국 주식/ETF: 프리·애프터 포함
else:           curr = fast_info['last_price']          # 선물·FX·지수·크립토: 24H 실시간

# 전일 종가 (선물/FX/지수/크립토)
daily_last = history(5d).Close[-1]
if abs(curr - daily_last) / daily_last < 0.001:
    prev = history(5d).Close[-2]  # 장 마감 상태
else:
    prev = daily_last             # 거래 중
```

### 시간대 주의사항
- yfinance는 미국 주식 15분 지연 (NYSE/NASDAQ)
- 한국시간 오전 9시~오후 5시: Blue Ocean ATS 거래 (yfinance 미지원) → 주식/ETF 시세 어제 종가
- 선물(=F), FX(=X), 크립토: 24H/24/5 → 언제든 실시간

### HTML 색상 규칙 (중요)
- **절대 금지**: 원색 노란(`#f1c40f`, `\033[38;5;226m`), 원색 초록(`#2ecc71`, `\033[38;5;82m`) → 눈 아픔
- **터미널 색상**:
  - 좋음: CYAN `\033[36m`
  - 경고: AMBER `\033[38;5;214m`
  - 위험: ALERT `\033[38;5;203m` (연한 빨간)
  - RESET: `\033[0m`
- **HTML 배경**: 반드시 흰색 계열 (`background: #f5f6f8`, 카드: `#fff`)
- **절대 금지**: 검정 배경 HTML (`#0d0f18` 등)
- 신호 색상 (HTML): 좋음=`#00838f`(teal), 경고=`#e65100`(orange), 나쁨=`#c62828`(red)

---

## 파일 구조

```
jason_market/
├── menu.py               ← 메인 런처 (여기서 실행)
├── config.py             ← API키·설정 (dotenv)
├── .env                  ← API 키 (GitHub 미포함, 각 기기에 직접 생성)
├── portfolio.json        ← 포트폴리오 (GitHub 미포함, xlsx_sync.py로 생성)
├── requirements.txt      ← 패키지 목록
│
├── view_prices.py        ← 1번: 시세 조회
├── portfolio_tracker.py  ← 2번: 포트폴리오 손익
├── fear_greed.py         ← 3번: 공포탐욕
├── macro_dashboard.py    ← 4번: 거시경제
├── news_summary.py       ← 5번: 뉴스 AI
├── price_alert.py        ← 6번: 가격 알리미
├── technical_analysis_with_ai.py ← 7번: 기술분석
├── support_resistance.py ← 8번: 지지저항
├── returns_comparison.py ← 9번: 수익률 비교
├── correlation_matrix.py ← 10번: 상관관계
├── auto_analysis.py      ← 11번: 자동 분석
├── multi_agent_analyst.py← 12번: 멀티 에이전트
├── chart_viewer.py       ← 13번: 차트
├── options_monitor.py    ← 14번: 옵션
├── sector_flow.py        ← 15번: 섹터 흐름
├── portfolio_risk.py     ← 16번: 리스크
├── market_stress.py      ← 17번: 시장 스트레스
└── xlsx_sync.py          ← s번: 구글드라이브 동기화
```

---

## 환경 설정

### .env 파일 (각 기기에 직접 생성, GitHub 미업로드)
```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 설치 명령어
```bash
git clone https://github.com/miyoo1016/jason_market.git
cd jason_market
pip install -r requirements.txt
# .env 파일 직접 생성
python3 xlsx_sync.py   # 포트폴리오 동기화 (최초 1회)
python3 menu.py        # 실행
```

### Git 동기화 (맥북 ↔ 윈도우북)
```bash
git pull origin main   # 최신 코드 받기
git add -A && git commit -m "수정내용" && git push origin main  # 업로드
```

---

## 주의사항

- `portfolio.json`, `price_alerts.json`, `calendar_today.json`, `.env` 는 `.gitignore` 처리됨
- HTML 출력 파일들도 `.gitignore` 처리됨 (실행 시 자동 생성)
- API 사용 항목: 5번(뉴스), 11번(자동분석), 12번(멀티에이전트) — 나머지는 무료
- 7번 기술분석은 AI 분석 제거됨 (API 소모 없음)
