#!/usr/bin/env python3
"""ollama_client.py — Jason Market 로컬 LLM 클라이언트

endpoint  : http://127.0.0.1:11434/api/generate
stream    : false
keep_alive: 30s  (모델 자동 언로드 타이머)
num_predict: 모델별 차등 (thinking 토큰 예산 확보)
"""

import re
import time
import requests

# ── 설정 ──────────────────────────────────────────────────────────
OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/generate"
KEEP_ALIVE      = "30s"

# 모델별 timeout (초)
MODEL_TIMEOUTS: dict = {
    "gemma4:26b": 300,   # 빠른 분석
    "gemma4:31b": 600,   # 정밀 분석 (기본)
}
DEFAULT_TIMEOUT = 300

# 모델별 generation 옵션
# ※ num_predict 설정 이유:
#    Gemma4 계열은 thinking(내부 추론) 토큰이 먼저 실행된다.
#    num_predict가 너무 작으면 thinking 단계에서 예산을 소모해 visible output이 0이 된다.
#    4096 / 6144로 충분한 예산을 확보하여 이 문제를 방지한다.
MODEL_OPTIONS: dict = {
    "gemma4:26b": {"temperature": 0.2, "num_predict": 4096},
    "gemma4:31b": {"temperature": 0.2, "num_predict": 6144},
}
DEFAULT_OPTIONS: dict = {"temperature": 0.2}   # 알 수 없는 모델 fallback

# ── 금지 표현 목록 ─────────────────────────────────────────────────
FORBIDDEN_PHRASES: list = [
    "강력 매수", "강력 매도",
    "지금 사야", "지금 팔아야",
    "확정 상승", "확정 하락",
    "폭락 확정", "수익 보장",
    "투자 추천",
]


# ── 연결 확인 ─────────────────────────────────────────────────────

def is_available() -> bool:
    """Ollama 서버 연결 가능 여부 (3s 타임아웃)"""
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ── 생성 ──────────────────────────────────────────────────────────

def generate(prompt: str,
             model: str = "gemma4:26b",
             timeout: int | None = None,
             options: dict | None = None) -> dict:
    """
    Ollama /api/generate 호출 (stream=false).

    Parameters
    ----------
    prompt  : str    완성된 분석 프롬프트
    model   : str    예) "gemma4:26b" / "gemma4:31b"
    timeout : int    HTTP 타임아웃(초). None이면 MODEL_TIMEOUTS 자동 적용.
    options : dict   generation 옵션. None이면 MODEL_OPTIONS 자동 적용.

    Returns
    -------
    dict
        success : bool
        text    : str    응답 텍스트 (실패 시 "")
        error   : str    오류 메시지 (성공 시 "")
        elapsed : float  소요 시간(초)
        model   : str    호출한 모델명
    """
    _timeout = timeout if timeout is not None else MODEL_TIMEOUTS.get(model, DEFAULT_TIMEOUT)
    _options = options if options is not None else MODEL_OPTIONS.get(model, DEFAULT_OPTIONS).copy()

    payload = {
        "model":      model,
        "prompt":     prompt,
        "stream":     False,
        "keep_alive": KEEP_ALIVE,
        "options":    _options,
    }

    t0 = time.time()
    try:
        r = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=_timeout)
        elapsed = round(time.time() - t0, 1)

        if r.status_code == 200:
            text = r.json().get("response", "").strip()
            return {"success": True,  "text": text, "error": "",
                    "elapsed": elapsed, "model": model}
        else:
            return {"success": False, "text": "",
                    "error":   f"HTTP {r.status_code}: {r.text[:120]}",
                    "elapsed": elapsed, "model": model}

    except requests.exceptions.Timeout:
        elapsed = round(time.time() - t0, 1)
        return {"success": False, "text": "",
                "error":   f"Timeout ({_timeout}s 초과)",
                "elapsed": elapsed, "model": model}
    except Exception as exc:
        elapsed = round(time.time() - t0, 1)
        return {"success": False, "text": "",
                "error":   str(exc)[:120],
                "elapsed": elapsed, "model": model}


# ── 검증 ──────────────────────────────────────────────────────────

def is_valid_response(text: str) -> bool:
    """
    응답이 유효한지 판단.

    아래 조건이면 False (빈 응답 또는 불완전 응답):
    - None / 빈 문자열
    - strip 후 50자 미만
    - 마크다운 제목(##)과 판정 키워드(주의/중립/양호) 모두 없음
    """
    if not text or len(text.strip()) < 50:
        return False
    has_heading = bool(re.search(r'^##?\s+', text, re.MULTILINE))
    has_verdict = any(w in text for w in ('주의', '중립', '양호', '판정'))
    return has_heading or has_verdict


def validate_output(text: str) -> tuple:
    """
    금지 표현 검사.

    Returns
    -------
    (text: str, found_phrases: list[str])
    """
    found = [p for p in FORBIDDEN_PHRASES if p in text]
    return text, found


def check_number_distortion(data_facts: str, llm_output: str) -> tuple:
    """
    LLM 출력에 DATA FACTS에 없는 숫자(소수점 2자리 이상)가 있는지 확인.
    단순 휴리스틱 — 오탐 가능성 있음.

    Returns
    -------
    (is_suspicious: bool, suspicious_nums: list[str])
    """
    pat = re.compile(r'\d+\.\d{2,}')
    facts_nums  = set(pat.findall(data_facts))
    output_nums = set(pat.findall(llm_output))
    suspicious  = output_nums - facts_nums
    suspicious  = {n for n in suspicious if float(n) > 10}
    return bool(suspicious), sorted(suspicious)[:5]


def extract_verdict(text: str) -> str:
    """
    LLM 출력에서 '한 줄 판정' 섹션(## 6 또는 ## 7) 이후 첫 실질 줄 추출.
    없으면 '주의/중립/양호' 키워드 검색.
    """
    match = re.search(r'##\s*[67][.\s]*한\s*줄\s*판정', text)
    if match:
        after = text[match.end():]
        for line in after.split('\n'):
            line = line.strip().lstrip('-').strip()
            if line and not line.startswith('#'):
                return line[:120]
    for word in ['주의', '중립', '양호']:
        if word in text:
            return word
    return "판정 없음"


def memo_quality(res: dict) -> tuple:
    """
    결과 dict로 간단 규칙 기반 장점/단점 메모 생성.

    Returns
    -------
    (pros: str, cons: str)
    """
    if not res.get('success'):
        err = res.get('error', '')
        if 'Timeout' in err or 'timeout' in err:
            return "", "실행 불가 (timeout)"
        return "", f"연결 실패 ({err[:30]})"

    text = res.get('text', '')
    _, forb = validate_output(text)
    length  = len(text)

    if forb:
        return "분석 완료", "표현 검증 필요"
    if length < 300:
        return "빠른 응답", "분석이 짧음"
    return "기본 검증 통과", ""
