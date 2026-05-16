#!/usr/bin/env python3
"""ollama_client.py — Jason Market 로컬 LLM 클라이언트

endpoint  : http://127.0.0.1:11434/api/generate
stream    : false
keep_alive: 30s  (모델 자동 언로드 타이머)
options   : temperature=0.2, num_predict=1800
"""

import re
import time
import requests

# ── 설정 ──────────────────────────────────────────────────────────
OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/generate"
KEEP_ALIVE      = "30s"

# 모델별 timeout (초) — 크기별 차등 적용
MODEL_TIMEOUTS: dict = {
    "gemma4:26b": 240,   # 빠른 분석
    "gemma4:31b": 600,   # 정밀 분석 (기본)
}
DEFAULT_TIMEOUT = 300   # 알 수 없는 모델의 기본값

# Ollama 공통 generation 옵션
# ※ num_predict를 설정하지 않는 이유:
#    Gemma4 / Qwen3 계열은 thinking(내부 추론) 토큰이 num_predict 예산을 먼저 소모해
#    visible output이 0이 되는 문제가 발생합니다.
#    출력 길이 제한은 프롬프트 내 "5줄 이내" 지시로 제어합니다.
DEFAULT_OPTIONS: dict = {
    "temperature": 0.2,
}

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
    model   : str    예) "gemma4:26b" / "gemma4:31b" / "qwen3.6:latest"
    timeout : int    HTTP 타임아웃(초). None이면 MODEL_TIMEOUTS 자동 적용.
    options : dict   generation 옵션. None이면 DEFAULT_OPTIONS 사용.

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
    _options = options if options is not None else DEFAULT_OPTIONS.copy()

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
    # 섹션 6 또는 7 탐색
    match = re.search(r'##\s*[67][.\s]*한\s*줄\s*판정', text)
    if match:
        after = text[match.end():]
        for line in after.split('\n'):
            line = line.strip().lstrip('-').strip()
            if line and not line.startswith('#'):
                return line[:120]
    # 키워드 fallback
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
