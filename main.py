"""자동화 시스템 메인 - Jason Market
사용법:
  python3 main.py              # 24시간 자동 모니터링
  python3 main.py --test       # 1회 테스트 실행
  python3 main.py --interactive # 수동 분석 메뉴
"""

import schedule
import time
import logging
import sys
from datetime import datetime
from config import (
    TRADING_START_HOUR, TRADING_END_HOUR,
    DATA_COLLECTION_INTERVAL, ANALYSIS_INTERVAL,
    LOG_FILE, LOG_LEVEL,
)
from data_collector import DataCollector
from analyzer import MarketAnalyzer
from alerter import AlertManager

# ── 로깅 ──────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# ── 글로벌 객체 ────────────────────────────────────────────
collector     = DataCollector()
analyzer      = MarketAnalyzer()
alert_manager = AlertManager()

# ── 스케줄 작업 ────────────────────────────────────────────

def job_collect_prices():
    try:
        collector.collect_asset_prices()
    except Exception as e:
        logger.error(f"가격 수집 실패: {e}")

def job_check_alerts():
    try:
        data   = collector.get_all_data()
        alerts = alert_manager.check_all_conditions(data['assets'])
        for a in alerts:
            alert_manager.send_notification(a)
    except Exception as e:
        logger.error(f"알림 확인 실패: {e}")

def job_analyze_market():
    try:
        data     = collector.get_all_data()
        analysis = analyzer.analyze_market_snapshot(data)
        logger.info("=" * 60)
        logger.info("📊 시장 분석 결과")
        logger.info("=" * 60)
        logger.info(analysis)
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"분석 실패: {e}")

def job_daily_startup():
    logger.info("🌅 오늘의 자동화 시작")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
    try:
        collector.load_calendar_from_file('calendar_today.json')
        collector.collect_asset_prices()
        data     = collector.get_all_data()
        analysis = analyzer.analyze_market_snapshot(data)
        logger.info(f"📊 아침 분석:\n{analysis}")
    except Exception as e:
        logger.error(f"아침 시작 실패: {e}")

def job_daily_closing():
    logger.info("🌙 오늘의 자동화 종료")
    summary = alert_manager.get_alert_summary()
    logger.info(f"오늘 알림 | 전체:{summary['total_alerts']} "
                f"Critical:{summary['critical']} Warning:{summary['warning']} Info:{summary['info']}")
    alert_manager.clear_alerts()
    analyzer.clear_history()

# ── 스케줄 설정 ────────────────────────────────────────────

def schedule_jobs():
    schedule.every().day.at("08:00").do(job_daily_startup)
    schedule.every().day.at("22:00").do(job_daily_closing)
    schedule.every(1).minutes.do(job_collect_prices)
    schedule.every(5).minutes.do(job_check_alerts)
    schedule.every(15).minutes.do(job_analyze_market)
    logger.info(f"✅ 스케줄 설정 완료 (운영: {TRADING_START_HOUR}:00 ~ {TRADING_END_HOUR}:00)")

# ── 모드별 실행 ────────────────────────────────────────────

def run_scheduler():
    logger.info("🚀 Jason 자동화 시스템 시작")
    schedule_jobs()
    # 시작 즉시 1회 실행
    collector.collect_all()
    try:
        while True:
            current_hour = datetime.now().hour
            if TRADING_START_HOUR <= current_hour < TRADING_END_HOUR:
                schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("\n🛑 사용자 종료 (Ctrl+C)")

def run_once_test():
    logger.info("🧪 테스트 모드")
    data   = collector.collect_all()
    alerts = alert_manager.check_all_conditions(data['assets'])
    logger.info(f"알림 {len(alerts)}개 감지")

    analysis = analyzer.analyze_market_snapshot(data)
    print("\n" + "=" * 60)
    print("📊 분석 결과")
    print("=" * 60)
    print(analysis)
    print("=" * 60)

def interactive_analysis():
    print("\n💬 인터랙티브 분석 모드 (0: 종료)")
    while True:
        print("\n1. 시장 스냅샷 분석")
        print("2. 자산 상관관계 분석")
        print("3. 알림 요약")
        print("0. 종료")
        choice = input("선택: ").strip()

        if choice == '1':
            data = collector.collect_all()
            print(analyzer.analyze_market_snapshot(data))
        elif choice == '2':
            data = collector.collect_all()
            print(analyzer.analyze_correlations(data['assets']))
        elif choice == '3':
            s = alert_manager.get_alert_summary()
            print(f"전체:{s['total_alerts']} Critical:{s['critical']} Warning:{s['warning']} Info:{s['info']}")
            for a in s['alerts']:
                print(f"  [{a['time']}] {a['message']}")
        elif choice == '0':
            break
        else:
            print("⚠ 잘못된 입력")

# ── 엔트리 포인트 ──────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test':
            run_once_test()
        elif sys.argv[1] == '--interactive':
            interactive_analysis()
        else:
            print("사용법: python3 main.py [--test | --interactive]")
    else:
        run_scheduler()
