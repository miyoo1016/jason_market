"""
analyzer.py
수집된 데이터를 Claude AI로 분석하는 모듈
"""

import json
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketAnalyzer:
    """Claude AI를 활용한 시장 분석 클래스"""
    
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("❌ ANTHROPIC_API_KEY 환경변수 설정 필요")
        
        self.client = Anthropic()
        self.model = CLAUDE_MODEL
        self.max_tokens = 1000
        
        # 대화 히스토리 (맥락 유지)
        self.conversation_history = []
        logger.info(f"✅ Claude 분석기 초기화 (모델: {self.model})")
    
    # ============================================
    # 기본 분석
    # ============================================
    def analyze_market_snapshot(self, market_data):
        """
        현재 시장 상황의 스냅샷 분석
        
        Parameters:
        -----------
        market_data : dict
            data_collector에서 수집한 모든 데이터
        
        Returns:
        --------
        str : Claude의 분석 리포트
        """
        logger.info("🔍 시장 스냅샷 분석 중...")
        
        # 데이터 정리
        assets = market_data.get('assets', {})
        news = market_data.get('news', [])
        calendar = market_data.get('calendar', [])
        
        # 프롬프트 구성
        prompt = f"""
당신은 60년 이상의 월가 펀드매니저입니다. Jason의 투자 분석을 도와주세요.

[현재 시장 데이터 - {market_data.get('collection_time')}]

자산 가격:
{self._format_assets(assets)}

오늘의 주요 뉴스:
{self._format_news(news)}

오늘의 경제 캘린더:
{self._format_calendar(calendar)}

분석 요청:
1. 현재 시장의 핵심 신호는 무엇인가?
2. 각 자산별로 단기(6개월) vs 장기(3년+) 전망은 어떻게 되는가?
3. 가장 주의해야 할 위험 요소는?
4. Jason의 투자 포지션을 조정해야 하는가? (ISA 기준)

한국어로 간결하게 분석해주세요.
"""
        
        response = self._call_claude(prompt)
        return response
    
    # ============================================
    # 이벤트 기반 분석
    # ============================================
    def analyze_price_movement(self, asset_name, price_data, previous_prices):
        """
        특정 자산의 급격한 가격 변동 분석
        
        Parameters:
        -----------
        asset_name : str
            자산명 (예: 'VIX', '금', 'BTC')
        price_data : dict
            현재 가격 데이터
        previous_prices : list
            과거 가격 데이터
        """
        logger.info(f"📊 {asset_name} 가격 변동 분석 중...")
        
        prompt = f"""
[{asset_name} 가격 변동 분석]

현재 가격: {price_data.get('current_price')}
일일 변화: {price_data.get('daily_change_pct')}%
5일 변화: {price_data.get('five_day_change_pct')}%
5일 이동평균: {price_data.get('ma_5')}

과거 5개 가격 데이터:
{json.dumps(previous_prices, indent=2)}

분석:
1. 이 변동은 구조적인가 아니면 일시적인가?
2. 다른 자산과의 상관관계는?
3. Jason의 포지션에 미치는 영향은?
4. 다음 24시간 주시해야 할 레벨은?

간결하게 분석해주세요.
"""
        
        response = self._call_claude(prompt)
        return response
    
    # ============================================
    # 상관관계 분석
    # ============================================
    def analyze_correlations(self, assets_data):
        """
        자산 간 상관관계 분석
        
        Parameters:
        -----------
        assets_data : dict
            모든 자산의 가격 데이터
        """
        logger.info("🔗 자산 간 상관관계 분석 중...")
        
        prompt = f"""
[자산 간 상관관계 분석]

현재 자산 가격 및 변화:
{self._format_assets(assets_data)}

분석:
1. 달러와 금의 역상관은 얼마나 강한가?
2. 유가와 금리의 관계는 현재 어떤 상태인가?
3. BTC의 움직임이 전통 금융과 동조/역동조 되는가?
4. VIX 상승 시 각 자산의 typical 반응은?
5. 현재 포트폴리오 리밸런싱이 필요한가?

Jason의 6개월 직투 관점에서 조언해주세요.
"""
        
        response = self._call_claude(prompt)
        return response
    
    # ============================================
    # 경제 달력 기반 분석
    # ============================================
    def analyze_economic_calendar(self, calendar_events, market_context):
        """
        오늘의 경제 이벤트와 시장의 관계 분석
        
        Parameters:
        -----------
        calendar_events : list
            오늘의 경제 캘린더 이벤트
        market_context : dict
            현재 시장 상황
        """
        if not calendar_events:
            logger.warning("⚠️ 경제 캘린더 이벤트 없음")
            return "경제 캘린더 이벤트가 없습니다."
        
        logger.info("📅 경제 캘린더 분석 중...")
        
        prompt = f"""
[경제 캘린더 기반 시장 분석]

오늘의 주요 이벤트:
{json.dumps(calendar_events, indent=2, ensure_ascii=False)}

현재 시장 상황:
{self._format_assets(market_context.get('assets', {}))}

분석:
1. 각 이벤트 발표 시 예상되는 시장 반응은?
2. Expectation vs Reality의 갭이 크면 어떻게 되나?
3. 이벤트 발표 전후로 어떤 헤징 전략이 필요한가?
4. Jason이 주의해야 할 시간은? (한국 시간 기준)
5. 위험-보상 비율을 고려한 포지션 조정 제안은?

간결하고 실행 가능한 조언 부탁합니다.
"""
        
        response = self._call_claude(prompt)
        return response
    
    # ============================================
    # 시나리오 분석
    # ============================================
    def scenario_analysis(self, base_scenario, bull_scenario, bear_scenario):
        """
        기본값, 낙관, 약세 시나리오 분석 및 확률 가중치 제시
        
        Parameters:
        -----------
        base_scenario : dict
            기본 시나리오
        bull_scenario : dict
            상승장 시나리오
        bear_scenario : dict
            약세 시나리오
        """
        logger.info("🎯 시나리오 분석 중...")
        
        prompt = f"""
[시나리오 분석 - 확률 가중치 포함]

기본 시나리오 (Base Case):
{json.dumps(base_scenario, indent=2, ensure_ascii=False)}

상승장 시나리오 (Bull Case):
{json.dumps(bull_scenario, indent=2, ensure_ascii=False)}

약세 시나리오 (Bear Case):
{json.dumps(bear_scenario, indent=2, ensure_ascii=False)}

분석:
1. 현재 각 시나리오의 확률은? (합계 100%)
2. 6개월 후 예상 결과는?
3. 3년 후 예상 결과는?
4. 각 시나리오별 Jason의 포지션 조정안은?
5. 트리거 이벤트는 무엇인가?

확률 기반 결론을 제시해주세요.
"""
        
        response = self._call_claude(prompt)
        return response
    
    # ============================================
    # Claude API 호출
    # ============================================
    def _call_claude(self, user_message):
        """
        Claude API 호출 (내부용)
        """
        try:
            # 새로운 메시지 추가
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })
            
            # Claude API 호출
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system="""당신은 60년 이상의 월가 펀드매니저입니다.
                
분석 원칙:
- 팩트 기반, 한국어
- 가정→영향→반증 구조
- 시나리오별 확률 가중치로 결론
- 6개월 직투 / 3년+ 연금ISA 구분
- 간결하고 실행 가능한 조언""",
                messages=self.conversation_history
            )
            
            # 응답 추출
            assistant_message = response.content[0].text
            
            # 히스토리에 추가
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            logger.info("✅ Claude 분석 완료")
            return assistant_message
            
        except Exception as e:
            logger.error(f"❌ Claude API 호출 실패: {str(e)}")
            return f"분석 오류: {str(e)}"
    
    # ============================================
    # 유틸리티 함수
    # ============================================
    def _format_assets(self, assets):
        """자산 데이터를 읽기 좋은 형식으로 변환"""
        formatted = []
        for name, data in assets.items():
            formatted.append(
                f"{name}: {data['current_price']:.2f} "
                f"(일일: {data['daily_change_pct']:+.2f}%, "
                f"5일: {data['five_day_change_pct']:+.2f}%)"
            )
        return "\n".join(formatted)
    
    def _format_news(self, news_list):
        """뉴스 데이터를 읽기 좋은 형식으로 변환"""
        if not news_list:
            return "뉴스 없음"
        
        formatted = []
        for item in news_list[:5]:  # 최근 5개
            formatted.append(
                f"- [{item['keyword']}] {item['title']}"
            )
        return "\n".join(formatted)
    
    def _format_calendar(self, calendar_events):
        """경제 캘린더를 읽기 좋은 형식으로 변환"""
        if not calendar_events:
            return "경제 이벤트 없음"
        
        formatted = []
        for event in calendar_events:
            formatted.append(
                f"[{event.get('time')}] {event.get('event')} "
                f"(중요도: {event.get('importance')})"
            )
        return "\n".join(formatted)
    
    def clear_history(self):
        """대화 히스토리 초기화"""
        self.conversation_history = []
        logger.info("🔄 대화 히스토리 초기화")


# ============================================
# 테스트 코드
# ============================================
if __name__ == "__main__":
    from data_collector import DataCollector
    
    # 데이터 수집
    collector = DataCollector()
    market_data = collector.collect_all()
    
    # 분석
    analyzer = MarketAnalyzer()
    analysis = analyzer.analyze_market_snapshot(market_data)
    
    print("\n" + "="*60)
    print("📊 시장 분석 결과")
    print("="*60)
    print(analysis)
