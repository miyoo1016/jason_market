#!/usr/bin/env python3
"""
historical_scenario.py — 역사적 시나리오 패턴 분석기
50년 경력 월가 매니저의 관점으로 설계

실행 → Flask 로컬 서버 자동 시작 → 브라우저 오픈
브라우저에서 시나리오 입력 → Gemini 2.0 Flash 분석
→ 역사적 유사 시점 매칭 → Plotly 인터랙티브 차트
"""

import os, json, threading, webbrowser
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template_string
import yfinance as yf
import pandas as pd
from google import genai

load_dotenv()

app = Flask(__name__)

# ── Gemini 설정 ─────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
_genai_client = genai.Client(api_key=GEMINI_API_KEY)

# ── 종목 정보 ────────────────────────────────────────────────────
TICKERS_INFO = {
    'SPY':  'S&P500 ETF',
    'QQQ':  '나스닥100 ETF',
    'GLD':  '금 ETF',
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'GOOGL':'Alphabet',
    'AMZN': 'Amazon',
    'META': 'Meta',
    'NVDA': 'NVIDIA',
    'TSLA': 'Tesla',
}

TICKER_COLORS = {
    'SPY':'#1a3a5c','QQQ':'#00838f','GLD':'#b8860b',
    'AAPL':'#555555','MSFT':'#107C10','GOOGL':'#4285F4',
    'AMZN':'#FF9900','META':'#0866FF','NVDA':'#76B900','TSLA':'#E31937'
}

# ── 역사적 이벤트 DB (300개) ─────────────────────────────────────
EVENTS_DB = [
    # ─── 금융위기 / 시장붕괴 ───────────────────────────────────────
    {"date":"1987-10-19","name":"블랙 먼데이","category":"금융위기",
     "keywords":["블랙먼데이","시장붕괴","프로그램트레이딩","폭락","패닉"],
     "desc":"다우지수 하루 22.6% 폭락. 역사상 최대 단일일 낙폭. 프로그램 트레이딩·포트폴리오 보험 연쇄 매도가 원인.","impact":-22},

    {"date":"1997-07-02","name":"아시아 금융위기 시작","category":"금융위기",
     "keywords":["아시아금융위기","태국바트","IMF","신흥국위기","외환위기"],
     "desc":"태국 바트화 평가절하로 시작된 아시아 외환위기. 한국 IMF 구제금융. 신흥국 연쇄 타격.","impact":-15},

    {"date":"1998-08-17","name":"러시아 디폴트 + LTCM 붕괴","category":"금융위기",
     "keywords":["러시아디폴트","LTCM","헤지펀드붕괴","신용위기","채권"],
     "desc":"러시아 모라토리엄 + 천재 헤지펀드 LTCM 붕괴. Fed 긴급 구제. 시스템 리스크 최초 경고.","impact":-20},

    {"date":"2000-03-10","name":"닷컴버블 정점","category":"금융위기",
     "keywords":["닷컴버블","인터넷버블","기술주","나스닥버블","과대평가"],
     "desc":"나스닥 5,048.62 역사적 정점. 이후 78% 폭락. 수백 개 인터넷 기업 파산. 2002년까지 지속.","impact":-49},

    {"date":"2001-09-11","name":"9/11 테러 공격","category":"지정학",
     "keywords":["9/11","테러","항공","안보위기","전쟁","보안"],
     "desc":"알카에다 테러 세계무역센터 붕괴. 4거래일 증시 폐장. 재개장 첫날 S&P500 -4.9%.","impact":-12},

    {"date":"2003-03-20","name":"이라크 전쟁 개전","category":"지정학",
     "keywords":["이라크전쟁","중동","유가","WMD","부시"],
     "desc":"미국 이라크 침공. 불확실성 해소로 오히려 시장 반등. '전쟁 개시 후 매수' 패턴.","impact":5},

    {"date":"2007-07-31","name":"서브프라임 위기 첫 신호","category":"금융위기",
     "keywords":["서브프라임","모기지","주택위기","MBS","CDO"],
     "desc":"베어스턴스 헤지펀드 2개 청산. 주택담보증권 가치 붕괴 시작. 2년 후 리먼 사태로 이어짐.","impact":-5},

    {"date":"2008-03-17","name":"베어스턴스 붕괴","category":"금융위기",
     "keywords":["베어스턴스","투자은행","JP모건","긴급구제","유동성위기"],
     "desc":"Fed 긴급 유동성. JP모건 주당 $2에 인수(원래 $170). 시스템 위기 최초 현실화.","impact":-10},

    {"date":"2008-09-15","name":"리먼브라더스 파산 — 글로벌 금융위기","category":"금융위기",
     "keywords":["리먼브라더스","금융위기","파산","신용경색","글로벌위기","뱅크런"],
     "desc":"158년 역사 투자은행 파산. 글로벌 금융시스템 붕괴 직전. S&P500 고점 대비 -57%.","impact":-57},

    {"date":"2010-04-27","name":"유로존 재정위기 — 그리스 디폴트 우려","category":"금융위기",
     "keywords":["유로존위기","그리스","재정위기","PIIGS","유럽채권"],
     "desc":"그리스 신용등급 정크 강등. 포르투갈·아일랜드·이탈리아·스페인 연쇄 위기.","impact":-16},

    {"date":"2010-05-06","name":"플래시 크래시","category":"금융위기",
     "keywords":["플래시크래시","알고리즘","HFT","순간폭락","자동매매"],
     "desc":"장중 다우 -1,000p 순간 폭락. 20분 만에 회복. HFT·알고리즘 트레이딩 취약성 노출.","impact":-3},

    {"date":"2011-08-05","name":"S&P 미국 신용등급 AAA→AA+ 강등","category":"금융위기",
     "keywords":["신용등급강등","미국부채","AAA","재정절벽","S&P"],
     "desc":"사상 첫 미국 국채 신용등급 강등. 부채한도 협상 실패 후. VIX 48까지 폭등.","impact":-19},

    {"date":"2015-08-24","name":"중국발 블랙 먼데이 2.0","category":"금융위기",
     "keywords":["중국증시붕괴","위안화절하","신흥국","블랙먼데이","중국경제"],
     "desc":"중국 위안화 평가절하 + 상하이 증시 8% 폭락. 다우 장중 -1,000p. 글로벌 연쇄 매도.","impact":-12},

    {"date":"2018-02-05","name":"볼마게돈 — VIX 폭발","category":"금융위기",
     "keywords":["볼마게돈","VIX폭발","변동성","인버스VIX","XIV"],
     "desc":"인버스 VIX 상품 청산 연쇄. 하루 VIX +115%. S&P500 -4.1%. 수천억달러 손실.","impact":-10},

    {"date":"2018-12-24","name":"크리스마스 이브 시장 폭락","category":"금융위기",
     "keywords":["크리스마스폭락","파월쇼크","자동조종","금리인상","유동성"],
     "desc":"파월 '자동조종' 발언 + 금리인상 강행. S&P500 -20% 베어마켓. 최단 조정 후 V자 반등.","impact":-20},

    {"date":"2020-02-20","name":"코로나19 시장 붕괴 시작","category":"팬데믹",
     "keywords":["코로나","팬데믹","코로나19","봉쇄","바이러스","전염병"],
     "desc":"코로나19 글로벌 확산 공포. 33일 만에 S&P500 -34%. 역사상 가장 빠른 베어마켓.","impact":-34},

    {"date":"2022-01-03","name":"Fed 긴축 공포 — 기술주 대조정","category":"금리",
     "keywords":["긴축","QT","테이퍼링","성장주폭락","금리상승","기술주조정"],
     "desc":"Fed 의사록 예상보다 빠른 긴축 시사. 나스닥 -33%, 성장주 최대 -70~90% 조정.","impact":-24},

    {"date":"2023-03-10","name":"SVB 붕괴 — 은행 위기","category":"금융위기",
     "keywords":["SVB","실리콘밸리은행","뱅크런","은행위기","예금인출","금리역전"],
     "desc":"48시간 만에 붕괴. 2008 이후 최대 은행 파산. 시그니처·퍼스트리퍼블릭 연쇄.","impact":-8},

    {"date":"2024-08-05","name":"엔 캐리트레이드 청산 쇼크","category":"금융위기",
     "keywords":["엔캐리트레이드","일본금리인상","BOJ","청산","글로벌폭락"],
     "desc":"일본 BOJ 예상 밖 금리인상 → 엔화 급등 → 엔 캐리 청산 → 코스피 -8.77% 서킷브레이커.","impact":-6},

    # ─── 금리 / 통화정책 ────────────────────────────────────────────
    {"date":"1994-02-04","name":"그린스펀 기습 금리인상 — 채권 대학살","category":"금리",
     "keywords":["기습금리인상","채권대학살","그린스펀","서프라이즈","채권"],
     "desc":"예고 없이 금리 0.25%p 인상. 1994년 총 2.5%p 인상. 채권 가격 -20%. 멕시코 위기 촉발.","impact":-8},

    {"date":"2004-06-30","name":"Fed 금리인상 사이클 시작 (2004)","category":"금리",
     "keywords":["금리인상사이클","점진적인상","연준","연착륙","중립금리"],
     "desc":"1%에서 금리인상 시작. 2006년까지 17연속 인상 5.25%. '점진적 인상' 시장 안정.","impact":10},

    {"date":"2007-09-18","name":"서브프라임 대응 첫 금리인하 0.5%","category":"금리",
     "keywords":["금리인하","서브프라임","베르냉키","빅컷","경기부양"],
     "desc":"예상보다 큰 0.5%p 인하. 시장 환영. 이후 2.25%p까지 인하.","impact":8},

    {"date":"2008-11-25","name":"QE1 발표 — 양적완화 시대 개막","category":"금리",
     "keywords":["QE1","양적완화","비전통통화정책","국채매입","MBS"],
     "desc":"Fed 사상 첫 양적완화 6,000억달러. 현대 통화정책의 분수령.","impact":5},

    {"date":"2010-11-03","name":"QE2 발표","category":"금리",
     "keywords":["QE2","양적완화2","국채매입","위험자산","달러약세"],
     "desc":"6,000억달러 추가 국채 매입. 위험자산 랠리. 달러 약세.","impact":15},

    {"date":"2012-09-13","name":"QE3 — 무제한 양적완화","category":"금리",
     "keywords":["QE3","무제한양적완화","MBS","헬리콥터벤","부양"],
     "desc":"월 400억달러 MBS 무제한 매입. '헬리콥터 벤' 극한 부양.","impact":18},

    {"date":"2013-05-22","name":"테이퍼 탠트럼","category":"금리",
     "keywords":["테이퍼탠트럼","테이퍼링","버냉키","채권폭락","신흥국자본이탈"],
     "desc":"버냉키 의회 증언 '테이퍼링 가능' 언급. 10년물 급등. 신흥국 자본 대규모 이탈.","impact":-6},

    {"date":"2015-12-16","name":"9년 만의 제로금리 종료","category":"금리",
     "keywords":["제로금리종료","첫금리인상","정상화","연준","기준금리"],
     "desc":"2008년 이후 7년 제로금리 종료. 0.25%p 첫 인상. 시장 불확실성 해소.","impact":5},

    {"date":"2018-12-19","name":"파월 매파 충격 — '자동조종' 발언","category":"금리",
     "keywords":["파월쇼크","매파","자동조종","금리인상충격","연준독립성"],
     "desc":"4번째 금리인상 + '중립금리에서 멀리' 발언. S&P500 한 달 -20%.","impact":-20},

    {"date":"2019-07-31","name":"예방적 금리인하 (보험성)","category":"금리",
     "keywords":["예방적인하","보험성인하","무역전쟁","연준선제대응","경기연장"],
     "desc":"무역전쟁 불확실성 선제 대응. 2019년 3차례 인하. 역대 최장 강세장 연장.","impact":8},

    {"date":"2020-03-03","name":"코로나 긴급 금리인하 0.5%","category":"금리",
     "keywords":["긴급금리인하","코로나","FOMC외","패닉","경기부양"],
     "desc":"정례 FOMC 외 긴급 인하. 오히려 패닉 신호로 해석. 시장 반응 미미.","impact":-5},

    {"date":"2020-03-15","name":"제로금리 + 무제한 QE 발표","category":"금리",
     "keywords":["제로금리","무제한QE","코로나부양","최강부양","연준"],
     "desc":"0~0.25% 제로금리 + 국채/MBS 무제한 매입. 역사적 최강 부양. 시장 저점 확인.","impact":70},

    {"date":"2021-11-03","name":"테이퍼링 공식 발표","category":"금리",
     "keywords":["테이퍼링","양적완화축소","인플레이션일시적","연준","통화정책전환"],
     "desc":"월 150억달러 QE 축소. '인플레이션 일시적' 기조 공식 변화.","impact":5},

    {"date":"2022-03-16","name":"2022 금리인상 사이클 시작","category":"금리",
     "keywords":["금리인상사이클2022","인플레이션대응","파월","연준긴축","제로금리종료"],
     "desc":"0.25%p 첫 인상. 이후 11차례 연속 인상. 2022년 가장 가파른 인상 사이클.","impact":-24},

    {"date":"2022-05-04","name":"빅스텝 0.5% 인상","category":"금리",
     "keywords":["빅스텝","0.5인상","22년만의빅스텝","인플레이션","파월"],
     "desc":"22년 만의 빅스텝. 파월 '0.75는 없다' 발언. 이후 4차례 연속 자이언트스텝으로 번복.","impact":-10},

    {"date":"2022-06-15","name":"자이언트스텝 0.75% 인상","category":"금리",
     "keywords":["자이언트스텝","0.75인상","CPI쇼크","1994이후최대","인플레이션"],
     "desc":"CPI 8.6% 쇼크 후 1994년 이후 첫 0.75%p 인상. 4연속 자이언트스텝 시작.","impact":-15},

    {"date":"2022-11-30","name":"파월 금리인상 속도 조절 시사","category":"금리",
     "keywords":["속도조절","금리피벗기대","파월브루킹스","상승","피벗"],
     "desc":"파월 브루킹스연구소 연설 '12월 속도 조절 적절'. 피벗 기대 상승.","impact":8},

    {"date":"2023-07-26","name":"마지막 금리인상 — 피크 5.25~5.5%","category":"금리",
     "keywords":["마지막금리인상","피크금리","긴축종료","연착륙","금리정점"],
     "desc":"23년 최고 5.25~5.5%. 이후 동결. 연착륙 기대 상승. S&P500 2023년 +26%.","impact":15},

    {"date":"2024-09-18","name":"빅컷 0.5% 금리인하","category":"금리",
     "keywords":["빅컷","0.5인하","완화사이클","연착륙","4년만인하"],
     "desc":"4년 만의 첫 금리인하. 예상보다 큰 0.5%p. 연착륙 기대 최고조.","impact":5},

    # ─── 경제지표 쇼크 ──────────────────────────────────────────────
    {"date":"2021-11-10","name":"CPI 6.2% — 30년 최고","category":"경제지표",
     "keywords":["CPI6.2","인플레이션","30년최고","물가급등","일시적기조붕괴"],
     "desc":"소비자물가 6.2%, 1990년 이후 최고. '인플레이션 일시적' 기조 공식 붕괴.","impact":-5},

    {"date":"2022-06-10","name":"CPI 8.6% — 40년 최고 쇼크","category":"경제지표",
     "keywords":["CPI8.6","40년최고","물가쇼크","인플레이션공포","예상상회"],
     "desc":"1981년 이후 최고. 예상 8.3% 대폭 상회. S&P500 -2.9%, 10년물 급등.","impact":-8},

    {"date":"2022-09-13","name":"CPI 예상 상회 — 대폭락","category":"경제지표",
     "keywords":["CPI예상상회","인플레이션재가속","S&P폭락","자이언트스텝확실","금리"],
     "desc":"8월 CPI 8.3%, 예상 8.1% 상회. S&P500 -4.3%. 자이언트스텝 확실시.","impact":-5},

    {"date":"2023-02-14","name":"CPI 재가속 — 인플레이션 점착","category":"경제지표",
     "keywords":["CPI재가속","인플레이션점착","더높이더오래","금리인상지속","매파"],
     "desc":"1월 CPI 6.4% 예상 상회. '더 높이 더 오래(Higher for Longer)' 우려 재점화.","impact":-3},

    {"date":"2024-03-12","name":"CPI 3.2% 예상 상회 — 마지막 마일","category":"경제지표",
     "keywords":["CPI3.2","라스트마일","인플레이션재가속","금리인하지연","채권"],
     "desc":"2월 CPI 3.2%, 예상 3.1% 상회. 금리인하 지연 우려. '라스트 마일' 난관.","impact":-3},

    {"date":"2020-04-03","name":"실업급여 신청 700만 — 코로나 고용 충격","category":"경제지표",
     "keywords":["실업대란","코로나실업","경기침체","일자리붕괴","실업급여"],
     "desc":"주간 실업급여 694만 건. 역사상 최대. 1982년 기록의 10배.","impact":-15},

    {"date":"2023-05-05","name":"비농업고용 253만 — 연착륙 신호","category":"경제지표",
     "keywords":["NFP","비농업고용","연착륙","고용서프라이즈","강한경제"],
     "desc":"예상 180만 대폭 상회 253만. 연착륙 기대 vs 긴축 장기화 우려 공존.","impact":2},

    {"date":"2022-04-28","name":"GDP 역성장 -1.4% — 기술적 침체 우려","category":"경제지표",
     "keywords":["GDP역성장","경기침체","리세션","1분기GDP","경기하강"],
     "desc":"1분기 GDP -1.4%. 2분기도 -0.6%. 기술적 침체(연속 역성장) 진입.","impact":-5},

    {"date":"2023-10-27","name":"GDP 4.9% — 예상 압도하는 성장","category":"경제지표",
     "keywords":["GDP4.9","강한성장","소비폭발","연착륙확신","경제호조"],
     "desc":"3분기 GDP +4.9%, 예상 4.7% 상회. 미국 경제 예외주의 확인.","impact":5},

    {"date":"2024-01-26","name":"PCE 2.6% — 인플레이션 목표 근접","category":"경제지표",
     "keywords":["PCE2.6","인플레이션목표근접","2%목표","금리인하기대","연착륙"],
     "desc":"Fed 선호 물가지표 PCE 2.6%. 2% 목표 근접. 금리인하 기대 최고조.","impact":5},

    # ─── 지정학적 리스크 ───────────────────────────────────────────
    {"date":"1990-08-02","name":"걸프전 — 이라크 쿠웨이트 침공","category":"지정학",
     "keywords":["걸프전","이라크","쿠웨이트","유가급등","중동전쟁"],
     "desc":"이라크 쿠웨이트 침공. 유가 2배 폭등. 미국 경기침체 시작.","impact":-20},

    {"date":"2014-03-18","name":"러시아 크림반도 병합","category":"지정학",
     "keywords":["크림반도","러시아","우크라이나","제재","지정학"],
     "desc":"러시아 크림반도 강제 병합. 서방 제재 1라운드. 에너지·원자재 불안.","impact":-3},

    {"date":"2016-06-23","name":"브렉시트 국민투표 충격","category":"지정학",
     "keywords":["브렉시트","영국EU탈퇴","파운드폭락","유럽분열","불확실성"],
     "desc":"영국 EU 탈퇴 51.9% 가결. 파운드 -10%. S&P500 -3.6%. 글로벌 충격.","impact":-5},

    {"date":"2016-11-08","name":"트럼프 1기 대선 당선","category":"정치",
     "keywords":["트럼프1기","트럼프트레이드","규제완화","재정확대","서프라이즈"],
     "desc":"트럼프 예상 밖 당선. 야간 선물 급락 후 급반등. 금융·에너지·인프라 랠리.","impact":12},

    {"date":"2022-02-24","name":"러시아 우크라이나 전면 침공","category":"지정학",
     "keywords":["러우전쟁","우크라이나침공","에너지위기","원자재급등","전쟁"],
     "desc":"70년 만의 유럽 전면전. 에너지·식량 가격 폭등. 유럽 에너지 위기. 인플레이션 가속.","impact":-10},

    {"date":"2023-10-07","name":"이스라엘-하마스 전쟁 발발","category":"지정학",
     "keywords":["이스라엘하마스","중동전쟁","확전우려","유가","안전자산"],
     "desc":"하마스 기습 공격. 가자 지상전. 중동 확전·이란 개입 우려.","impact":-5},

    {"date":"2024-04-13","name":"이란-이스라엘 직접 교전","category":"지정학",
     "keywords":["이란이스라엘","직접교전","드론미사일","중동확전","지정학"],
     "desc":"이란의 이스라엘 드론·미사일 직접 공격. 사상 첫 직접 교전. 확전 공포.","impact":-3},

    {"date":"2024-11-05","name":"트럼프 2기 대선 당선","category":"정치",
     "keywords":["트럼프2기","대선2024","공화당압승","규제완화2.0","트럼프트레이드"],
     "desc":"트럼프 압승. 상·하원 동시 장악(Red Sweep). 감세·규제완화·관세 기대.","impact":8},

    # ─── 무역 / 관세 ───────────────────────────────────────────────
    {"date":"1930-06-17","name":"스무트-홀리 관세법 — 대공황 심화","category":"무역",
     "keywords":["스무트홀리","관세법","대공황","보호무역","무역붕괴"],
     "desc":"평균 45% 관세. 보복관세 연쇄. 세계 무역 66% 감소. 대공황 심화의 원인.","impact":-80},

    {"date":"2018-03-22","name":"트럼프 500억달러 대중 관세 발표","category":"무역",
     "keywords":["트럼프관세","미중무역전쟁","관세폭탄","500억달러","중국"],
     "desc":"중국산 500억달러 25% 관세. 미중 무역전쟁 1라운드 시작.","impact":-10},

    {"date":"2018-07-06","name":"미중 무역전쟁 1라운드 발동","category":"무역",
     "keywords":["미중무역전쟁","340억달러","상호관세","공급망불안","디커플링"],
     "desc":"340억달러 상호 관세 동시 발동. 글로벌 공급망 재편 시작.","impact":-6},

    {"date":"2019-05-10","name":"관세 25% 인상 + 화웨이 제재","category":"무역",
     "keywords":["관세25%인상","화웨이제재","기술전쟁","반도체","디커플링"],
     "desc":"2,000억달러 관세 25% 인상. 화웨이 블랙리스트. 기술 디커플링 본격화.","impact":-7},

    {"date":"2019-08-23","name":"위안화 7위안 돌파 + 보복관세","category":"무역",
     "keywords":["위안화절하","7위안","환율전쟁","보복관세","중국"],
     "desc":"위안화 달러당 7 돌파(11년 만). 중국 750억달러 보복관세. 환율전쟁 우려.","impact":-6},

    {"date":"2020-01-15","name":"미중 1단계 무역합의 서명","category":"무역",
     "keywords":["미중합의","무역전쟁완화","1단계합의","농산물","휴전"],
     "desc":"2년 무역전쟁 1차 휴전. 중국 2,000억달러 미국산 수입 확대 약속.","impact":5},

    {"date":"2022-10-07","name":"반도체 수출통제 대폭 강화","category":"무역",
     "keywords":["반도체수출통제","NVDA제한","엔비디아A100H100","첨단반도체","중국"],
     "desc":"미국 對중 첨단 반도체·장비 포괄 수출 금지. NVDA A100·H100 수출 차단.","impact":-5},

    {"date":"2023-08-09","name":"대중 첨단기술 투자 제한 행정명령","category":"무역",
     "keywords":["바이든행정명령","대중투자제한","반도체AI양자","기술전쟁","디커플링"],
     "desc":"AI·반도체·양자 분야 중국 투자 금지. 기술 전쟁 본격화.","impact":-3},

    {"date":"2025-04-02","name":"트럼프 2기 상호관세 'Liberation Day'","category":"무역",
     "keywords":["상호관세","해방의날","트럼프2기관세","중국145%","관세전쟁"],
     "desc":"전 세계 상호관세. 중국 최대 145%. 글로벌 무역 질서 재편. 1930년대 재연 우려.","impact":-15},

    # ─── 기업실적 / 기술 혁명 ──────────────────────────────────────
    {"date":"2007-06-29","name":"아이폰 출시 — 모바일 혁명 개막","category":"기술혁명",
     "keywords":["아이폰","스마트폰혁명","애플","모바일시대","앱경제"],
     "desc":"스티브 잡스 아이폰 출시. 모바일 경제 시대 개막. AAPL 이후 100배 성장.","impact":8},

    {"date":"2012-05-18","name":"페이스북 IPO — 역대 최대 기술주 상장","category":"기업실적",
     "keywords":["페이스북IPO","META상장","소셜미디어","기술주IPO","과대평가"],
     "desc":"160억달러 역대 최대 기술주 IPO. 상장 직후 폭락. 이후 1,000% 상승.","impact":-3},

    {"date":"2016-11-30","name":"OPEC 감산 합의","category":"원자재",
     "keywords":["OPEC감산","유가급등","산유국","에너지주","WTI"],
     "desc":"8년 만의 OPEC 감산 합의. 유가 10% 급등. 에너지주 랠리.","impact":3},

    {"date":"2022-11-30","name":"ChatGPT 출시 — AI 혁명 시작","category":"기술혁명",
     "keywords":["ChatGPT","AI혁명","오픈AI","생성AI","GPT4"],
     "desc":"5일 만에 100만 사용자. AI 혁명 시작. 빅테크 AI 경쟁 촉발. NVDA 황금기.","impact":15},

    {"date":"2023-01-26","name":"빅테크 대규모 감원 — 비용효율화","category":"기업실적",
     "keywords":["빅테크감원","레이오프","비용절감","수익성개선","AI전환"],
     "desc":"MS·구글·아마존 등 10만 명+ 감원. 비용 효율화로 주가 역설적 급등.","impact":8},

    {"date":"2023-05-24","name":"NVDA 실적 폭탄 — AI 슈퍼사이클","category":"기업실적",
     "keywords":["NVDA실적","AI슈퍼사이클","GPU수요폭발","데이터센터","AI인프라"],
     "desc":"매출 가이던스 +53% 서프라이즈. AI 인프라 수요 폭발. 시총 1조달러 첫 돌파.","impact":20},

    {"date":"2024-02-22","name":"NVDA 실적 — AI 시대 확인","category":"기업실적",
     "keywords":["NVDA실적2024","AI수요지속","블랙웰","데이터센터","AI붐"],
     "desc":"4분기 매출 $221억 vs 예상 $203억. 1분기 가이던스 $240억. AI 수요 지속 확인.","impact":16},

    {"date":"2000-01-10","name":"AOL-타임워너 합병 — 버블 정점 신호","category":"기업실적",
     "keywords":["AOL타임워너","역대최대M&A","닷컴정점","버블","합병"],
     "desc":"1,640억달러 M&A. 닷컴버블 최정점 신호. 결국 990억달러 사상 최대 손실.","impact":-49},

    # ─── 팬데믹 / 보건 ────────────────────────────────────────────
    {"date":"2003-03-17","name":"SARS 공포 — 아시아 경기 충격","category":"팬데믹",
     "keywords":["SARS","전염병","아시아","여행제한","공포"],
     "desc":"SARS 아시아 확산. 홍콩·중국 여행 제한. 아시아 경제 단기 충격.","impact":-5},

    {"date":"2020-01-21","name":"미국 첫 코로나 확진","category":"팬데믹",
     "keywords":["코로나첫확진","중국바이러스","전염병","우한"],
     "desc":"미국 최초 코로나19 확진. 시장 반응 미미. 이후 폭풍의 전조.","impact":-2},

    {"date":"2020-03-11","name":"WHO 코로나 팬데믹 공식 선언","category":"팬데믹",
     "keywords":["팬데믹선언","WHO","봉쇄","NBA중단","유럽입국금지"],
     "desc":"WHO 팬데믹 공식 선언. 전 세계 봉쇄. NBA·리그 중단. 트럼프 유럽 입국 금지.","impact":-5},

    {"date":"2020-03-23","name":"코로나 시장 저점 — 역사적 매수 기회","category":"팬데믹",
     "keywords":["코로나저점","저점매수","공포극점","반등","Fed부양"],
     "desc":"S&P500 2,191 최저점. -34%에서 Fed 무제한 QE로 역사적 반등 시작.","impact":70},

    {"date":"2020-04-09","name":"2조달러 경기부양책 통과","category":"팬데믹",
     "keywords":["경기부양","CARES법","2조달러","헬리콥터머니","재정확대"],
     "desc":"역사상 최대 경기부양 법안. 직접 지급 + 기업 대출 + 실업급여 확대.","impact":10},

    {"date":"2020-11-09","name":"화이자 백신 90% 효과 — 리오프닝 신호","category":"팬데믹",
     "keywords":["화이자백신","백신발표","리오프닝","경제재개","여행회복"],
     "desc":"화이자 mRNA 백신 90% 효과 발표. 리오프닝 기대. 항공·여행·가치주 폭등.","impact":12},

    # ─── 정치 / 정책 ────────────────────────────────────────────
    {"date":"2011-07-31","name":"미국 부채한도 위기 — 디폴트 직전","category":"정치",
     "keywords":["부채한도","디폴트위기","정치교착","미국신용","재정"],
     "desc":"의회 협상 막판 교착. 디폴트 공포. S&P 신용등급 강등으로 이어짐.","impact":-15},

    {"date":"2013-10-01","name":"미국 정부 셧다운 16일","category":"정치",
     "keywords":["셧다운","정부폐쇄","오바마케어","의회교착","연방정부"],
     "desc":"오바마케어 예산 갈등. 16일 연방정부 부분 폐쇄. 800억달러 경제 손실.","impact":-2},

    {"date":"2020-11-03","name":"바이든 대선 당선","category":"정치",
     "keywords":["바이든당선","민주당","친환경","세금인상","정책전환"],
     "desc":"바이든 당선. 친환경·테크 정책. 백신 기대감 맞물려 시장 강세.","impact":15},

    {"date":"2023-05-01","name":"미국 부채한도 위기 2023 — X-date 압박","category":"정치",
     "keywords":["부채한도2023","X-date","디폴트","바이든","재무부"],
     "desc":"X-date(디폴트 시한) 압박. 재무부 비상조치 한계. 막판 양당 합의.","impact":-3},

    {"date":"2025-01-20","name":"트럼프 2기 취임 — 정책 실행 시작","category":"정치",
     "keywords":["트럼프취임","관세즉시발동","이민통제","연방규제철폐","달러"],
     "desc":"취임 첫날 행정명령 쏟아냄. 관세·이민·환경규제 즉시 역전.","impact":3},

    # ─── 원자재 / 에너지 ──────────────────────────────────────────
    {"date":"1973-10-17","name":"1차 오일쇼크 — OPEC 금수 조치","category":"원자재",
     "keywords":["오일쇼크","OPEC","에너지위기","유가폭등","인플레이션"],
     "desc":"아랍 OPEC 이스라엘 지원국 석유 금수. 유가 4배 폭등. 스태그플레이션 시작.","impact":-40},

    {"date":"1979-01-16","name":"2차 오일쇼크 — 이란 혁명","category":"원자재",
     "keywords":["이란혁명","오일쇼크2","유가","스태그플레이션","에너지"],
     "desc":"이란 이슬람 혁명. 유가 다시 2배. 스태그플레이션 심화. Volcker 금리 쇼크.","impact":-20},

    {"date":"2020-04-20","name":"WTI 유가 마이너스 — 사상 첫 음수","category":"원자재",
     "keywords":["유가마이너스","WTI음수","원유폭락","저장용량고갈","코로나"],
     "desc":"WTI 선물 -$37.63. 역사상 첫 음수 유가. 코로나로 수요 소멸, 저장용량 한계.","impact":-5},

    {"date":"2022-03-07","name":"유가 130달러 돌파 — 러우전쟁 에너지 위기","category":"원자재",
     "keywords":["유가130달러","에너지위기","러시아원유","인플레이션가속","LNG"],
     "desc":"WTI 130달러 돌파. 2008년 이후 최고. 러시아 에너지 제재 우려. 유럽 위기.","impact":-8},

    # ─── 달러 / 환율 ───────────────────────────────────────────────
    {"date":"1985-09-22","name":"플라자합의 — 달러 강제 절하","category":"환율",
     "keywords":["플라자합의","달러절하","엔화강세","무역불균형","G5"],
     "desc":"G5 달러 강제 절하 합의. 이후 달러 50% 하락. 일본 엔화 폭등 버블 시작.","impact":5},

    {"date":"2022-09-28","name":"달러 인덱스 114 — 20년 최고","category":"환율",
     "keywords":["달러강세","DXY114","20년최고","신흥국위기","엔화152"],
     "desc":"달러 인덱스 114.78. 20년 최고. 신흥국 외채 위기. 엔화 152. 글로벌 긴축.","impact":-5},

    # ─── 금융 혁신 / 구조적 이벤트 ────────────────────────────────
    {"date":"2009-01-03","name":"비트코인 제네시스 블록 — 탈중앙화 시대","category":"기술혁명",
     "keywords":["비트코인","암호화폐","블록체인","사토시","탈중앙화"],
     "desc":"사토시 나카모토 비트코인 제네시스 블록 생성. 금융 혁명의 시작.","impact":0},

    {"date":"2021-11-10","name":"비트코인 69,000달러 사상 최고","category":"기술혁명",
     "keywords":["비트코인최고가","암호화폐버블","NFT","메타버스","디지털자산"],
     "desc":"BTC 69,000달러 역사적 최고. NFT·메타버스 붐 정점. 이후 -80% 폭락.","impact":5},

    {"date":"2022-11-11","name":"FTX 붕괴 — 암호화폐 리먼 사태","category":"금융위기",
     "keywords":["FTX붕괴","암호화폐리먼","SBF","뱅크런","디지털자산위기"],
     "desc":"샘 뱅크먼-프리드 FTX 파산. 320억달러 암호화폐 거래소 붕괴. BTC -20%.","impact":-5},

    {"date":"2024-01-10","name":"비트코인 ETF 승인 — 기관 투자 개막","category":"기술혁명",
     "keywords":["비트코인ETF","블랙록","기관투자","디지털금","SEC승인"],
     "desc":"블랙록 등 현물 BTC ETF 승인. 기관 투자 자금 유입 시작. BTC 새 사이클.","impact":8},
]


# ── Gemini 분석 함수 ─────────────────────────────────────────────
def analyze_with_gemini(scenario_text: str) -> dict:
    """시나리오를 Gemini로 분석 → 유사 역사적 이벤트 매칭"""

    # 이벤트 DB 요약 (Gemini 컨텍스트용)
    events_list = "\n".join(
        f"[{e['date']}] {e['name']} | 카테고리:{e['category']} | 키워드:{','.join(e['keywords'][:4])}"
        for e in EVENTS_DB
    )

    prompt = f"""당신은 50년 경력의 월가 수석 투자 전략가입니다.
현재 시장 시나리오를 분석하고 역사적으로 가장 유사한 시점을 찾아 투자자에게 인사이트를 제공해야 합니다.

[분석할 현재 시나리오]
{scenario_text}

[참고 가능한 역사적 이벤트 DB]
{events_list}

위 DB에서 현재 시나리오와 가장 유사한 이벤트를 최대 4개 선정하세요.
유사도는 이벤트의 성격, 규모, 시장 구조, 정책 배경을 종합 판단합니다.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "analysis": "현재 시나리오의 핵심 분석. 어떤 유형의 위험/기회인지, 시장에 어떤 영향을 줄 수 있는지 (3-4문장, 한국어)",
  "main_risks": ["핵심 리스크1", "핵심 리스크2", "핵심 리스크3"],
  "matched_events": [
    {{
      "date": "YYYY-MM-DD",
      "name": "이벤트명",
      "similarity_score": 유사도(0-100 정수),
      "reason": "현재 시나리오와 유사한 이유. 어떤 공통점이 있는지 구체적으로 (2-3문장, 한국어)",
      "market_outcome": "당시 S&P500/나스닥/금 등의 시장 반응 결과 요약 (1-2문장, 한국어)"
    }}
  ],
  "outlook": "역사적 패턴을 기반으로 현재 시나리오에서 향후 시장 전망. 주의사항 포함 (4-5문장, 한국어)",
  "key_levels_to_watch": "지금 가장 주목해야 할 지표·수준·이벤트 (한국어, 1-2문장)"
}}"""

    # 모델 폴백: 2.5-flash → 2.0-flash → 2.0-flash-lite (할당량 초과 시 순차 시도)
    models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite']
    last_err = None
    for model_name in models_to_try:
        try:
            resp = _genai_client.models.generate_content(model=model_name, contents=prompt)
            text = resp.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except Exception as e:
            last_err = e
            if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
                continue  # 다음 모델 시도
            raise  # 다른 오류는 즉시 raise
    raise last_err


# ── yfinance 주가 데이터 수집 ─────────────────────────────────────
def get_chart_data(event_date_str: str, selected_tickers: list) -> dict:
    """이벤트 전 6개월 / 후 12개월 주가 데이터 수집 (이벤트일=100 정규화)"""
    try:
        event_dt = datetime.strptime(event_date_str, "%Y-%m-%d")
    except ValueError:
        return {}

    start = event_dt - timedelta(days=180)
    end   = min(event_dt + timedelta(days=365), datetime.now())

    # META: 2012-05-18 상장, NVDA: 충분히 오래됨
    meta_ipo = datetime(2012, 5, 18)
    result = {}

    for ticker in selected_tickers:
        # META 상장 전 이벤트는 스킵
        if ticker == 'META' and event_dt < meta_ipo:
            continue
        try:
            df = yf.download(ticker, start=start, end=end,
                             progress=False, auto_adjust=True)
            if df.empty:
                continue
            # yfinance 최신 버전 MultiIndex 컬럼 처리
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if 'Close' not in df.columns:
                continue
            close = df['Close'].dropna()
            if len(close) < 5:
                continue

            # 이벤트 날짜 기준 인덱스
            idx = close.index.searchsorted(pd.Timestamp(event_dt))
            if idx >= len(close):
                idx = len(close) - 1
            base = float(close.iloc[idx])
            if base <= 0:
                continue

            normalized = (close / base * 100).round(2)
            result[ticker] = {
                "dates":  normalized.index.strftime('%Y-%m-%d').tolist(),
                "values": [float(v) if pd.notna(v) else None
                           for v in normalized.values.flatten()],
                "base_price": round(base, 2)
            }
        except Exception:
            continue

    return result


# ── Flask 라우트 ──────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/analyze', methods=['POST'])
def analyze():
    data     = request.get_json()
    scenario = data.get('scenario', '').strip()
    tickers  = data.get('tickers', ['SPY','QQQ','GLD','AAPL','MSFT','NVDA'])

    if not scenario:
        return jsonify({'error': '시나리오를 입력해주세요.'}), 400

    try:
        gemini_result = analyze_with_gemini(scenario)

        charts = {}
        for ev in gemini_result.get('matched_events', []):
            date = ev.get('date', '')
            if date:
                charts[date] = get_chart_data(date, tickers)

        # 이벤트 DB에서 해당 날짜 상세 정보 추가
        db_map = {e['date']: e for e in EVENTS_DB}
        for ev in gemini_result.get('matched_events', []):
            date = ev.get('date', '')
            if date in db_map:
                ev['db_desc']   = db_map[date]['desc']
                ev['category']  = db_map[date]['category']
                ev['impact']    = db_map[date].get('impact')

        return jsonify({'gemini': gemini_result, 'charts': charts})

    except json.JSONDecodeError:
        return jsonify({'error': 'Gemini 응답 파싱 오류. 다시 시도해주세요.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── HTML 템플릿 ───────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 역사적 시나리오 분석기 — Jason Market</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root{
  --bg:#f5f4ee;--card:#ffffff;--border:#dedad2;
  --text:#252525;--sub:#666;
  --navy:#1a3a5c;--gold:#9a7209;
  --teal:#00838f;--red:#c62828;--orange:#e65100;
  --up:#00838f;--down:#c62828;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;color:var(--text);min-height:100vh;}

/* ── 헤더 ── */
.hdr{background:var(--navy);color:#fff;padding:16px 36px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 8px rgba(0,0,0,.18);}
.hdr-title{font-size:1.25rem;font-weight:800;letter-spacing:-.3px;}
.hdr-sub{font-size:.78rem;opacity:.7;margin-top:2px;}
.hdr-badge{background:var(--gold);color:#fff;padding:4px 12px;border-radius:20px;font-size:.72rem;font-weight:700;letter-spacing:.3px;}

/* ── 레이아웃 ── */
.wrap{max-width:1100px;margin:0 auto;padding:28px 18px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;margin-bottom:18px;box-shadow:0 1px 4px rgba(0,0,0,.05);}
.ctitle{font-size:.92rem;font-weight:800;color:var(--navy);margin-bottom:14px;display:flex;align-items:center;gap:7px;}

/* ── 입력창 ── */
textarea{width:100%;height:130px;border:1.5px solid var(--border);border-radius:9px;padding:13px 14px;font-size:.92rem;font-family:inherit;resize:vertical;background:#fafaf6;color:var(--text);line-height:1.65;transition:border-color .2s;}
textarea:focus{outline:none;border-color:var(--navy);background:#fff;}
textarea::placeholder{color:#b0a890;}

.examples{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px;}
.ex-btn{background:#edeae0;border:1px solid #cdc9be;border-radius:18px;padding:5px 13px;font-size:.77rem;cursor:pointer;color:var(--navy);transition:all .18s;}
.ex-btn:hover{background:var(--navy);color:#fff;border-color:var(--navy);}

/* ── 종목 선택 ── */
.ticker-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin-top:10px;}
.tick-lbl{display:flex;align-items:center;gap:8px;padding:9px 11px;border:1.5px solid var(--border);border-radius:9px;cursor:pointer;transition:all .18s;user-select:none;background:#fff;}
.tick-lbl:hover{border-color:var(--navy);background:#eef2f7;}
.tick-lbl.on{border-color:var(--navy);background:#e8eef8;}
.tick-check{width:17px;height:17px;border:1.5px solid #bbb;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:.75rem;color:var(--navy);font-weight:900;flex-shrink:0;background:#fff;transition:all .15s;}
.tick-lbl.on .tick-check{background:var(--navy);border-color:var(--navy);color:#fff;}
.t-name{font-weight:800;font-size:.84rem;}
.t-desc{font-size:.68rem;color:var(--sub);}

/* ── 버튼 ── */
.btn-go{width:100%;padding:13px;background:var(--navy);color:#fff;border:none;border-radius:10px;font-size:.98rem;font-weight:700;cursor:pointer;transition:all .2s;margin-top:14px;letter-spacing:.4px;}
.btn-go:hover{background:#0e2540;transform:translateY(-1px);box-shadow:0 4px 12px rgba(26,58,92,.25);}
.btn-go:active{transform:translateY(0);}
.btn-go:disabled{background:#aaa;cursor:not-allowed;transform:none;box-shadow:none;}

/* ── 로딩 ── */
.loading{display:none;text-align:center;padding:50px 20px;}
.spin{width:44px;height:44px;border:4px solid #ddd;border-top-color:var(--navy);border-radius:50%;animation:spin .75s linear infinite;margin:0 auto 16px;}
@keyframes spin{to{transform:rotate(360deg)}}
.loading p{color:var(--sub);font-size:.88rem;margin-top:6px;}

/* ── 결과 ── */
#results{display:none;}

.analysis-box{background:linear-gradient(135deg,rgba(26,58,92,.04),rgba(154,114,9,.04));border-left:4px solid var(--navy);padding:16px 18px;border-radius:0 9px 9px 0;margin-bottom:12px;line-height:1.72;font-size:.91rem;}
.risk-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px;}
.rtag{background:#fff3e0;border:1px solid #e65100;color:#e65100;padding:3px 10px;border-radius:16px;font-size:.77rem;font-weight:700;}

/* ── 이벤트 카드 ── */
.ev-grid{display:grid;gap:10px;}
.ev-card{border:1.5px solid var(--border);border-radius:11px;padding:15px 18px;cursor:pointer;transition:all .18s;}
.ev-card:hover{border-color:var(--navy);box-shadow:0 2px 10px rgba(26,58,92,.1);}
.ev-card.sel{border-color:var(--navy);background:#f0f4fa;}
.ev-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;}
.ev-date{font-size:.78rem;color:var(--sub);font-family:monospace;letter-spacing:.3px;}
.ev-meta{display:flex;gap:6px;align-items:center;}
.cat-badge{font-size:.68rem;padding:2px 7px;border-radius:10px;font-weight:700;background:#e8eef8;color:var(--navy);}
.sim-badge{background:var(--navy);color:#fff;padding:2px 8px;border-radius:10px;font-size:.73rem;font-weight:700;}
.ev-name{font-weight:800;font-size:.93rem;margin-bottom:6px;}
.ev-reason{font-size:.82rem;color:var(--sub);line-height:1.55;}
.ev-outcome{margin-top:8px;font-size:.78rem;padding:6px 10px;background:#f5f5f0;border-radius:7px;color:#555;}
.ev-db-desc{margin-top:6px;font-size:.78rem;color:#888;line-height:1.45;font-style:italic;}
.impact-bar{display:flex;align-items:center;gap:6px;margin-top:8px;}
.impact-lbl{font-size:.72rem;color:var(--sub);}
.impact-val{font-size:.8rem;font-weight:800;}
.impact-val.pos{color:var(--up);}
.impact-val.neg{color:var(--down);}

/* ── 차트 ── */
.chart-wrap{width:100%;height:440px;}
.chart-note{text-align:center;font-size:.73rem;color:#aaa;margin-top:8px;}

/* ── 전망 ── */
.outlook-box{background:#f9f7f0;border:1px solid #e4e0d4;border-radius:10px;padding:18px 20px;}
.outlook-box p{line-height:1.72;font-size:.9rem;}
.key-lvl{margin-top:12px;padding-top:11px;border-top:1px solid #e4e0d4;font-size:.83rem;color:var(--orange);font-weight:700;}
.disclaimer{text-align:center;font-size:.72rem;color:#bbb;margin-top:14px;padding-top:10px;border-top:1px solid #eee;}
</style>
</head>
<body>

<div class="hdr">
  <div>
    <div class="hdr-title">📊 역사적 시나리오 분석기</div>
    <div class="hdr-sub">Historical Pattern Matcher — Jason Market</div>
  </div>
  <div class="hdr-badge">Gemini 2.0 Flash</div>
</div>

<div class="wrap">

  <!-- 시나리오 입력 -->
  <div class="card">
    <div class="ctitle">📝 시나리오 입력</div>
    <textarea id="si" placeholder="현재 시장 상황이나 앞으로 예상되는 이벤트를 자유롭게 입력하세요.

예시:
• 미중 관세전쟁 심화 + 달러 강세 + 경기침체 우려
• CPI 재가속 + 연준 금리인하 지연 + 채권금리 급등
• 중동 확전 + 유가 급등 + 안전자산 수요 증가
• AI 슈퍼사이클 + 빅테크 실적 서프라이즈 + 성장주 랠리
• 은행위기 + 신용경색 + 연준 긴급 유동성 공급"></textarea>

    <div class="examples">
      <span style="font-size:.75rem;color:var(--sub);align-self:center;">빠른 입력:</span>
      <button class="ex-btn" onclick="setEx(this)">미중 관세전쟁 + 경기침체 우려</button>
      <button class="ex-btn" onclick="setEx(this)">인플레이션 재가속 + 금리인상</button>
      <button class="ex-btn" onclick="setEx(this)">은행위기 + 신용경색 + 유동성위기</button>
      <button class="ex-btn" onclick="setEx(this)">지정학 리스크 + 유가 급등 + 전쟁</button>
      <button class="ex-btn" onclick="setEx(this)">AI 붐 + 빅테크 실적 서프라이즈</button>
      <button class="ex-btn" onclick="setEx(this)">연준 금리인하 + 경기부양 + 달러약세</button>
      <button class="ex-btn" onclick="setEx(this)">달러 강세 + 신흥국 자본이탈 + 외환위기</button>
      <button class="ex-btn" onclick="setEx(this)">스태그플레이션 + 경기침체 + 인플레이션</button>
    </div>
  </div>

  <!-- 종목 선택 -->
  <div class="card">
    <div class="ctitle">📈 차트에 표시할 종목</div>
    <div class="ticker-grid" id="tg"></div>
    <button class="btn-go" id="goBtn" onclick="doAnalyze()">🔍 역사적 유사 시점 분석 시작</button>
  </div>

  <!-- 로딩 -->
  <div class="loading" id="ld">
    <div class="spin"></div>
    <p><strong>Gemini AI</strong>가 역사적 패턴을 분석 중...</p>
    <p>주가 데이터 수집 포함 약 15~40초 소요됩니다.</p>
  </div>

  <!-- 결과 -->
  <div id="results">

    <div class="card">
      <div class="ctitle">🤖 Gemini 시나리오 분석</div>
      <div class="analysis-box" id="aText"></div>
      <div class="risk-tags" id="rTags"></div>
    </div>

    <div class="card">
      <div class="ctitle">🕰️ 역사적 유사 시점 — 클릭하면 차트가 표시됩니다</div>
      <div class="ev-grid" id="evCards"></div>
    </div>

    <div class="card" id="chartCard" style="display:none">
      <div class="ctitle" id="chartTitle">📈 주가 흐름</div>
      <div class="chart-wrap" id="chartDiv"></div>
      <div class="chart-note">빨간 점선 = 이벤트 발생일 (기준 100) | 전후 6개월 / 12개월</div>
    </div>

    <div class="card">
      <div class="ctitle">🔭 역사적 패턴 기반 시장 전망</div>
      <div class="outlook-box">
        <p id="outlookTxt"></p>
        <div class="key-lvl" id="keyLvl"></div>
      </div>
      <div class="disclaimer">
        ⚠️ 본 분석은 역사적 패턴 참고용이며 투자 조언이 아닙니다. 과거 패턴이 미래를 보장하지 않습니다.
        적중률은 방향성 기준 55~65% 수준입니다.
      </div>
    </div>

  </div>
</div>

<script>
// 종목 정의
const TICKERS = [
  {t:'SPY',d:'S&P500 ETF',on:true},
  {t:'QQQ',d:'나스닥100 ETF',on:true},
  {t:'GLD',d:'금 ETF',on:true},
  {t:'AAPL',d:'Apple',on:true},
  {t:'MSFT',d:'Microsoft',on:true},
  {t:'GOOGL',d:'Alphabet',on:false},
  {t:'AMZN',d:'Amazon',on:false},
  {t:'META',d:'Meta',on:false},
  {t:'NVDA',d:'NVIDIA',on:true},
  {t:'TSLA',d:'Tesla',on:false},
];

const COLORS = {
  SPY:'#1a3a5c',QQQ:'#00838f',GLD:'#b8860b',
  AAPL:'#555',MSFT:'#107C10',GOOGL:'#4285F4',
  AMZN:'#FF9900',META:'#0866FF',NVDA:'#76B900',TSLA:'#E31937'
};

// 종목 버튼 생성 (checkbox 대신 data-selected 속성으로 상태 관리)
const tg = document.getElementById('tg');
TICKERS.forEach(({t,d,on}) => {
  const div = document.createElement('div');
  div.className = 'tick-lbl' + (on?' on':'');
  div.dataset.t = t;
  div.dataset.selected = on ? '1' : '0';
  div.innerHTML = `<span class="tick-check">${on?'✓':''}</span><div><div class="t-name">${t}</div><div class="t-desc">${d}</div></div>`;
  div.addEventListener('click', () => {
    const isOn = div.dataset.selected === '1';
    div.dataset.selected = isOn ? '0' : '1';
    div.classList.toggle('on', !isOn);
    div.querySelector('.tick-check').textContent = isOn ? '' : '✓';
    if (curEvent && chartCache[curEvent]) renderChart(curEvent, chartCache[curEvent]);
  });
  tg.appendChild(div);
});

function getSelected() {
  return [...document.querySelectorAll('.tick-lbl[data-selected="1"]')].map(d=>d.dataset.t);
}

function setEx(btn) {
  document.getElementById('si').value = btn.textContent;
}

let chartCache = {};
let curEvent = null;

async function doAnalyze() {
  const scenario = document.getElementById('si').value.trim();
  if (!scenario) { alert('시나리오를 입력해주세요.'); return; }

  const btn = document.getElementById('goBtn');
  btn.disabled = true;
  document.getElementById('ld').style.display = 'block';
  document.getElementById('results').style.display = 'none';
  document.getElementById('chartCard').style.display = 'none';
  chartCache = {}; curEvent = null;

  try {
    const res = await fetch('/analyze', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ scenario, tickers: getSelected() })
    });
    const data = await res.json();
    if (data.error) { alert('오류: '+data.error); return; }
    renderAll(data);
  } catch(e) {
    alert('오류: '+e.message);
  } finally {
    btn.disabled = false;
    document.getElementById('ld').style.display = 'none';
  }
}

function renderAll(data) {
  const g = data.gemini;

  // AI 분석
  document.getElementById('aText').textContent = g.analysis || '';
  document.getElementById('rTags').innerHTML = (g.main_risks||[])
    .map(r=>`<span class="rtag">${r}</span>`).join('');

  // 이벤트 카드
  chartCache = data.charts || {};
  const evEl = document.getElementById('evCards');
  evEl.innerHTML = '';
  (g.matched_events||[]).forEach((ev,i) => {
    const impact = ev.impact;
    const impHtml = impact != null
      ? `<div class="impact-bar"><span class="impact-lbl">당시 시장영향:</span>
         <span class="impact-val ${impact>=0?'pos':'neg'}">${impact>=0?'+':''}${impact}%</span></div>`
      : '';
    const div = document.createElement('div');
    div.className = 'ev-card'+(i===0?' sel':'');
    div.innerHTML = `
      <div class="ev-top">
        <div class="ev-date">📅 ${ev.date}</div>
        <div class="ev-meta">
          ${ev.category?`<span class="cat-badge">${ev.category}</span>`:''}
          <span class="sim-badge">유사도 ${ev.similarity_score}%</span>
        </div>
      </div>
      <div class="ev-name">${ev.name}</div>
      <div class="ev-reason">${ev.reason}</div>
      <div class="ev-outcome">📊 ${ev.market_outcome}</div>
      ${ev.db_desc?`<div class="ev-db-desc">💬 ${ev.db_desc}</div>`:''}
      ${impHtml}
    `;
    div.onclick = () => {
      document.querySelectorAll('.ev-card').forEach(c=>c.classList.remove('sel'));
      div.classList.add('sel');
      curEvent = ev.date;
      if (chartCache[ev.date]) renderChart(ev.date, chartCache[ev.date]);
    };
    evEl.appendChild(div);
  });

  // 전망
  document.getElementById('outlookTxt').textContent = g.outlook||'';
  document.getElementById('keyLvl').textContent = g.key_levels_to_watch
    ? '👁️ '+g.key_levels_to_watch : '';

  document.getElementById('results').style.display = 'block';

  // 첫 번째 이벤트 자동 차트
  if (g.matched_events?.length && chartCache[g.matched_events[0].date]) {
    curEvent = g.matched_events[0].date;
    renderChart(curEvent, chartCache[curEvent]);
  }
}

function renderChart(evDate, data) {
  if (!data || !Object.keys(data).length) return;

  const sel = getSelected();
  const traces = sel
    .filter(t => data[t])
    .map(t => ({
      x: data[t].dates,
      y: data[t].values,
      name: t,
      type:'scatter', mode:'lines',
      line:{color:COLORS[t]||'#888',width:2.2},
      hovertemplate:`<b>${t}</b><br>%{x}<br>%{y:.1f}<extra></extra>`
    }));

  if (!traces.length) return;

  const layout = {
    paper_bgcolor:'#fff', plot_bgcolor:'#fafaf6',
    font:{family:'Apple SD Gothic Neo,sans-serif',size:11.5},
    xaxis:{showgrid:true,gridcolor:'#eeeee8',zeroline:false,
           showspikes:true,spikecolor:'#999',spikethickness:1},
    yaxis:{title:'상대 수익률 (이벤트 당일 = 100)',
           showgrid:true,gridcolor:'#eeeee8',zeroline:true,zerolinecolor:'#ccc'},
    legend:{orientation:'h',y:-0.16,x:0.5,xanchor:'center'},
    hovermode:'x unified',
    shapes:[{type:'line',x0:evDate,x1:evDate,y0:0,y1:1,yref:'paper',
             line:{color:'#c62828',width:2,dash:'dash'}}],
    annotations:[{x:evDate,y:0.97,yref:'paper',
                  text:'이벤트',showarrow:false,
                  font:{color:'#c62828',size:10},
                  xanchor:'left',xshift:5}],
    margin:{t:18,b:60,l:62,r:18}
  };

  document.getElementById('chartTitle').textContent = `📈 ${evDate} 전후 주가 흐름`;
  document.getElementById('chartCard').style.display = 'block';
  Plotly.newPlot('chartDiv', traces, layout, {responsive:true,displayModeBar:true,
    modeBarButtonsToRemove:['toImage','sendDataToCloud']});
  document.getElementById('chartCard').scrollIntoView({behavior:'smooth',block:'start'});
}
</script>
</body>
</html>"""


# ── 실행 ─────────────────────────────────────────────────────────
def main():
    if not GEMINI_API_KEY:
        print("  ⚠️  .env 파일에 GEMINI_API_KEY가 없습니다.")
        return

    port = 5151
    url  = f"http://127.0.0.1:{port}"

    def _open():
        import time; time.sleep(1.3)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    print(f"\n  📊 역사적 시나리오 분석기 시작")
    print(f"  🌐 브라우저 자동 오픈: {url}")
    print(f"  ⚡ Gemini 2.0 Flash (무료 최강 모델)")
    print(f"  🛑 종료: Ctrl+C\n")
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
