"""
설정 파일 (config.py)
모든 자동화 설정을 여기서 관리합니다.
"""

import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# ============================================
# API 키 설정
# ============================================
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
FRED_API_KEY = os.getenv('FRED_API_KEY')  # https://fred.stlouisfed.org에서 무료 가입
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')    # https://newsapi.org에서 무료 플랜 가입

# ============================================
# 모니터링 대상 (자동 수집)
# ============================================
MONITORED_ASSETS = {
    'VIX': '^VIX',           # 변동성 지수
    '금': 'GC=F',            # 금 선물
    '브렌트유': 'BZ=F',      # 브렌트유 선물
    'WTI': 'CL=F',           # WTI 원유 선물
    'BTC': 'BTC-USD',        # 비트코인
    'USD/KRW': 'USDKRW=X',   # 달러-원 환율
    'S&P500': '^GSPC',       # S&P 500
    'NASDAQ': '^IXIC',       # 나스닥
}

# ============================================
# 경제지표 (FRED API)
# ============================================
ECONOMIC_INDICATORS = {
    'UNRATE': '실업률(%)',
    'CPIAUCSL': 'CPI(1982-84=100)',
    'DFFx': 'Fed Funds Rate(%)',
    'DGS10': '10년물 수익률(%)',
    'DCOILWTICO': 'WTI유가($/bbl)',
}

# ============================================
# 알림 조건 설정
# ============================================
ALERT_CONDITIONS = {
    'VIX': {
        'high': 25,          # VIX 25 이상 → 알림
        'very_high': 30,     # VIX 30 이상 → 강력 알림
    },
    'GOLD': {
        'daily_change_pct': -3,  # 금 -3% 이상 급락 → 알림
    },
    'BRENT': {
        'threshold': 100,    # 브렌트유 $100 돌파 → 알림
    },
    'BTC': {
        'support': 69000,    # BTC $69,000 이탈 → 알림
        'resistance': 72000, # BTC $72,000 상향 → 알림
    }
}

# ============================================
# 실행 설정
# ============================================
DATA_COLLECTION_INTERVAL = 60  # 데이터 수집 간격 (초)
NEWS_REFRESH_INTERVAL = 600    # 뉴스 업데이트 간격 (초, 10분)
ANALYSIS_INTERVAL = 300        # 분석 실행 간격 (초, 5분)

# 자동화 시작 시간 (24시간 형식)
TRADING_START_HOUR = 8         # 오전 8시 시작
TRADING_END_HOUR = 22          # 오후 10시 종료

# ============================================
# Claude AI 설정
# ============================================
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 1000

# ============================================
# 로깅 설정
# ============================================
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "trading_automation.log"

# ============================================
# 데이터 저장소
# ============================================
DATA_STORAGE_DIR = "./data"
CACHE_DIR = "./cache"

print("✅ 설정 로드 완료")
