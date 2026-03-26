"""
alerter.py
자동 알림 시스템 - 조건 감시 및 알림 발송
"""

import logging
from datetime import datetime
from config import ALERT_CONDITIONS
from data_collector import DataCollector
from analyzer import MarketAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlertManager:
    """실시간 알림 관리 클래스"""
    
    def __init__(self):
        self.alerts = []
        self.triggered_alerts = []
        self.collector = DataCollector()
        self.analyzer = MarketAnalyzer()
        logger.info("✅ 알림 관리자 초기화")
    
    # ============================================
    # 조건 감시
    # ============================================
    def check_vix_condition(self, assets_data):
        """
        VIX 조건 확인
        - VIX > 25: 높은 변동성 알림
        - VIX > 30: 극도의 공포 알림
        """
        if 'VIX' not in assets_data:
            return None
        
        vix_value = assets_data['VIX']['current_price']
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # 극도의 공포 (30 이상)
        if vix_value > ALERT_CONDITIONS['VIX']['very_high']:
            alert = {
                'type': 'VIX_EXTREME',
                'severity': 'CRITICAL',
                'message': f"🚨 [극도의 공포] VIX {vix_value:.2f} - 시장 극심한 불안정",
                'value': vix_value,
                'time': current_time,
                'recommendation': "• 포지션 헤징 검토\n• 유동성 확보\n• 지정학 뉴스 모니터링"
            }
            return alert
        
        # 높은 변동성 (25~30)
        elif vix_value > ALERT_CONDITIONS['VIX']['high']:
            alert = {
                'type': 'VIX_HIGH',
                'severity': 'WARNING',
                'message': f"⚠️ [높은 변동성] VIX {vix_value:.2f}",
                'value': vix_value,
                'time': current_time,
                'recommendation': "• 주식 포지션 리밸런싱 고려\n• Protective Put 검토"
            }
            return alert
        
        return None
    
    def check_gold_condition(self, assets_data):
        """
        금 급락 조건 확인
        - 일일 -3% 이상: 마진콜 경보
        """
        if '금' not in assets_data:
            return None
        
        gold_change = assets_data['금']['daily_change_pct']
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if gold_change < ALERT_CONDITIONS['GOLD']['daily_change_pct']:
            alert = {
                'type': 'GOLD_CRASH',
                'severity': 'WARNING',
                'message': f"📉 [금 급락] {gold_change:.2f}% - 마진콜 위험",
                'value': gold_change,
                'time': current_time,
                'recommendation': "• 레버리지 포지션 즉시 확인\n• 마진율 체크\n• 청산 필요 여부 검토"
            }
            return alert
        
        return None
    
    def check_oil_condition(self, assets_data):
        """
        유가 조건 확인
        - 브렌트유 $100 돌파
        """
        if '브렌트유' not in assets_data:
            return None
        
        brent_price = assets_data['브렌트유']['current_price']
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if brent_price > ALERT_CONDITIONS['BRENT']['threshold']:
            alert = {
                'type': 'BRENT_BREAKOUT',
                'severity': 'INFO',
                'message': f"⛽ [유가 상승] 브렌트유 ${brent_price:.2f} - $100 돌파",
                'value': brent_price,
                'time': current_time,
                'recommendation': "• 인플레이션 압박 가능성\n• 금리 인상 신호\n• 방어주 강세 예상"
            }
            return alert
        
        return None
    
    def check_btc_condition(self, assets_data):
        """
        BTC 조건 확인
        - 지지선 $69,000 이탈
        - 저항선 $72,000 상향
        """
        if 'BTC' not in assets_data:
            return None
        
        btc_price = assets_data['BTC']['current_price']
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # 지지선 이탈
        if btc_price < ALERT_CONDITIONS['BTC']['support']:
            alert = {
                'type': 'BTC_SUPPORT_BREAK',
                'severity': 'WARNING',
                'message': f"💥 [BTC 지지선 이탈] ${btc_price:.0f} - 추가 하락 가능",
                'value': btc_price,
                'time': current_time,
                'recommendation': "• $67,500 다음 지지선 감시\n• 암호화폐 시장 약세\n• Risk-off 신호"
            }
            return alert
        
        # 저항선 상향
        elif btc_price > ALERT_CONDITIONS['BTC']['resistance']:
            alert = {
                'type': 'BTC_RESISTANCE_BREAK',
                'severity': 'INFO',
                'message': f"🚀 [BTC 저항선 돌파] ${btc_price:.0f} - 상승 신호",
                'value': btc_price,
                'time': current_time,
                'recommendation': "• Risk-on 심화\n• 다음 저항선 $75,000\n• 수익 실현 고려"
            }
            return alert
        
        return None
    
    # ============================================
    # 통합 조건 확인
    # ============================================
    def check_all_conditions(self, assets_data):
        """
        모든 조건을 확인하고 알림 목록 반환
        """
        logger.info("🔔 조건 확인 중...")
        
        alerts = []
        
        # 각 조건 확인
        vix_alert = self.check_vix_condition(assets_data)
        if vix_alert:
            alerts.append(vix_alert)
        
        gold_alert = self.check_gold_condition(assets_data)
        if gold_alert:
            alerts.append(gold_alert)
        
        oil_alert = self.check_oil_condition(assets_data)
        if oil_alert:
            alerts.append(oil_alert)
        
        btc_alert = self.check_btc_condition(assets_data)
        if btc_alert:
            alerts.append(btc_alert)
        
        # 새로운 알림만 기록
        for alert in alerts:
            if alert['type'] not in [a['type'] for a in self.triggered_alerts]:
                self.triggered_alerts.append(alert)
                logger.warning(f"🔔 NEW ALERT: {alert['message']}")
        
        return alerts
    
    # ============================================
    # 알림 발송 (시뮬레이션)
    # ============================================
    def send_notification(self, alert):
        """
        알림 발송 (현재: 로그 출력 / 실제로는 카톡/텔레그램 연동)
        
        향후 구현:
        - Telegram Bot API
        - KakaoTalk Bot API
        - Email (smtplib)
        """
        logger.warning("=" * 60)
        logger.warning(alert['message'])
        logger.warning(f"값: {alert['value']}")
        logger.warning(f"시간: {alert['time']}")
        logger.warning(f"심각도: {alert['severity']}")
        logger.warning("-" * 60)
        logger.warning("권장사항:")
        logger.warning(alert['recommendation'])
        logger.warning("=" * 60)
        
        # 실제 알림 예제:
        # 1. Telegram
        # import requests
        # requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        #     params={'chat_id': CHAT_ID, 'text': alert['message']})
        
        # 2. KakaoTalk (Flask 서버 필요)
        # requests.post("https://kapi.kakao.com/v2/api/talk/memo/default/send",
        #     headers={'Authorization': f'Bearer {TOKEN}'},
        #     json={'template_object': json.dumps({...})})
    
    # ============================================
    # 분석 기반 알림
    # ============================================
    def trigger_analysis_alert(self, market_data):
        """
        시장 데이터 기반 Claude 분석 알림 생성
        """
        logger.info("📊 분석 알림 생성 중...")
        
        analysis = self.analyzer.analyze_market_snapshot(market_data)
        
        alert = {
            'type': 'MARKET_ANALYSIS',
            'severity': 'INFO',
            'message': '📊 시장 종합 분석 완료',
            'time': datetime.now().strftime("%H:%M:%S"),
            'analysis': analysis
        }
        
        return alert
    
    # ============================================
    # 알림 히스토리
    # ============================================
    def get_alert_summary(self):
        """오늘의 알림 요약"""
        summary = {
            'total_alerts': len(self.triggered_alerts),
            'critical': len([a for a in self.triggered_alerts if a['severity'] == 'CRITICAL']),
            'warning': len([a for a in self.triggered_alerts if a['severity'] == 'WARNING']),
            'info': len([a for a in self.triggered_alerts if a['severity'] == 'INFO']),
            'alerts': self.triggered_alerts
        }
        return summary
    
    def clear_alerts(self):
        """알림 초기화"""
        self.triggered_alerts = []
        logger.info("🔄 알림 초기화")


# ============================================
# 테스트 코드
# ============================================
if __name__ == "__main__":
    # 알림 매니저 초기화
    alert_mgr = AlertManager()
    
    # 데이터 수집
    market_data = alert_mgr.collector.collect_all()
    
    # 조건 확인
    alerts = alert_mgr.check_all_conditions(market_data['assets'])
    
    # 알림 발송
    for alert in alerts:
        alert_mgr.send_notification(alert)
    
    # 요약
    print("\n" + "="*60)
    print("📊 알림 요약")
    print("="*60)
    summary = alert_mgr.get_alert_summary()
    print(f"총 알림: {summary['total_alerts']}")
    print(f"Critical: {summary['critical']}")
    print(f"Warning: {summary['warning']}")
    print(f"Info: {summary['info']}")
