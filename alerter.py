"""알림 모듈 - Jason Market"""

import logging
from datetime import datetime
from config import (
    ALERT_VIX_HIGH, ALERT_VIX_CRITICAL,
    ALERT_GOLD_DROP_PCT,
    ALERT_BTC_SUPPORT, ALERT_BTC_RESIST,
)

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self):
        self.triggered_alerts = []
        logger.info("✅ 알림 관리자 초기화")

    def _make_alert(self, alert_type, severity, message, value, recommendation):
        return {
            'type':           alert_type,
            'severity':       severity,
            'message':        message,
            'value':          value,
            'time':           datetime.now().strftime('%H:%M:%S'),
            'recommendation': recommendation,
        }

    def check_vix(self, assets_data):
        if 'VIX' not in assets_data:
            return None
        vix = assets_data['VIX']['current_price']
        if vix > ALERT_VIX_CRITICAL:
            return self._make_alert(
                'VIX_EXTREME', 'CRITICAL',
                f"🚨 [극도 공포] VIX {vix:.2f}",
                vix, "포지션 헤징 검토 / 유동성 확보"
            )
        if vix > ALERT_VIX_HIGH:
            return self._make_alert(
                'VIX_HIGH', 'WARNING',
                f"⚠ [높은 변동성] VIX {vix:.2f}",
                vix, "Protective Put 검토 / 리밸런싱 고려"
            )
        return None

    def check_gold(self, assets_data):
        if '금' not in assets_data:
            return None
        pct = assets_data['금']['daily_change_pct']
        if pct < ALERT_GOLD_DROP_PCT:
            return self._make_alert(
                'GOLD_CRASH', 'WARNING',
                f"📉 [금 급락] {pct:.2f}%",
                pct, "레버리지 포지션 확인 / 마진율 체크"
            )
        return None

    def check_btc(self, assets_data):
        if 'BTC' not in assets_data:
            return None
        price = assets_data['BTC']['current_price']
        if price < ALERT_BTC_SUPPORT:
            return self._make_alert(
                'BTC_SUPPORT_BREAK', 'WARNING',
                f"💥 [BTC 지지선 이탈] ${price:,.0f}",
                price, "추가 하락 감시 / Risk-off 대비"
            )
        if price > ALERT_BTC_RESIST:
            return self._make_alert(
                'BTC_RESIST_BREAK', 'INFO',
                f"🚀 [BTC 저항선 돌파] ${price:,.0f}",
                price, "수익 실현 고려 / 다음 저항선 모니터링"
            )
        return None

    def check_all_conditions(self, assets_data):
        alerts = []
        for checker in [self.check_vix, self.check_gold, self.check_btc]:
            result = checker(assets_data)
            if result:
                alerts.append(result)
                # 같은 타입 중복 알림 방지 (30분 이내)
                existing = [a['type'] for a in self.triggered_alerts]
                if result['type'] not in existing:
                    self.triggered_alerts.append(result)
                    logger.warning(f"🔔 {result['message']}")
        return alerts

    def send_notification(self, alert):
        logger.warning(f"[{alert['severity']}] {alert['message']} | {alert['recommendation']}")

    def get_alert_summary(self):
        return {
            'total_alerts': len(self.triggered_alerts),
            'critical': sum(1 for a in self.triggered_alerts if a['severity'] == 'CRITICAL'),
            'warning':  sum(1 for a in self.triggered_alerts if a['severity'] == 'WARNING'),
            'info':     sum(1 for a in self.triggered_alerts if a['severity'] == 'INFO'),
            'alerts':   self.triggered_alerts,
        }

    def clear_alerts(self):
        self.triggered_alerts = []
