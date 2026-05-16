#!/usr/bin/env python3
"""ollama_client.py — Jason Market 로컬 LLM 클라이언트

endpoint  : http://127.0.0.1:11434/api/generate
stream    : false
keep_alive: 30s  (분석 완료 후 30s 뒤 모델 자동 언로드)
timeout   : 300s
"""

import re
import time
import requests

# ── 설정 ──────────────────────────────────────────────────────────
OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/generate"
OLLAMA_TIMEOUT  = 300          # 5분
KEEP_ALIVE      = "30s"        # 분석 완료 후 모델 자동 언로드 타이머

# ── 금지 표현 목록 ─────────────────────────────────────────────────
FORBIDDEN_PHRASES = [
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

def generate(prompt: str, model: str = "gemma4:26b") -> dict:
    """
    Ollama /api/generate 호출 (stream=false).

    Parameters
    ----------
    prompt : str    완성된 분석 프롬프트
    model  : str    예) "gemma4:26b" / "gemma4:31b"

    Returns
    -------
    dict
        success : bool
        text    : str   응답 텍스트 (실패 시 "")
        error   : str   오류 메시지 (성공 시 "")
        elapsed : float 소요 시간(초)
        model   : str   호출한 모델명
    """
    t0 = time.time()
    payload = {
        "model":      model,
        "prompt":     prompt,
        "stream":     False,
        "keep_alive": KEEP_ALIVE,
    }
    try:
        r = requests.post(
            OLLAMA_ENDPOINT,
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        elapsed = round(time.time() - t0, 1)

        if r.status_code == 200:
            text = r.json().get("response", "").strip()
            return {
                "success": True,
                "text":    text,
                "error":   "",
                "elapsed": elapsed,
                "model":   model,
            }
        else:
            return {
                "success": False,
                "text":    "",
                "error":   f"HTTP {r.status_code}: {r.text[:120]}",
                "elapsed": elapsed,
                "model":   model,
            }

    except requests.exceptions.Timeout:
        elapsed = round(time.time() - t0, 1)
        return {
            "success": False,
            "text":    "",
            "error":   f"Timeout ({OLLAMA_TIMEOUT}s 초과)",
            "elapsed": elapsed,
            "model":   model,
        }
    except Exception as exc:
        elapsed = round(time.time() - t0, 1)
        return {
            "success": False,
            "text":    "",
            "error":   str(exc)[:120],
            "elapsed": elapsed,
            "model":   model,
        }


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
    # 소수점 2자리 이상 숫자 추출 (금융 수치 패턴)
    pat = re.compile(r'\d+\.\d{2,}')
    facts_nums = set(pat.findall(data_facts))
    output_nums = set(pat.findall(llm_output))
    suspicious = output_nums - facts_nums
    # 섹션 번호(예: "1.23" 같은 단순 수)는 제외
    suspicious = {n for n in suspicious if float(n) > 10}
    return bool(suspicious), sorted(suspicious)[:5]


def extract_verdict(text: str) -> str:
    """
    LLM 출력에서 '## 7. 한 줄 판정' 이후 첫 실질 줄 추출.
    없으면 '주의/중립/양호' 키워드 검색.
    """
    # 섹션 7 이후 텍스트
    match = re.search(r'##\s*7[.\s]*한\s*줄\s*판정', text)
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
