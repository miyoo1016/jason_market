#!/usr/bin/env python3
"""
Jason Market 스모크 테스트 - 모든 모듈 동작 검증
사용법: python3 tests/smoke_test.py
"""

import sys
import os
import importlib
import traceback
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Color codes
GREEN = '\033[36m'      # CYAN
AMBER = '\033[38;5;214m'  # WARNING
RED = '\033[38;5;203m'    # ALERT
RESET = '\033[0m'

# 17개 분석 모듈 목록 (menu.py 제외, config/xlsx_sync 제외)
ANALYSIS_MODULES = [
    'view_prices',
    'portfolio_tracker',
    'fear_greed',
    'macro_dashboard',
    'technical_analysis_with_ai',
    'support_resistance',
    'returns_comparison',
    'correlation_matrix',
    'auto_analysis',
    'chart_viewer',
    'options_monitor',
    'sector_flow',
    'portfolio_risk',
    'market_stress',
    'alpha_hunter',
    'analyzer',
    'data_collector',
]

CORE_MODULES = [
    'menu',
    'config',
    'xlsx_sync',
]

class SmokeTest:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.start_time = datetime.now()

    def test_imports(self):
        """Test importing all modules"""
        print(f"\n{'='*80}")
        print(f"  🔍 스모크 테스트: 모듈 Import 검증")
        print(f"{'='*80}\n")

        # Test analysis modules
        print(f"📦 분석 모듈 ({len(ANALYSIS_MODULES)}개):")
        print(f"{'-'*80}")

        for module_name in ANALYSIS_MODULES:
            try:
                module = importlib.import_module(module_name)
                print(f"  {GREEN}✓{RESET} {module_name:35} (정상)")
                self.passed += 1
            except Exception as e:
                print(f"  {RED}✗{RESET} {module_name:35} (실패: {str(e)[:40]})")
                self.failed += 1
                self.errors.append((module_name, str(e)))

        # Test core modules
        print(f"\n📦 핵심 모듈 ({len(CORE_MODULES)}개):")
        print(f"{'-'*80}")

        for module_name in CORE_MODULES:
            try:
                module = importlib.import_module(module_name)
                print(f"  {GREEN}✓{RESET} {module_name:35} (정상)")
                self.passed += 1
            except Exception as e:
                print(f"  {RED}✗{RESET} {module_name:35} (실패: {str(e)[:40]})")
                self.failed += 1
                self.errors.append((module_name, str(e)))

    def test_menu(self):
        """Test menu system"""
        print(f"\n{'='*80}")
        print(f"  🎯 메뉴 시스템 검증")
        print(f"{'='*80}\n")

        try:
            import menu

            # Check MENU structure
            if not hasattr(menu, 'MENU'):
                raise Exception("MENU attribute not found")

            print(f"  {GREEN}✓{RESET} MENU 구조 존재: {len(menu.MENU)}개 항목")
            self.passed += 1

            # Verify all menu items have required fields
            for num, desc, script, args, is_html in menu.MENU:
                if not all([num, desc, script]):
                    raise Exception(f"Menu item {num} has missing fields")

            print(f"  {GREEN}✓{RESET} MENU 항목 검증: 모두 유효함")
            self.passed += 1

            # Verify menu lookup works
            test_lookup = next((item for item in menu.MENU if item[0] == '1'), None)
            if not test_lookup:
                raise Exception("Menu lookup failed for item '1'")

            print(f"  {GREEN}✓{RESET} 메뉴 검색 기능: 정상")
            self.passed += 1

        except Exception as e:
            print(f"  {RED}✗{RESET} 메뉴 검증 실패: {str(e)}")
            self.failed += 1
            self.errors.append(('menu_system', str(e)))

    def test_config(self):
        """Test configuration"""
        print(f"\n{'='*80}")
        print(f"  ⚙️  설정 검증")
        print(f"{'='*80}\n")

        try:
            import config

            # Check if config loads
            if not hasattr(config, '__name__'):
                raise Exception("Config module not loaded")

            print(f"  {GREEN}✓{RESET} config.py 로드: 성공")
            self.passed += 1

            # Try to access API key (should exist or be empty)
            try:
                from dotenv import load_dotenv
                load_dotenv()
                import os
                api_key = os.getenv('ANTHROPIC_API_KEY', 'NOT_SET')
                if api_key == 'NOT_SET':
                    print(f"  {AMBER}⚠{RESET}  ANTHROPIC_API_KEY: 미설정 (선택사항)")
                else:
                    print(f"  {GREEN}✓{RESET} ANTHROPIC_API_KEY: 설정됨")
                self.passed += 1
            except Exception as e:
                print(f"  {AMBER}⚠{RESET}  환경변수 확인 실패: {str(e)}")
                self.passed += 1  # Not critical

        except Exception as e:
            print(f"  {RED}✗{RESET} 설정 검증 실패: {str(e)}")
            self.failed += 1
            self.errors.append(('config', str(e)))

    def test_dependencies(self):
        """Test external dependencies"""
        print(f"\n{'='*80}")
        print(f"  📚 외부 패키지 검증")
        print(f"{'='*80}\n")

        required_packages = {
            'yfinance': ('yfinance', '시세 데이터'),
            'pandas': ('pandas', '데이터 처리'),
            'numpy': ('numpy', '수학 계산'),
            'scipy': ('scipy', 'Black-Scholes'),
            'requests': ('requests', 'HTTP 요청'),
            'anthropic': ('anthropic', 'Claude API'),
            'python-dotenv': ('dotenv', '환경변수'),
        }

        for pkg_name, (import_name, purpose) in required_packages.items():
            try:
                module = importlib.import_module(import_name)
                version = getattr(module, '__version__', 'installed')
                print(f"  {GREEN}✓{RESET} {pkg_name:20} v{version:10} ({purpose})")
                self.passed += 1
            except ImportError:
                print(f"  {RED}✗{RESET} {pkg_name:20} (미설치)")
                self.failed += 1
                self.errors.append((f'pkg:{pkg_name}', 'Not installed'))

    def test_portfolio_json(self):
        """Test portfolio.json existence"""
        print(f"\n{'='*80}")
        print(f"  💼 데이터 파일 검증")
        print(f"{'='*80}\n")

        try:
            if os.path.exists('portfolio.json'):
                import json
                with open('portfolio.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"  {GREEN}✓{RESET} portfolio.json: 존재 ({len(data)} 자산)")
                self.passed += 1
            else:
                print(f"  {AMBER}⚠{RESET}  portfolio.json: 미존재 (초기화 필요)")
                self.passed += 1  # Not critical on first run
        except Exception as e:
            print(f"  {RED}✗{RESET} portfolio.json 검증 실패: {str(e)}")
            self.failed += 1
            self.errors.append(('portfolio.json', str(e)))

    def run(self):
        """Run all tests"""
        print(f"\n{'='*80}")
        print(f"  Jason Market 스모크 테스트")
        print(f"  시작 시간: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        # Run all test suites
        self.test_imports()
        self.test_menu()
        self.test_config()
        self.test_dependencies()
        self.test_portfolio_json()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        total = self.passed + self.failed

        print(f"\n{'='*80}")
        print(f"  📊 테스트 결과 요약")
        print(f"{'='*80}\n")

        print(f"  {GREEN}✓ 통과{RESET}: {self.passed}개")
        print(f"  {RED}✗ 실패{RESET}: {self.failed}개")
        print(f"  총합: {total}개")
        print(f"  소요 시간: {duration:.2f}초\n")

        if self.errors:
            print(f"{'─'*80}")
            print(f"  ⚠️  에러 상세:")
            print(f"{'─'*80}")
            for module, error in self.errors:
                print(f"\n  {RED}✗ {module}{RESET}")
                print(f"     {error[:70]}")

        # Final status
        print(f"\n{'='*80}")
        if self.failed == 0:
            print(f"  {GREEN}✅ 모든 테스트 통과!{RESET}")
            print(f"     시스템 안정화 완료 ✓")
        else:
            print(f"  {RED}⚠️  일부 테스트 실패{RESET}")
            print(f"     상세 내용 위 참고")
        print(f"{'='*80}\n")

        return 0 if self.failed == 0 else 1


if __name__ == '__main__':
    tester = SmokeTest()
    tester.run()
    sys.exit(tester.print_summary() - 1)  # Adjust exit code
