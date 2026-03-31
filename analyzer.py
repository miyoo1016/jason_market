"""AI 분석 모듈 - Jason Market"""

import json
import logging
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS

logger = logging.getLogger(__name__)

class MarketAnalyzer:
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("❌ .env 파일에 ANTHROPIC_API_KEY가 없습니다")

        from anthropic import Anthropic
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model  = CLAUDE_MODEL
        self.max_tokens = CLAUDE_MAX_TOKENS
        self.history = []   # 최대 10쌍 유지
        logger.info(f"✅ Claude 분석기 초기화 (모델: {self.model})")

    def _call_claude(self, prompt, system=None):
        if system is None:
            system = """당신은 30년 경력의 월가 퀀트 펀드매니저입니다.
Jason(한국 개인투자자)의 포트폴리오: 비트코인, 금, 구글, 나스닥QQQM, S&P500 SPY.
팩트 기반, 간결한 한국어, 실행 가능한 조언."""

        self.history.append({'role': 'user', 'content': prompt})

        # 히스토리 최대 20개 메시지(10쌍)로 제한
        if len(self.history) > 20:
            self.history = self.history[-20:]

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=self.history,
            )
            text = resp.content[0].text
            self.history.append({'role': 'assistant', 'content': text})
            return text
        except Exception as e:
            logger.error(f"❌ Claude API 오류: {e}")
            return f"분석 오류: {e}"

    def analyze_market_snapshot(self, market_data):
        assets   = market_data.get('assets', {})
        calendar = market_data.get('calendar', [])
        ts       = market_data.get('collection_time', '불명')

        assets_text = '\n'.join(
            f"  {name}: {d['current_price']:.2f} ({d['daily_change_pct']:+.2f}%)"
            for name, d in assets.items()
        )
        cal_text = '\n'.join(
            f"  [{e.get('time','')}] {e.get('event','')} (중요도: {e.get('importance','')})"
            for e in calendar
        ) or '  이벤트 없음'

        prompt = f"""[현재 시장 데이터 - {ts}]

자산 가격:
{assets_text}

오늘의 경제 캘린더:
{cal_text}

분석:
1. 현재 시장 핵심 신호
2. 가장 주의할 위험 요소
3. Jason 포트폴리오 단기 대응
(300자 이내, 간결하게)"""

        return self._call_claude(prompt)

    def analyze_correlations(self, assets_data):
        assets_text = '\n'.join(
            f"  {name}: {d['current_price']:.2f} ({d['daily_change_pct']:+.2f}%)"
            for name, d in assets_data.items()
        )
        prompt = f"""[자산 상관관계 분석]

{assets_text}

1. 달러-금 역상관 상태
2. BTC와 전통 자산 동조 여부
3. 포트폴리오 리밸런싱 필요 여부
(250자 이내)"""
        return self._call_claude(prompt)

    def clear_history(self):
        self.history = []
        logger.info("🔄 대화 히스토리 초기화")
