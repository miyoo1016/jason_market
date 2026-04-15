#!/usr/bin/env python3
"""
historical_scenario.py — 역사적 시나리오 패턴 분석기
50년 경력 월가 매니저의 관점으로 설계

실행 → Flask 로컬 서버 자동 시작 → 브라우저 오픈
브라우저에서 시나리오 입력 → Gemini 2.0 Flash 분석
→ 역사적 유사 시점 매칭 → Plotly 인터랙티브 차트
"""

import os, json, re, threading, webbrowser
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template_string
import yfinance as yf
import pandas as pd

load_dotenv()

app = Flask(__name__)

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
    'TSM':  'TSMC',
    'SMH':  '반도체 ETF',
}

TICKER_COLORS = {
    'SPY':'#1a3a5c','QQQ':'#00838f','GLD':'#b8860b',
    'AAPL':'#555555','MSFT':'#107C10','GOOGL':'#4285F4',
    'AMZN':'#FF9900','META':'#0866FF','NVDA':'#76B900','TSLA':'#E31937',
    'TSM':'#CE0E2D','SMH':'#7B2FBE',
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

    # ─── 2024 경제지표 / 금리 이벤트 ─────────────────────────────
    {"date":"2024-03-12","name":"CPI 3.2% 예상 상회 — 라스트 마일 난관","category":"경제지표",
     "keywords":["CPI상회","인플레이션라스트마일","금리인하지연","채권금리상승","연착륙불확실"],
     "desc":"2월 CPI 3.2%, 예상 3.1% 상회. 금리인하 지연 우려. '라스트 마일' 난관.","impact":-3},

    {"date":"2024-04-10","name":"CPI 3.5% 서프라이즈 — 금리인하 기대 붕괴","category":"경제지표",
     "keywords":["CPI서프라이즈","금리인하기대붕괴","인플레이션재가속","채권금리급등","스태그플레이션"],
     "desc":"3월 CPI 3.5%, 예상치 대폭 상회. 6월 금리인하 기대 소멸. S&P500 -1.2%.","impact":-5},

    {"date":"2024-05-03","name":"비농업고용 175K 예상 하회 — 9월 인하 기대 부활","category":"경제지표",
     "keywords":["비농업고용쇼크","고용둔화","금리인하기대","노동시장냉각","연착륙"],
     "desc":"4월 고용 175K, 예상 240K 하회. 노동시장 냉각 신호. 9월 인하 기대 부활. 채권 랠리.","impact":3},

    {"date":"2024-07-11","name":"CPI 3.0% 쇼크 하회 — 금리인하 확신","category":"경제지표",
     "keywords":["CPI하회","디스인플레이션","금리인하확신","연착륙","9월인하"],
     "desc":"6월 CPI 3.0%, 예상 3.1% 하회. 9월 인하 확신. 소형주 로테이션 급등. 빅테크 차익.","impact":5},

    {"date":"2024-08-02","name":"고용 쇼크 + 삼의 법칙 발동 — 경기침체 공포","category":"경제지표",
     "keywords":["고용쇼크","삼의법칙","경기침체공포","VIX급등","안전자산"],
     "desc":"7월 고용 114K, 실업률 4.3% 삼의 법칙 발동. S&P500 -1.8%, VIX 38 급등.","impact":-6},

    {"date":"2024-09-06","name":"고용보고서 재반등 — 경기침체 우려 완화","category":"경제지표",
     "keywords":["고용반등","경기침체우려완화","연착륙재확인","빅컷","FOMC"],
     "desc":"8월 고용 142K, 예상 하회지만 삼의 법칙 해제 수준. 빅컷 기대 50:50.","impact":1},

    {"date":"2024-09-18","name":"FOMC 50bp 빅컷 — 연착륙 선언","category":"금리",
     "keywords":["빅컷","50bp인하","연착륙선언","Fed피벗","금리인하사이클"],
     "desc":"Fed 50bp 빅컷 단행. 연착륙 자신감 표명. 금리인하 사이클 공식 시작.","impact":8},

    {"date":"2024-11-07","name":"FOMC 25bp 인하 + 트럼프 당선 후 첫 회의","category":"금리",
     "keywords":["FOMC인하","트럼프관세","인플레이션재우려","중립금리","점도표"],
     "desc":"11월 FOMC 25bp 추가 인하. 트럼프 당선 이후 관세 인플레이션 우려 언급.","impact":2},

    {"date":"2024-12-18","name":"FOMC 매파적 인하 — 2025년 인하 2회로 축소","category":"금리",
     "keywords":["매파적인하","2025인하횟수축소","채권금리급등","나스닥급락","점도표충격"],
     "desc":"25bp 인하 + 2025년 인하 횟수 4→2회로 축소. 채권금리 급등. 나스닥 -3.6%.","impact":-5},

    # ─── 2024 정치 / 지정학 ────────────────────────────────────────
    {"date":"2024-11-06","name":"트럼프 2기 당선 — 감세·관세·규제완화 기대","category":"정치",
     "keywords":["트럼프당선","감세","관세","규제완화","비트코인","달러강세"],
     "desc":"트럼프 2기 압승. S&P500 +2.5%, 비트코인 급등, 달러 강세. 감세·규제완화 기대.","impact":10},

    # ─── 2024 실적발표 이벤트 ─────────────────────────────────────
    {"date":"2024-01-18","name":"TSMC Q4 2023 실적 — AI 반도체 수요 폭증 확인","category":"실적",
     "keywords":["TSMC실적","AI반도체","파운드리","HBM","CoWoS","반도체사이클"],
     "desc":"TSMC Q4 매출 예상 상회. AI 칩 수요 급증 공식 확인. 반도체 섹터 랠리 촉발.","impact":8},

    {"date":"2024-02-21","name":"NVDA Q4 FY24 실적 — AI 사이클 본격화","category":"실적",
     "keywords":["NVDA실적","H100","데이터센터","AI사이클","EPS서프라이즈"],
     "desc":"NVDA FY Q4 EPS $5.16 vs $4.56 예상. 매출 $22.1B. 다음 분기 가이던스 대폭 상회.","impact":15},

    {"date":"2024-04-18","name":"TSMC Q1 2024 실적 — AI 수요 사이클 재확인","category":"실적",
     "keywords":["TSMC실적","AI수요확인","파운드리가동률","반도체사이클","엔비디아수요"],
     "desc":"TSMC Q1 실적 예상 상회. AI 칩 수요가 반도체 사이클 전체 견인 확인.","impact":5},

    {"date":"2024-04-25","name":"META Q1 2024 실적 쇼크 — AI 투자 부담","category":"실적",
     "keywords":["META실적쇼크","카펙스급증","AI투자부담","광고매출","빅테크밸류에이션"],
     "desc":"META 매출 예상 상회 불구 카펙스 가이던스 대폭 상향. AI 투자 부담 우려로 -11%.","impact":-11},

    {"date":"2024-05-02","name":"AAPL Q2 FY24 실적 — AI 슈퍼사이클 기대","category":"실적",
     "keywords":["AAPL실적","애플인텔리전스","자사주매입1100억","AI폰","아이폰16"],
     "desc":"AAPL Q2 예상 상회 + 110B 자사주 매입 발표. 애플 인텔리전스 AI 전략 공개.","impact":7},

    {"date":"2024-07-30","name":"META Q2 2024 실적 — AI 광고 혁명","category":"실적",
     "keywords":["META실적","AI광고효율","라마","오픈소스AI","Advantage+"],
     "desc":"META Q2 EPS $5.16 서프라이즈. AI 광고 효율화로 마진 급개선. Llama 오픈소스.","impact":6},

    {"date":"2024-08-28","name":"NVDA Q2 FY25 실적 — 기대치 부합 but 시간외 하락","category":"실적",
     "keywords":["NVDA실적","블랙웰지연","데이터센터","AI인프라","고평가논란"],
     "desc":"NVDA Q2 대폭 상회 불구 블랙웰 지연 우려 + 시간외 -7%. '서프라이즈 피로감'.","impact":-3},

    {"date":"2024-10-17","name":"TSMC Q3 2024 실적 — AI 붐 최전성기","category":"실적",
     "keywords":["TSMC실적","AI붐","CoWoS","HBM3E","N3공정","매출+39%"],
     "desc":"TSMC Q3 매출 +39% YoY. AI 수요 폭발. 2024년 가이던스 상향. 반도체 섹터 강세.","impact":7},

    {"date":"2024-10-24","name":"AMZN Q3 2024 실적 — AWS AI 가속","category":"실적",
     "keywords":["AMZN실적","AWS성장","AI클라우드","베드락","물류자동화"],
     "desc":"AMZN Q3 AWS +19% 성장. AI 수요로 클라우드 재가속. 마진 개선. +6%.","impact":6},

    {"date":"2023-07-25","name":"GOOGL Q2 2023 실적 — 유튜브 반등 + 클라우드 재가속","category":"실적",
     "keywords":["GOOGL실적","유튜브광고","구글클라우드","검색광고","알파벳"],
     "desc":"GOOGL Q2 EPS $1.44 vs $1.34 예상 대폭 상회. 유튜브 광고 역성장 탈출 +4%. 클라우드 +28% 성장 가속.","impact":6},

    {"date":"2023-10-24","name":"GOOGL Q3 2023 실적 — 검색 서프라이즈 + AI 투자 확대","category":"실적",
     "keywords":["GOOGL실적","검색광고급증","유튜브성장","구글클라우드","AI투자비용"],
     "desc":"GOOGL Q3 EPS $1.55 서프라이즈. 검색 광고 +11% YoY. Cloud 22% 성장. 시간외 +4%.","impact":4},

    {"date":"2024-01-30","name":"GOOGL Q4 2023 실적 — 클라우드 기대 하회","category":"실적",
     "keywords":["GOOGL실적","구글클라우드기대하회","검색견조","유튜브성장","알파벳실적"],
     "desc":"GOOGL Q4 EPS 서프라이즈. 그러나 클라우드 부문 기대치 소폭 하회로 시간외 -5%.","impact":-5},

    {"date":"2024-04-25","name":"GOOGL Q1 2024 실적 — 첫 배당 + 클라우드 급성장","category":"실적",
     "keywords":["GOOGL실적","구글첫배당","구글클라우드+28%","자사주매입","제미나이1.5"],
     "desc":"GOOGL Q1 첫 배당($0.20/주) + 700억 자사주매입 발표. Cloud +28% 어닝 서프라이즈. +10%.","impact":10},

    {"date":"2024-07-23","name":"GOOGL Q2 2024 실적 — 유튜브·클라우드 동반 가속","category":"실적",
     "keywords":["GOOGL실적","유튜브+13%","구글클라우드+29%","광고수익","제미나이"],
     "desc":"GOOGL Q2 EPS $1.89 서프라이즈. YouTube +13%, Cloud +29%, 검색 견조. +5%.","impact":5},

    {"date":"2024-10-29","name":"GOOGL Q3 2024 실적 — 클라우드 반등 서프라이즈","category":"실적",
     "keywords":["GOOGL실적","구글클라우드","제미나이","검색AI","광고수익"],
     "desc":"GOOGL Q3 대폭 상회. 구글 클라우드 +35% 성장. 광고 견조. +6%.","impact":6},

    {"date":"2025-02-04","name":"GOOGL Q4 2024 실적 — 클라우드 +30% + AI 투자 확대","category":"실적",
     "keywords":["GOOGL실적","구글클라우드+30%","제미나이2.0","AI인프라투자","유튜브광고"],
     "desc":"GOOGL Q4 2024 실적 서프라이즈. Cloud +30% 성장. Gemini 2.0 발표. 카펙스 $75B 확대 계획. +3%.","impact":3},

    {"date":"2025-04-29","name":"GOOGL Q1 2025 실적 — AI 검색 전환 + 클라우드 재가속","category":"실적",
     "keywords":["GOOGL실적","구글AI검색","AI오버뷰","클라우드재가속","광고AI최적화"],
     "desc":"GOOGL Q1 2025 매출 $90.2B 대폭 상회. Cloud $12.3B +28%. AI Overview 검색 전환 긍정. +6%.","impact":6},

    {"date":"2024-10-30","name":"MSFT Q1 FY25 실적 — Azure 성장 둔화 우려","category":"실적",
     "keywords":["MSFT실적","Azure성장둔화","코파일럿","클라우드","AI투자"],
     "desc":"MSFT Q1 EPS 서프라이즈. Azure 29% vs 31% 예상. 시간외 -4%.","impact":-3},

    {"date":"2024-11-21","name":"NVDA Q3 FY25 실적 — 기대치 상회 but 시장 실망","category":"실적",
     "keywords":["NVDA실적","블랙웰양산","데이터센터","호퍼매출","AI에이전트"],
     "desc":"NVDA Q3 EPS $0.81 vs $0.75 예상. 매출 $35.1B. 블랙웰 양산 본격화. 시간외 하락.","impact":-3},

    # ─── 2025 이벤트 ──────────────────────────────────────────────
    {"date":"2025-01-20","name":"트럼프 2기 취임 + 관세 행정명령 예고","category":"무역",
     "keywords":["트럼프취임","관세행정명령","DOGE","달러정책","규제완화"],
     "desc":"트럼프 2기 취임. 캐나다·멕시코 25%, 중국 10% 추가 관세 예고. 시장 혼조.","impact":-3},

    {"date":"2025-01-27","name":"DeepSeek R1 충격 — AI 인프라 투자 의문","category":"기술혁명",
     "keywords":["DeepSeek","AI인프라","NVDA폭락","중국AI","저비용AI","효율AI"],
     "desc":"중국 DeepSeek R1 오픈소스 출시. NVDA -17%, 나스닥 -3%. 데이터센터 투자 가치 의문.","impact":-8},

    {"date":"2025-01-29","name":"NVDA Q4 FY25 실적 — 블랙웰 양산 본격화","category":"실적",
     "keywords":["NVDA실적","블랙웰","AI에이전트","추론칩","DeepSeek충격"],
     "desc":"블랙웰 GPU 양산 본격화. 매출 $39.3B. DeepSeek 충격 이후 발표 혼조 반응.","impact":-2},

    {"date":"2025-02-19","name":"FOMC 의사록 — 관세 인플레이션 + 금리인하 신중","category":"금리",
     "keywords":["FOMC의사록","금리인하신중","관세인플레이션","경기불확실","동결"],
     "desc":"Fed: 관세 불확실성·인플레이션 재가속 우려로 금리 인하 신중. 동결 기조 강화.","impact":-2},

    {"date":"2025-03-04","name":"캐나다·멕시코 25% 관세 발동 — 무역전쟁 현실화","category":"무역",
     "keywords":["캐나다멕시코관세","자동차관세","USMCA","무역전쟁","스태그플레이션"],
     "desc":"캐나다·멕시코 25% 관세 실제 발동. 자동차·농산물 타격. 나스닥 -2.8%.","impact":-5},

    {"date":"2025-03-12","name":"CPI 2.8% 예상 하회 — 물가 안도 but 관세 불확실","category":"경제지표",
     "keywords":["CPI하회","물가안정","관세인플레이션","Fed동결","스태그플레이션우려"],
     "desc":"2월 CPI 2.8%, 예상 2.9% 하회. 단기 안도감. 그러나 관세 영향 본격화 우려.","impact":2},

    {"date":"2025-04-02","name":"Liberation Day — 전 세계 상호관세 발표","category":"무역",
     "keywords":["해방의날","상호관세","전면관세전쟁","중국145%","1930대공황재연"],
     "desc":"전 세계 상호관세 발표. 중국 최대 145%. 글로벌 무역 질서 재편. 나스닥 -5%.","impact":-15},

    {"date":"2025-04-09","name":"90일 관세 유예 발표 — 나스닥 역사적 V반등","category":"무역",
     "keywords":["관세유예","V자반등","나스닥9.5%","협상기대","단기반등"],
     "desc":"중국 제외 90일 관세 유예 발표. 나스닥 +9.5%, S&P500 +9.5%. 역사적 단일일 급등.","impact":10},

    {"date":"2025-04-10","name":"중국 보복관세 125% — 미중 관세전쟁 최고조","category":"무역",
     "keywords":["중국보복관세","미중무역전쟁","125%관세","공급망붕괴","달러약세"],
     "desc":"중국 미국산 125% 보복관세. 미중 관세전쟁 전면화. 글로벌 공급망 재편 가속.","impact":-8},

    {"date":"2025-04-17","name":"TSMC Q1 2025 실적 — AI 수요 vs 관세 리스크","category":"실적",
     "keywords":["TSMC실적","AI수요","관세영향","파운드리","지정학리스크","N3공정"],
     "desc":"TSMC Q1 2025 실적. AI 반도체 수요 지속 확인 vs 관세·지정학 가이던스 주목.","impact":0},

    {"date":"2025-04-16","name":"필라델피아연은 제조업지수 악화 — 경기침체 신호","category":"경제지표",
     "keywords":["필라델피아연은","제조업지수","경기침체신호","관세충격","제조업둔화"],
     "desc":"4월 필라델피아연은 제조업지수 급락. 관세 충격으로 제조업 심리 위축 본격화.","impact":-4},
]


# ── 카테고리별 확장 키워드 (입력 텍스트 → 이벤트 매칭용) ────────────
CATEGORY_EXPAND = {
    '금융위기': ['위기','붕괴','파산','폭락','패닉','뱅크런','금융위기','신용위기','레버리지'],
    '금리':     ['금리','연준','Fed','FOMC','인상','인하','기준금리','빅컷','피벗','점도표',
                 '윌리엄스','파월','이사','총재','통화정책','긴축','완화','동결','베이비스텝'],
    '경제지표': ['CPI','물가','인플레이션','고용','실업','비농업','GDP','ISM','PMI','제조업',
                 '소비자물가','신규실업','실업수당','산업생산','소매판매','주택','PCE',
                 '필라델피아','시카고','리치먼드','경기침체','연착륙','스태그플레이션'],
    '지정학':   ['전쟁','러시아','우크라이나','중동','이란','북한','핵','미사일','테러','분쟁',
                 '이스라엘','하마스','가자','NATO','지정학'],
    '무역':     ['관세','무역','미중','중국','보호무역','해방의날','상호관세','Liberation',
                 '수출','수입','무역적자','공급망','USMCA'],
    '기술혁명': ['AI','인공지능','ChatGPT','GPT','DeepSeek','반도체','칩','클라우드',
                 '데이터센터','빅테크','기술주','나스닥'],
    '팬데믹':   ['코로나','팬데믹','바이러스','봉쇄','백신','감염','확진'],
    '정치':     ['선거','트럼프','대통령','행정명령','DOGE','취임','정치'],
    '원자재':   ['유가','원유','WTI','브렌트','금','에너지','LNG','천연가스','재고'],
    '환율':     ['달러','환율','엔화','원화','달러인덱스','DXY','강달러','약달러'],
    '실적':     ['실적','분기','EPS','매출','가이던스','어닝','earnings','서프라이즈',
                 '실적발표','장전','장후','어닝시즌','분기실적','실적시즌'],
}

# 티커명 → 이벤트 키워드 매핑
TICKER_TO_KW = {
    'TSMC': ['TSMC','TSM','파운드리','반도체'],
    'TSM':  ['TSMC','TSM','파운드리','반도체'],
    'NVDA': ['NVDA','엔비디아','GPU','블랙웰','H100'],
    'PEP':  ['펩시','PEP','소비재','음료'],
    'SCHW': ['슈왑','SCHW','증권','브로커리지'],
    'ABT':  ['애보트','ABT','헬스케어','의료'],
    'AAPL': ['AAPL','애플','아이폰'],
    'MSFT': ['MSFT','마이크로소프트','Azure'],
    'GOOGL':['GOOGL','구글','Alphabet','알파벳','유튜브'],
    'META': ['META','메타','페이스북'],
    'AMZN': ['AMZN','아마존','AWS'],
    'TSLA': ['TSLA','테슬라','전기차'],
}

# ── 한국어/영어/티커 → 정식 티커 매핑 ─────────────────────────────
COMPANY_MAP = {
    # 한국어
    '엔비디아':'NVDA','엔비':'NVDA',
    '애플':'AAPL','아이폰':'AAPL',
    '마이크로소프트':'MSFT','마소':'MSFT',
    '구글':'GOOGL','알파벳':'GOOGL','유튜브':'GOOGL',
    '아마존':'AMZN',
    '메타':'META','페이스북':'META','인스타그램':'META',
    '테슬라':'TSLA',
    'TSMC':'TSM','대만반도체':'TSM','티에스엠씨':'TSM',
    '퀄컴':'QCOM','인텔':'INTC','브로드컴':'AVGO',
    '에이에스엠엘':'ASML','암드':'AMD',
    '펩시':'PEP','펩시코':'PEP',
    '슈왑':'SCHW','찰스슈왑':'SCHW',
    '애보트':'ABT',
    '반도체':'SMH','나스닥':'QQQ',
    '에스앤피':'SPY','금':'GLD','원유':'USO','채권':'TLT',
    '제이피모건':'JPM','JP모건':'JPM','골드만삭스':'GS',
    '모건스탠리':'MS','비자':'V','마스터카드':'MA',
    '존슨앤존슨':'JNJ','화이자':'PFE','일라이릴리':'LLY','릴리':'LLY',
    '코카콜라':'KO','맥도날드':'MCD','월마트':'WMT',
    '엑슨모빌':'XOM','쉐브론':'CVX',
    '뱅크오브아메리카':'BAC','뱅크오':'BAC',
    # 영어 소문자
    'nvidia':'NVDA','apple':'AAPL','microsoft':'MSFT',
    'google':'GOOGL','alphabet':'GOOGL','youtube':'GOOGL',
    'amazon':'AMZN','facebook':'META','instagram':'META',
    'tesla':'TSLA','tsmc':'TSM','taiwan semiconductor':'TSM',
    'qualcomm':'QCOM','intel':'INTC','broadcom':'AVGO',
    'asml':'ASML','amd':'AMD',
    'pepsi':'PEP','pepsico':'PEP',
    'schwab':'SCHW','charles schwab':'SCHW','abbott':'ABT',
    'semiconductor':'SMH','gold':'GLD','oil':'USO',
    'jpmorgan':'JPM','jp morgan':'JPM','goldman':'GS','goldman sachs':'GS',
    'morgan stanley':'MS','visa':'V','mastercard':'MA',
    'pfizer':'PFE','eli lilly':'LLY','lilly':'LLY',
    'johnson':'JNJ','coca cola':'KO','cocacola':'KO',
    'mcdonald':'MCD','walmart':'WMT','exxon':'XOM','chevron':'CVX',
    'bank of america':'BAC',
    # 티커 소문자
    'nvda':'NVDA','aapl':'AAPL','msft':'MSFT','googl':'GOOGL','goog':'GOOGL',
    'amzn':'AMZN','tsla':'TSLA','tsm':'TSM','qcom':'QCOM','intc':'INTC',
    'avgo':'AVGO','smh':'SMH','spy':'SPY','qqq':'QQQ','gld':'GLD',
    'uso':'USO','tlt':'TLT','jpm':'JPM','bac':'BAC','gs':'GS',
    'pfe':'PFE','lly':'LLY','jnj':'JNJ','ko':'KO','mcd':'MCD',
    'wmt':'WMT','xom':'XOM','cvx':'CVX','pep':'PEP','schw':'SCHW','abt':'ABT',
}

# 티커 표시명
TICKER_DISPLAY = {
    'NVDA':'NVIDIA','AAPL':'Apple','MSFT':'Microsoft','GOOGL':'Alphabet',
    'AMZN':'Amazon','META':'Meta','TSLA':'Tesla','TSM':'TSMC','QCOM':'Qualcomm',
    'INTC':'Intel','AVGO':'Broadcom','AMD':'AMD','ASML':'ASML',
    'SMH':'반도체ETF','SPY':'S&P500','QQQ':'나스닥100','GLD':'금ETF',
    'USO':'원유ETF','TLT':'장기채권','JPM':'JPMorgan','BAC':'BofA',
    'GS':'Goldman','MS':'Morgan Stanley','V':'Visa','MA':'Mastercard',
    'PFE':'Pfizer','LLY':'Eli Lilly','JNJ':'J&J','KO':'Coca-Cola',
    'MCD':"McDonald's",'WMT':'Walmart','XOM':'ExxonMobil','CVX':'Chevron',
    'PEP':'PepsiCo','SCHW':'Charles Schwab','ABT':'Abbott',
}

# 관련주 매핑
RELATED_TICKERS = {
    'TSM':  ['NVDA','AMD','ASML','QCOM','SMH'],
    'NVDA': ['TSM','AMD','ASML','AVGO','SMH'],
    'AMD':  ['NVDA','TSM','INTC','SMH'],
    'INTC': ['AMD','TSM','NVDA','SMH'],
    'ASML': ['TSM','NVDA','AMD','SMH'],
    'QCOM': ['TSM','NVDA','AAPL','SMH'],
    'AVGO': ['TSM','NVDA','QCOM','SMH'],
    'SMH':  ['TSM','NVDA','AMD'],
    'AAPL': ['MSFT','GOOGL','META','NVDA'],
    'MSFT': ['GOOGL','AMZN','AAPL','NVDA'],
    'GOOGL':['META','MSFT','AMZN'],
    'META': ['GOOGL','AAPL','AMZN'],
    'AMZN': ['MSFT','GOOGL','AAPL'],
    'TSLA': ['NVDA','QQQ'],
    'GLD':  ['SPY','TLT'],
    'USO':  ['XOM','CVX','SPY'],
    'TLT':  ['SPY','GLD'],
    'PEP':  ['KO','WMT','SPY'],
    'SCHW': ['JPM','GS','MS'],
    'ABT':  ['JNJ','PFE','LLY'],
    'JPM':  ['GS','MS','BAC'],
    'GS':   ['JPM','MS','BAC'],
    'PFE':  ['LLY','JNJ','ABT'],
    'LLY':  ['PFE','JNJ','ABT'],
    'XOM':  ['CVX','USO'],
    'CVX':  ['XOM','USO'],
}


def detect_tickers(scenario_text: str) -> dict:
    """시나리오에서 종목 자동 감지 → main / related / baseline 분류"""
    txt_lower = scenario_text.lower()
    main = set()
    for key, ticker in COMPANY_MAP.items():
        if key.lower() in txt_lower:
            main.add(ticker)
    main -= {'SPY', 'QQQ'}  # baseline 별도 관리

    related = set()
    for t in list(main):
        for r in RELATED_TICKERS.get(t, [])[:3]:
            if r not in main and r not in ('SPY', 'QQQ'):
                related.add(r)

    main_list    = sorted(main)
    related_list = sorted(related)[:4]
    all_tickers  = ['SPY','QQQ'] + main_list + related_list
    return {
        'main':     main_list,
        'related':  related_list,
        'baseline': ['SPY','QQQ'],
        'all':      all_tickers,
    }


def match_events(scenario_text: str, top_n: int = 6,
                 year_from: int = None, year_to: int = None) -> list:
    """
    키워드 기반 이벤트 매칭 — API 불필요, 순수 DB 검색

    ★ 핵심 규칙:
    1. 기업명 감지 시 → 해당 기업 이벤트만 표시 (하드 필터)
    2. 연도 우선 정렬: 최신 연도 전체 → 없으면 전년도 → 그 전년도 순
    """
    txt_lower = scenario_text.lower()

    # ── 연도 범위 필터 ──────────────────────────────────────────────
    target_db = [
        e for e in EVENTS_DB
        if (year_from is None or int(e['date'][:4]) >= year_from)
        and (year_to   is None or int(e['date'][:4]) <= year_to)
    ]

    # ── 입력에서 기업명 감지 (한국어·영어·티커 모두 인식) ──────────────
    _exclude_tickers = {'SPY','QQQ','SMH','GLD','USO','TLT','BTC-USD'}
    input_companies = set()
    for key, ticker in COMPANY_MAP.items():
        if key.lower() in txt_lower and ticker not in _exclude_tickers:
            input_companies.add(ticker)

    # ── 이벤트별 점수 계산 ─────────────────────────────────────────
    def _score(ev):
        ev_combined = (ev['name'] + ' ' + ' '.join(ev['keywords'])).lower()
        score = 0
        matched = []

        # ① 기업 감지 시: 해당 기업 이벤트인지 확인 (하드 필터)
        if input_companies:
            company_hit = False
            for ticker in input_companies:
                aliases = [ticker] + TICKER_TO_KW.get(ticker, [])
                if any(a.lower() in ev_combined for a in aliases):
                    company_hit = True
                    score += 10
                    if ticker not in matched:
                        matched.append(ticker)
                    break
            if not company_hit:
                return None  # 다른 기업 이벤트는 완전 제외

        # ② DB 키워드 직접 매칭 (+4점)
        for kw in ev['keywords']:
            if kw.lower() in txt_lower:
                score += 4
                matched.append(kw)

        # ③ 카테고리 확장 키워드 매칭 (+2점)
        for kw in CATEGORY_EXPAND.get(ev['category'], []):
            if kw.lower() in txt_lower and kw not in matched:
                score += 2
                matched.append(kw)

        # ④ 이벤트 이름 단어 매칭 (+2점, 2글자 이상)
        for nt in re.split(r'[\s\-—·\(\)]+', ev['name'].lower()):
            if len(nt) >= 2 and nt in txt_lower and nt not in matched:
                score += 2
                matched.append(nt)

        # ⑤ 티커 직접 입력 매칭 (+3점)
        for ticker, kws in TICKER_TO_KW.items():
            if ticker.lower() in txt_lower:
                if any(kw.lower() in ev_combined for kw in kws):
                    score += 3
                    if ticker not in matched:
                        matched.append(ticker)
                    break

        # ⑥ 연도 직접 언급 (+1점)
        if ev['date'][:4] in txt_lower:
            score += 1

        # 기업 미지정 시 최소 점수 기준
        if not input_companies and score < 3:
            return None

        return score, list(dict.fromkeys(matched))

    # ── 전체 이벤트 채점 ───────────────────────────────────────────
    candidates = []
    for ev in target_db:
        result = _score(ev)
        if result is None:
            continue
        score, matched = result
        candidates.append({
            **ev,
            'matched_keywords': matched,
            'match_score':      score,
            'recency_bonus':    0,
            '_year':            int(ev['date'][:4]),
        })

    # ── ★ 정렬: 최신 연도 전체 우선 → 동년도는 점수 내림차순 ──────────
    # "2025년 매칭 전부 → 없으면 2024년 전부 → ..." 방식
    candidates.sort(key=lambda x: (-x['_year'], -x['match_score']))

    # 결과에서 _year 내부 필드 제거
    for c in candidates:
        c.pop('_year', None)

    return candidates[:top_n]


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
    req      = request.get_json()
    scenario = req.get('scenario', '').strip()
    year_from = req.get('year_from')  # None = 전체
    year_to   = req.get('year_to')

    if not scenario:
        return jsonify({'error': '시나리오를 입력해주세요.'}), 400

    try:
        # 연도 정수 변환
        yf_ = int(year_from) if year_from else None
        yt_ = int(year_to)   if year_to   else None

        # 종목 자동 감지
        ticker_info = detect_tickers(scenario)

        # 이벤트 매칭
        matched = match_events(scenario, top_n=6, year_from=yf_, year_to=yt_)

        # 차트 데이터 수집 (자동 감지된 종목 + baseline)
        all_tickers = ticker_info['all'] if ticker_info['all'] else ['SPY','QQQ','GLD']
        charts = {}
        for ev in matched:
            charts[ev['date']] = get_chart_data(ev['date'], all_tickers)

        return jsonify({
            'events':      matched,
            'charts':      charts,
            'ticker_info': ticker_info,
            'ticker_display': TICKER_DISPLAY,
        })

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
.result-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;}
.result-count{font-size:.82rem;color:var(--sub);}

/* ── 이벤트 카드 ── */
.ev-grid{display:grid;gap:12px;}
.ev-card{border:1.5px solid var(--border);border-radius:12px;padding:16px 20px;cursor:pointer;transition:all .18s;background:#fff;}
.ev-card:hover{border-color:var(--navy);box-shadow:0 3px 12px rgba(26,58,92,.1);}
.ev-card.sel{border-color:var(--navy);background:#f0f4fa;box-shadow:0 3px 12px rgba(26,58,92,.12);}
.ev-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;flex-wrap:wrap;gap:6px;}
.ev-date{font-size:.82rem;color:var(--sub);font-family:monospace;letter-spacing:.5px;font-weight:700;}
.ev-meta{display:flex;gap:6px;align-items:center;flex-wrap:wrap;}
.cat-badge{font-size:.7rem;padding:3px 9px;border-radius:10px;font-weight:700;background:#e8eef8;color:var(--navy);}
.score-badge{background:var(--navy);color:#fff;padding:3px 9px;border-radius:10px;font-size:.7rem;font-weight:700;}
.ev-name{font-weight:800;font-size:.96rem;margin-bottom:7px;color:#1a1a1a;}
.ev-desc{font-size:.85rem;color:#333;line-height:1.62;margin-bottom:8px;}
.ev-kws{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:9px;}
.kw-tag{font-size:.7rem;padding:2px 8px;border-radius:12px;background:#f0f4fa;color:var(--navy);border:1px solid #c8d8ee;font-weight:600;}
.kw-tag.hit{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7;font-weight:700;}
.ev-impact{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;margin-top:6px;}
.ev-impact.pos{background:#e8f5e9;border:1px solid #a5d6a7;}
.ev-impact.neg{background:#fce4e4;border:1px solid #e57373;}
.ev-impact.neu{background:#f5f5f0;border:1px solid #ddd;}
.impact-lbl{font-size:.75rem;color:#555;}
.impact-val{font-size:.95rem;font-weight:900;}
.impact-val.pos{color:#1b5e20;}
.impact-val.neg{color:#c62828;}
.impact-val.neu{color:#555;}
.impact-note{font-size:.73rem;color:#888;margin-left:4px;}

/* ── 차트 ── */
.chart-wrap{width:100%;height:460px;}
.chart-note{text-align:center;font-size:.73rem;color:#aaa;margin-top:8px;}

/* ── 복사 버튼 영역 ── */
.copy-bar{display:flex;gap:10px;margin-top:16px;flex-wrap:wrap;}
.copy-btn{flex:1;min-width:160px;padding:11px 16px;border:1.5px solid var(--navy);border-radius:9px;background:#fff;color:var(--navy);font-size:.84rem;font-weight:700;cursor:pointer;transition:all .18s;display:flex;align-items:center;justify-content:center;gap:7px;}
.copy-btn:hover{background:var(--navy);color:#fff;}
.copy-btn.copied{background:#00838f;border-color:#00838f;color:#fff;}
.copy-btn-raw{border-color:#888;color:#555;}
.copy-btn-raw:hover{background:#555;border-color:#555;color:#fff;}
.no-result{text-align:center;padding:40px 20px;color:var(--sub);font-size:.9rem;}

/* ── 조사 기간 ── */
.period-row{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:4px;}
.period-grp{display:flex;flex-direction:column;gap:4px;}
.period-lbl{font-size:.75rem;color:var(--sub);font-weight:600;}
.year-sel{padding:7px 10px;border:1.5px solid var(--border);border-radius:8px;font-size:.88rem;background:#fafaf6;cursor:pointer;color:var(--text);min-width:90px;}
.year-sel:focus{outline:none;border-color:var(--navy);}
.period-sep{font-size:1.1rem;font-weight:700;color:var(--sub);padding-bottom:6px;}

/* ── 종목 pill ── */
.ticker-pills{display:flex;flex-wrap:wrap;gap:8px;}
.t-pill{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;border-radius:20px;font-size:.78rem;font-weight:700;border:1.5px solid;}
.t-pill.main{background:#1a3a5c;color:#fff;border-color:#1a3a5c;}
.t-pill.related{background:#e8eef8;color:#1a3a5c;border-color:#1a3a5c55;}
.t-pill.baseline{background:#f5f5f5;color:#888;border-color:#ccc;}
</style>
</head>
<body>

<div class="hdr">
  <div>
    <div class="hdr-title">📊 역사적 시나리오 분석기</div>
    <div class="hdr-sub">Historical Pattern Matcher — Jason Market</div>
  </div>
  <div class="hdr-badge">API 불필요 · 키워드 매칭</div>
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

  <!-- 조사 기간 + 실행 -->
  <div class="card">
    <div class="ctitle">🗓️ 조사 기간 설정</div>
    <div class="period-row">
      <div class="period-grp">
        <label class="period-lbl">시작 연도</label>
        <select id="yearFrom" class="year-sel"></select>
      </div>
      <div class="period-sep">~</div>
      <div class="period-grp">
        <label class="period-lbl">종료 연도</label>
        <select id="yearTo" class="year-sel"></select>
      </div>
      <div style="flex:1;font-size:.77rem;color:var(--sub);align-self:flex-end;padding-bottom:4px">
        전체 DB: 1929~2026 | 기본값: 2018~2026 (최신 우선 정렬)
      </div>
    </div>
    <div style="margin-top:10px;font-size:.8rem;color:var(--sub)">
      💡 종목명은 한국어·영어·티커 모두 인식 — 예) <b>엔비디아, TSMC, nvda, 나스닥</b>
    </div>
    <button class="btn-go" id="goBtn" onclick="doAnalyze()">🔍 역사적 유사 시점 분석 시작</button>
  </div>

  <!-- 로딩 -->
  <div class="loading" id="ld">
    <div class="spin"></div>
    <p><strong>키워드 매칭</strong> + 주가 데이터 수집 중...</p>
    <p>약 10~30초 소요됩니다.</p>
  </div>

  <!-- 결과 -->
  <div id="results">

    <!-- 감지 종목 표시 -->
    <div class="card" id="tickerInfoCard" style="display:none">
      <div class="ctitle" style="margin-bottom:10px">🔎 감지된 종목 및 차트 구성</div>
      <div id="tickerPills"></div>
      <div style="font-size:.75rem;color:var(--sub);margin-top:8px">
        ★ 강조선 = 직접 언급 종목 | 보조선 = 관련주 | 회색선 = SPY·QQQ 기준선
      </div>
    </div>

    <div class="card">
      <div class="result-header">
        <div class="ctitle" style="margin-bottom:0">🕰️ 키워드 매칭 역사적 이벤트 — 클릭하면 차트 표시</div>
        <span class="result-count" id="resultCount"></span>
      </div>
      <div class="ev-grid" id="evCards"></div>
    </div>

    <div class="card" id="chartCard" style="display:none">
      <div class="ctitle" id="chartTitle">📈 주가 흐름</div>
      <div class="chart-wrap" id="chartDiv"></div>
      <div class="chart-note">빨간 점선 = 이벤트 발생일 (기준 100) | 전(6개월) / 후(12개월)</div>
    </div>

    <div class="card">
      <div class="ctitle">📤 데이터 내보내기 — 다른 AI로 분석하기</div>
      <div style="font-size:.82rem;color:var(--sub);margin-bottom:12px;line-height:1.6">
        위 매칭 결과를 복사해서 ChatGPT·Claude·Gemini 등에 붙여넣으면 더 깊은 분석이 가능합니다.
      </div>
      <div class="copy-bar">
        <button class="copy-btn" id="copyAllBtn" onclick="copyAll()">📋 전체 텍스트 복사 (AI 분석용)</button>
        <button class="copy-btn copy-btn-raw" id="copyRawBtn" onclick="copyRaw()">📄 원시 JSON 복사</button>
      </div>
      <div style="font-size:.72rem;color:#bbb;margin-top:12px;text-align:center">
        ⚠️ 역사적 팩트 데이터 기반 참고용 — 투자 조언 아님 | DB 이벤트 총 127개
      </div>
    </div>

  </div>
</div>

<script>
// ── 종목 색상 (main 강조용) ─────────────────────────────────────
const MAIN_COLORS = {
  NVDA:'#76B900',TSM:'#CE0E2D',AMD:'#ED1C24',AAPL:'#555555',
  MSFT:'#107C10',GOOGL:'#4285F4',AMZN:'#FF9900',META:'#0866FF',
  TSLA:'#E31937',QCOM:'#3253DC',INTC:'#0071C5',AVGO:'#CC0000',
  ASML:'#F7941D',SMH:'#7B2FBE',GLD:'#b8860b',USO:'#795548',
  TLT:'#00796B',JPM:'#003087',GS:'#6D8B74',PFE:'#00549e',
  LLY:'#D52B1E',JNJ:'#D62828',KO:'#F40009',MCD:'#FFC72C',
  WMT:'#007DC6',XOM:'#E32218',CVX:'#00829B',PEP:'#004B93',
  SCHW:'#00A0DF',ABT:'#0065BD',BAC:'#E31837',MS:'#002244',
};

let lastRawData   = null;
let lastScenario  = '';
let chartCache    = {};
let curEvent      = null;
let curTickerInfo = {main:[], related:[], baseline:['SPY','QQQ'], all:[]};

// ── 연도 select 생성 ────────────────────────────────────────────
(function buildYearSelects() {
  const fromSel = document.getElementById('yearFrom');
  const toSel   = document.getElementById('yearTo');
  for (let y = 2026; y >= 1929; y--) {
    fromSel.add(new Option(y, y, y===2018, y===2018));
    toSel  .add(new Option(y, y, y===2026, y===2026));
  }
})();

function setEx(btn) { document.getElementById('si').value = btn.textContent; }

async function doAnalyze() {
  const scenario  = document.getElementById('si').value.trim();
  if (!scenario)  { alert('시나리오를 입력해주세요.'); return; }
  lastScenario    = scenario;
  const year_from = parseInt(document.getElementById('yearFrom').value);
  const year_to   = parseInt(document.getElementById('yearTo').value);

  if (year_from > year_to) { alert('시작 연도가 종료 연도보다 클 수 없습니다.'); return; }

  const btn = document.getElementById('goBtn');
  btn.disabled = true;
  document.getElementById('ld').style.display      = 'block';
  document.getElementById('results').style.display = 'none';
  document.getElementById('chartCard').style.display = 'none';
  chartCache = {}; curEvent = null;

  try {
    const res  = await fetch('/analyze', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ scenario, year_from, year_to })
    });
    const data = await res.json();
    if (data.error) { alert('오류: ' + data.error); return; }
    renderAll(data);
  } catch(e) {
    alert('오류: ' + e.message);
  } finally {
    btn.disabled = false;
    document.getElementById('ld').style.display = 'none';
  }
}

// 카테고리 색상
const CAT_COLOR = {
  '금융위기':'#c62828','금리':'#1565c0','경제지표':'#00838f','지정학':'#6a1b9a',
  '무역':'#e65100','기술혁명':'#2e7d32','팬데믹':'#558b2f','정치':'#37474f',
  '원자재':'#f57f17','환율':'#0277bd','실적':'#ad1457',
};

function renderAll(data) {
  lastRawData    = data;
  chartCache     = data.charts || {};
  curTickerInfo  = data.ticker_info || {main:[],related:[],baseline:['SPY','QQQ'],all:[]};
  const tdisplay = data.ticker_display || {};
  const events   = data.events || [];

  // ── 감지 종목 pills ───────────────────────────────────────────
  const pillCard = document.getElementById('tickerInfoCard');
  const pillEl   = document.getElementById('tickerPills');
  pillEl.innerHTML = '';
  const allPills = [
    ...curTickerInfo.main.map(t=>({t,cls:'main',lbl:`★ ${t} (${tdisplay[t]||t})`})),
    ...curTickerInfo.related.map(t=>({t,cls:'related',lbl:`${t} (${tdisplay[t]||t}) 관련`})),
    ...curTickerInfo.baseline.map(t=>({t,cls:'baseline',lbl:`${t} 기준선`})),
  ];
  if (allPills.length) {
    const wrap = document.createElement('div');
    wrap.className = 'ticker-pills';
    allPills.forEach(({t,cls,lbl}) => {
      const sp = document.createElement('span');
      sp.className = `t-pill ${cls}`;
      if (cls==='main') sp.style.borderColor = MAIN_COLORS[t]||'#1a3a5c';
      if (cls==='main') sp.style.background  = MAIN_COLORS[t]||'#1a3a5c';
      sp.textContent = lbl;
      wrap.appendChild(sp);
    });
    pillEl.appendChild(wrap);
    pillCard.style.display = 'block';
  } else {
    pillCard.style.display = 'none';
  }

  // ── 이벤트 카드 ───────────────────────────────────────────────
  document.getElementById('resultCount').textContent = `${events.length}개 이벤트 매칭됨`;
  const evEl = document.getElementById('evCards');
  evEl.innerHTML = '';

  if (!events.length) {
    evEl.innerHTML = '<div class="no-result">⚠️ 해당 기간에 매칭된 이벤트가 없습니다. 연도 범위를 넓히거나 키워드를 변경해보세요.</div>';
    document.getElementById('results').style.display = 'block';
    return;
  }

  events.forEach((ev, i) => {
    const impact = ev.impact;
    const impCls = impact == null ? 'neu' : impact > 0 ? 'pos' : impact < 0 ? 'neg' : 'neu';
    const impTxt = impact == null ? '데이터 없음'
      : impact === 0 ? '±0% (중립 / 혼조)'
      : `${impact > 0 ? '+' : ''}${impact}%`;

    const catColor = CAT_COLOR[ev.category] || '#555';
    const allKws   = ev.keywords || [];
    const hitSet   = new Set((ev.matched_keywords||[]).map(k=>k.toLowerCase()));
    const kwHtml   = allKws.map(kw =>
      `<span class="kw-tag${hitSet.has(kw.toLowerCase())?' hit':''}">${kw}</span>`
    ).join('');

    const div = document.createElement('div');
    div.className = 'ev-card' + (i===0?' sel':'');
    div.innerHTML = `
      <div class="ev-top">
        <div class="ev-date">📅 ${ev.date}</div>
        <div class="ev-meta">
          <span class="cat-badge" style="background:${catColor}18;color:${catColor};border:1px solid ${catColor}44">${ev.category}</span>
          <span class="score-badge">매칭 ${ev.match_score}점</span>
        </div>
      </div>
      <div class="ev-name">${ev.name}</div>
      <div class="ev-desc">${ev.desc}</div>
      <div class="ev-kws">${kwHtml}</div>
      <div class="ev-impact ${impCls}">
        <span class="impact-lbl">당시 시장 영향</span>
        <span class="impact-val ${impCls}">${impTxt}</span>
        <span class="impact-note">(S&P500 / 나스닥 기준 추정)</span>
      </div>
    `;
    div.onclick = () => {
      document.querySelectorAll('.ev-card').forEach(c=>c.classList.remove('sel'));
      div.classList.add('sel');
      curEvent = ev.date;
      if (chartCache[ev.date] && Object.keys(chartCache[ev.date]).length)
        renderChart(ev.date, chartCache[ev.date]);
    };
    evEl.appendChild(div);
  });

  document.getElementById('results').style.display = 'block';

  // 첫 이벤트 자동 차트
  if (events.length) {
    const first = events[0];
    if (chartCache[first.date] && Object.keys(chartCache[first.date]).length) {
      curEvent = first.date;
      renderChart(curEvent, chartCache[curEvent]);
    }
  }
}

function copyAll() {
  if (!lastRawData) return;
  const events = lastRawData.events || [];
  const lines = [];
  lines.push('=== 역사적 시나리오 — 키워드 매칭 결과 ===');
  lines.push('');
  lines.push('[입력 시나리오]');
  lines.push(lastScenario);
  lines.push('');
  lines.push(`[매칭된 역사적 이벤트 ${events.length}건]`);
  lines.push('아래 각 이벤트의 역사적 사실을 참고하여 현재 시나리오와 비교 분석해주세요.');
  lines.push('');
  events.forEach((ev, i) => {
    lines.push(`──── ${i+1}번 이벤트 ────`);
    lines.push(`날짜: ${ev.date}`);
    lines.push(`이벤트명: ${ev.name}`);
    lines.push(`카테고리: ${ev.category}`);
    lines.push(`설명: ${ev.desc}`);
    lines.push(`키워드: ${(ev.keywords||[]).join(', ')}`);
    lines.push(`당시 시장 영향: ${ev.impact != null ? (ev.impact >= 0 ? '+' : '') + ev.impact + '%' : '미상'}`);
    lines.push(`매칭 키워드: ${(ev.matched_keywords||[]).join(', ')}`);
    lines.push('');
  });
  lines.push('[분석 요청]');
  lines.push('위 역사적 이벤트들과 현재 입력한 시나리오를 비교하여:');
  lines.push('1. 현재 상황과 가장 유사한 역사적 패턴은 무엇인가?');
  lines.push('2. 당시 이후 시장이 어떻게 움직였는가?');
  lines.push('3. 현재 시나리오에서 주목해야 할 리스크와 기회는?');

  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    const btn = document.getElementById('copyAllBtn');
    btn.textContent = '✅ 복사 완료!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '📋 전체 텍스트 복사 (AI 분석용)'; btn.classList.remove('copied'); }, 2500);
  });
}

function copyRaw() {
  if (!lastRawData) return;
  navigator.clipboard.writeText(JSON.stringify(lastRawData.events, null, 2)).then(() => {
    const btn = document.getElementById('copyRawBtn');
    btn.textContent = '✅ JSON 복사 완료!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '📄 원시 JSON 복사'; btn.classList.remove('copied'); }, 2500);
  });
}

function renderChart(evDate, data) {
  if (!data || !Object.keys(data).length) return;

  const mainSet     = new Set(curTickerInfo.main);
  const relatedSet  = new Set(curTickerInfo.related);
  const baselineSet = new Set(['SPY','QQQ']);
  const available   = Object.keys(data).filter(t => data[t] && data[t].dates?.length);

  const traces = [];

  // ① SPY · QQQ — 얇은 회색 기준선 (뒤에 그림)
  ['SPY','QQQ'].filter(t => available.includes(t)).forEach(t => {
    traces.push({
      x: data[t].dates, y: data[t].values,
      name: `${t} (기준)`,
      type:'scatter', mode:'lines',
      line:{color: t==='QQQ'?'#90CAF9':'#BDBDBD', width:1.5, dash:'dot'},
      opacity:0.65,
      hovertemplate:`<b>${t}</b> %{y:.1f}<extra></extra>`,
    });
  });

  // ② 관련주 — 중간 두께, 반투명
  available.filter(t => relatedSet.has(t) && !baselineSet.has(t)).forEach(t => {
    traces.push({
      x: data[t].dates, y: data[t].values,
      name: t,
      type:'scatter', mode:'lines',
      line:{color: MAIN_COLORS[t]||'#888', width:2},
      opacity:0.72,
      hovertemplate:`<b>${t}</b> %{y:.1f}<extra></extra>`,
    });
  });

  // ③ 직접 언급 main 종목 — 굵고 선명하게, 맨 앞
  const mainAvail = available.filter(t => mainSet.has(t) && !baselineSet.has(t));
  mainAvail.forEach(t => {
    traces.push({
      x: data[t].dates, y: data[t].values,
      name: `★ ${t}`,
      type:'scatter', mode:'lines',
      line:{color: MAIN_COLORS[t]||'#E31937', width:3.8},
      opacity:1.0,
      hovertemplate:`<b>★${t}</b> %{y:.1f}<extra></extra>`,
    });
  });

  // ④ 감지된 종목 없을 때 — 기준선 외 모든 종목 중간 두께로 표시
  if (mainAvail.length === 0 && relatedSet.size === 0) {
    available.filter(t => !baselineSet.has(t)).forEach(t => {
      traces.push({
        x: data[t].dates, y: data[t].values,
        name: t,
        type:'scatter', mode:'lines',
        line:{color: MAIN_COLORS[t]||'#888', width:2.5},
        opacity:0.9,
        hovertemplate:`<b>${t}</b> %{y:.1f}<extra></extra>`,
      });
    });
  }

  if (!traces.length) return;

  const layout = {
    paper_bgcolor:'#fff', plot_bgcolor:'#fafaf6',
    font:{family:'Apple SD Gothic Neo,sans-serif',size:11.5},
    xaxis:{showgrid:true, gridcolor:'#eeeee8', zeroline:false,
           showspikes:true, spikecolor:'#aaa', spikethickness:1},
    yaxis:{title:'상대 수익률 (이벤트 당일 = 100)',
           showgrid:true, gridcolor:'#eeeee8',
           zeroline:true, zerolinecolor:'#ccc'},
    legend:{orientation:'h', y:-0.18, x:0.5, xanchor:'center',
            font:{size:11}, traceorder:'reversed'},
    hovermode:'x unified',
    shapes:[{type:'line', x0:evDate, x1:evDate, y0:0, y1:1, yref:'paper',
             line:{color:'#c62828', width:2, dash:'dash'}}],
    annotations:[{x:evDate, y:0.97, yref:'paper', text:'이벤트일',
                  showarrow:false, font:{color:'#c62828', size:10},
                  xanchor:'left', xshift:6}],
    margin:{t:20, b:70, l:64, r:20},
  };

  document.getElementById('chartTitle').textContent = `📈 ${evDate} 전후 주가 흐름`;
  document.getElementById('chartCard').style.display = 'block';
  Plotly.newPlot('chartDiv', traces, layout,
    {responsive:true, displayModeBar:true,
     modeBarButtonsToRemove:['toImage','sendDataToCloud']});
  document.getElementById('chartCard').scrollIntoView({behavior:'smooth', block:'start'});
}
</script>
</body>
</html>"""


# ── 실행 ─────────────────────────────────────────────────────────
def _kill_port(port: int):
    """이전에 실행 중인 같은 포트 프로세스 강제 종료"""
    import subprocess, signal
    try:
        r = subprocess.run(['lsof', '-ti', f':{port}'],
                           capture_output=True, text=True, timeout=3)
        for pid in r.stdout.strip().split('\n'):
            pid = pid.strip()
            if pid.isdigit():
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except Exception:
                    pass
        import time; time.sleep(0.5)
    except Exception:
        pass


def main():
    port = 5151
    url  = f"http://127.0.0.1:{port}"

    # 이전 서버 프로세스 정리 (코드 변경 후 재실행 시 새 버전 반영)
    _kill_port(port)

    def _open():
        import time; time.sleep(1.3)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    print(f"\n  📊 역사적 시나리오 분석기 시작")
    print(f"  🌐 브라우저 자동 오픈: {url}")
    print(f"  🔍 키워드 매칭 엔진 — API 불필요")
    print(f"  📚 이벤트 DB: {len(EVENTS_DB)}개")
    print(f"  🛑 종료: Ctrl+C\n")
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
