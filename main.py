"""
main.py
자동화 시스템의 메인 실행 파일
모든 모듈을 통합하여 실시간 모니터링 및 분석 수행
"""

import schedule
import time
import logging
from datetime import datetime
from config import (
    TRADING_START_HOUR,
    TRADING_END_HOUR,
    DATA_COLLECTION_INTERVAL,
    NEWS_REFRESH_INTERVAL,
    ANALYSIS_INTERVAL,
    LOG_FILE,
    LOG_LEVEL
)
from data_collector import DataCollector
from analyzer import MarketAnalyzer
from alerter import AlertManager

# ============================================
# 로깅 설정
# ============================================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# 글로벌 객체
# ============================================
collector = DataCollector()
analyzer = MarketAnalyzer()
alert_manager = AlertManager()

# ============================================
# 스케줄 작업
# ============================================
def job_collect_prices():
    """실시간 가격 수집 (1분마다)"""
    try:
        collector.collect_asset_prices()
    except Exception as e:
        logger.error(f"❌ 가격 수집 실패: {str(e)}")

def job_collect_news():
    """뉴스 수집 (10분마다)"""
    try:
        collector.collect_market_news()
    except Exception as e:
        logger.error(f"❌ 뉴스 수집 실패: {str(e)}")

def job_check_alerts():
    """조건 확인 및 알림 (5분마다)"""
    try:
        market_data = collector.get_all_data()
        alerts = alert_manager.check_all_conditions(market_data['assets'])
        
        # 알림 발송
        for alert in alerts:
            alert_manager.send_notification(alert)
            
    except Exception as e:
        logger.error(f"❌ 알림 확인 실패: {str(e)}")

def job_analyze_market():
    """시장 종합 분석 (5분마다 또는 알림 발생 시)"""
    try:
        market_data = collector.get_all_data()
        analysis = analyzer.analyze_market_snapshot(market_data)
        
        # 분석 결과 로그 저장
        logger.info("="*60)
        logger.info("📊 시장 분석 결과")
        logger.info("="*60)
        logger.info(analysis)
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ 분석 실패: {str(e)}")

def job_daily_startup():
    """매일 아침 시작 (오전 8시)"""
    try:
        logger.info("🌅 오늘의 자동화 시작")
        logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
        
        # 1. 경제 캘린더 로드
        try:
            collector.load_calendar_from_file('calendar_today.json')
        except:
            logger.warning("⚠️ 경제 캘린더 파일 없음 - 수동 입력 필요")
        
        # 2. 초기 데이터 수집
        collector.collect_asset_prices()
        collector.collect_market_news()
        
        # 3. 초기 분석
        market_data = collector.get_all_data()
        analysis = analyzer.analyze_market_snapshot(market_data)
        logger.info(f"📊 아침 분석:\n{analysis}")
        
    except Exception as e:
        logger.error(f"❌ 아침 시작 실패: {str(e)}")

def job_daily_closing():
    """매일 오후 종료 (오후 10시)"""
    try:
        logger.info("🌙 오늘의 자동화 종료")
        
        # 최종 종합 분석
        market_data = collector.get_all_data()
        alerts = alert_manager.get_alert_summary()
        
        logger.info("="*60)
        logger.info("📊 오늘의 알림 요약")
        logger.info("="*60)
        logger.info(f"총 알림: {alerts['total_alerts']}")
        logger.info(f"Critical: {alerts['critical']}")
        logger.info(f"Warning: {alerts['warning']}")
        logger.info(f"Info: {alerts['info']}")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ 오후 종료 실패: {str(e)}")

# ============================================
# 스케줄 설정
# ============================================
def schedule_jobs():
    """모든 작업 스케줄 설정"""
    
    # 매일 오전 8시 시작
    schedule.every().day.at("08:00").do(job_daily_startup)
    
    # 1분마다 가격 수집
    schedule.every(1).minutes.do(job_collect_prices)
    
    # 10분마다 뉴스 수집
    schedule.every(10).minutes.do(job_collect_news)
    
    # 5분마다 조건 확인
    schedule.every(5).minutes.do(job_check_alerts)
    
    # 15분마다 분석
    schedule.every(15).minutes.do(job_analyze_market)
    
    # 매일 오후 10시 종료
    schedule.every().day.at("22:00").do(job_daily_closing)
    
    logger.info("✅ 모든 스케줄 설정 완료")
    logger.info(f"거래 시간: {TRADING_START_HOUR}:00 ~ {TRADING_END_HOUR}:00")

# ============================================
# 메인 실행 루프
# ============================================
def is_trading_hours():
    """현재 거래 시간인지 확인"""
    current_hour = datetime.now().hour
    return TRADING_START_HOUR <= current_hour < TRADING_END_HOUR

def run_scheduler():
    """스케줄 실행 루프"""
    logger.info("🚀 자동화 시스템 시작")
    logger.info("="*60)
    
    schedule_jobs()
    
    try:
        while True:
            # 거래 시간이 아니면 대기
            if not is_trading_hours():
                time.sleep(60)
                continue
            
            # 스케줄된 작업 실행
            schedule.run_pending()
            time.sleep(10)  # 10초마다 확인
            
    except KeyboardInterrupt:
        logger.info("\n🛑 자동화 시스템 종료")
    except Exception as e:
        logger.error(f"❌ 스케줄러 오류: {str(e)}")

# ============================================
# 테스트 모드 (일회성 실행)
# ============================================
def run_once_test():
    """한 번만 실행하여 테스트 (개발용)"""
    logger.info("🧪 테스트 모드 시작")
    logger.info("="*60)
    
    # 1. 데이터 수집
    logger.info("\n[1단계] 데이터 수집")
    market_data = collector.collect_all()
    
    # 2. 조건 확인
    logger.info("\n[2단계] 조건 확인")
    alerts = alert_manager.check_all_conditions(market_data['assets'])
    logger.info(f"감지된 알림: {len(alerts)}개")
    
    # 3. 분석
    logger.info("\n[3단계] 분석")
    analysis = analyzer.analyze_market_snapshot(market_data)
    print("\n" + "="*60)
    print("📊 분석 결과")
    print("="*60)
    print(analysis)
    print("="*60)
    
    logger.info("\n✅ 테스트 완료")

# ============================================
# 수동 분석 요청 (인터랙티브)
# ============================================
def interactive_analysis():
    """Jason의 수동 분석 요청 처리"""
    logger.info("💬 인터랙티브 분석 모드")
    logger.info("="*60)
    
    while True:
        print("\n[분석 메뉴]")
        print("1. 시장 스냅샷 분석")
        print("2. 자산 상관관계 분석")
        print("3. 경제 캘린더 분석")
        print("4. 시나리오 분석")
        print("5. 특정 자산 분석")
        print("6. 알림 요약")
        print("0. 종료")
        
        choice = input("\n선택: ")
        
        if choice == '1':
            market_data = collector.collect_all()
            result = analyzer.analyze_market_snapshot(market_data)
            print("\n" + "="*60)
            print(result)
            print("="*60)
        
        elif choice == '2':
            market_data = collector.collect_all()
            result = analyzer.analyze_correlations(market_data['assets'])
            print("\n" + "="*60)
            print(result)
            print("="*60)
        
        elif choice == '3':
            market_data = collector.collect_all()
            result = analyzer.analyze_economic_calendar(
                market_data['calendar'],
                market_data
            )
            print("\n" + "="*60)
            print(result)
            print("="*60)
        
        elif choice == '6':
            summary = alert_manager.get_alert_summary()
            print("\n" + "="*60)
            print(f"📊 알림 요약")
            print(f"총: {summary['total_alerts']} | "
                  f"Critical: {summary['critical']} | "
                  f"Warning: {summary['warning']} | "
                  f"Info: {summary['info']}")
            print("="*60)
            for alert in summary['alerts']:
                print(f"[{alert['time']}] {alert['message']}")
        
        elif choice == '0':
            print("종료합니다.")
            break
        
        else:
            print("⚠️ 잘못된 선택")

# ============================================
# 엔트리 포인트
# ============================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test':
            # 테스트 모드
            run_once_test()
        elif sys.argv[1] == '--interactive':
            # 인터랙티브 모드
            interactive_analysis()
        else:
            print("사용법:")
            print("  python main.py           # 스케줄러 실행")
            print("  python main.py --test    # 일회성 테스트")
            print("  python main.py --interactive # 인터랙티브 분석")
    else:
        # 일반 실행: 스케줄러
        run_scheduler()
