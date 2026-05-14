#!/usr/bin/env python3
"""health_check.py — Jason Market 환경 점검
실행: python3 health_check.py  또는  python health_check.py"""

import sys, os, glob, json, unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# .env 로드 (GOOGLE_SHEET_ID 등 환경변수 지원)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SCRIPT_DIR, '.env'))
except Exception:
    pass

OK   = "\033[36m  ✅\033[0m"   # cyan
WARN = "\033[38;5;214m  ⚠\033[0m"  # amber
FAIL = "\033[38;5;203m  ✗\033[0m"  # red
HEAD = "\033[1m"
RST  = "\033[0m"

results = []

def chk(label, ok, detail=""):
    sym = OK if ok else FAIL
    results.append(ok)
    suffix = f"  {detail}" if detail else ""
    print(f"{sym} {label}{suffix}")

def warn(label, detail=""):
    results.append(None)  # warning = not blocking
    suffix = f"  {detail}" if detail else ""
    print(f"{WARN} {label}{suffix}")

print(f"\n{HEAD}{'━'*60}{RST}")
print(f"{HEAD}  Jason Market — 환경 점검{RST}")
print(f"{'━'*60}\n")

# ── 1. Python 버전 + SSL 확인 ─────────────────────────────────
import ssl as _ssl
v = sys.version_info
ssl_ver = _ssl.OPENSSL_VERSION          # e.g. "LibreSSL 2.8.3" or "OpenSSL 3.x"
is_libre = "LibreSSL" in ssl_ver
ok = (v.major == 3 and v.minor >= 9)
chk(f"Python {v.major}.{v.minor}.{v.micro}", ok, f"({sys.executable})")
chk(f"SSL: {ssl_ver}", not is_libre)
if is_libre:
    print()
    print(f"  {WARN} urllib3 v2 경고 원인: Python 3.9 (CommandLineTools) = LibreSSL")
    print(f"       기능은 동작하지만 경고를 없애려면 venv를 재생성하세요.")
    print(f"\n  {HEAD}▶ 권장 venv 재생성 명령:{RST}")
    print(f"    cd ~/jason_market")
    print(f"    rm -rf venv")
    print(f"    python3 -m venv venv")
    print(f"    source venv/bin/activate")
    print(f"    pip install --upgrade pip && pip install -r requirements.txt")
    print()

# ── 2. venv 사용 여부 ──────────────────────────────────────────
in_venv = (
    hasattr(sys, 'real_prefix') or
    (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
)
chk("venv 활성화 여부", in_venv,
    "" if in_venv else "→ source venv/bin/activate 필요")

# ── 3. 필수 패키지 ────────────────────────────────────────────
print()
print(f"  {HEAD}[패키지]{RST}")
REQUIRED = ["yfinance", "pandas", "numpy", "requests",
            "anthropic", "gspread", "openpyxl", "flask",
            "plotly", "scipy", "dotenv"]
for pkg in REQUIRED:
    try:
        import importlib
        importlib.import_module(pkg if pkg != "dotenv" else "dotenv")
        chk(f"  {pkg}", True)
    except ImportError:
        chk(f"  {pkg}", False, "→ pip install -r requirements.txt")

# ── 4. yfinance 실제 조회 ──────────────────────────────────────
print()
print(f"  {HEAD}[yfinance 조회 테스트]{RST}")
try:
    import yfinance as yf
    ticker = yf.Ticker("SPY")
    price = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
    chk("  SPY 시세 조회", bool(price), f"현재가: ${price:.2f}" if price else "조회 실패")
except Exception as e:
    chk("  SPY 시세 조회", False, str(e)[:60])

# ── 5. gspread credentials ────────────────────────────────────
print()
print(f"  {HEAD}[Google 연동]{RST}")
cred = os.path.expanduser("~/.config/gspread/credentials.json")
auth = os.path.expanduser("~/.config/gspread/authorized_user.json")
chk("  credentials.json", os.path.exists(cred), cred)
chk("  authorized_user.json (OAuth 토큰)", os.path.exists(auth),
    auth if os.path.exists(auth) else "→ python3 xlsx_sync.py 실행 후 브라우저 인증")

# ── 6. Google Sheet ID 확인 및 연동 가능 여부 ─────────────────
# .gsheet 파일 자동 탐색 (NFC 정규화로 한글 파일명 비교)
_env_sheet_name = os.environ.get("GOOGLE_SHEET_NAME", "자산계산기(클로드)")
_target_nfc = unicodedata.normalize("NFC", _env_sheet_name)
_gsheet_doc_id = ""
_gsheet_path   = ""
for _pat in [
    "~/Library/CloudStorage/GoogleDrive-*/내 드라이브/PF/*.gsheet",
    "~/Library/CloudStorage/GoogleDrive-*/My Drive/PF/*.gsheet",
]:
    for _p in glob.glob(os.path.expanduser(_pat)):
        _bn = unicodedata.normalize("NFC", os.path.splitext(os.path.basename(_p))[0])
        if _bn == _target_nfc:
            try:
                _gsheet_doc_id = json.load(open(_p, encoding="utf-8")).get("doc_id", "")
                _gsheet_path = _p
            except Exception:
                pass
            break
    if _gsheet_doc_id:
        break

_env_sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
if _env_sheet_id:
    chk("  GOOGLE_SHEET_ID (.env 지정)", True, _env_sheet_id[:32] + "...")
elif _gsheet_doc_id:
    chk("  .gsheet 파일 자동 감지", True, _gsheet_path)
else:
    warn("  Google Sheet ID 미설정",
         "→ .env에 GOOGLE_SHEET_ID= 추가 또는 .gsheet 파일 위치 확인")

# 연동 가능 여부 종합 판정
_can_gsheet = (os.path.exists(cred) and os.path.exists(auth)
               and bool(_env_sheet_id or _gsheet_doc_id))
if _can_gsheet:
    chk("  Google Sheet 연동 가능", True, "Google Sheet 모드 사용 가능")
else:
    warn("  Google Sheet 연동 불가",
         "→ credentials/authorized_user.json + Sheet ID 모두 필요")

# xlsx 파일 (선택사항 — .gsheet만 있어도 무방)
_env_xlsx = os.environ.get("GOOGLE_DRIVE_XLSX_PATH", "")
_gdrive_xlsx = glob.glob(os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-*/내 드라이브/PF/자산계산기(클로드).xlsx"))
if not _gdrive_xlsx:
    _gdrive_xlsx = glob.glob(os.path.expanduser(
        "~/Library/CloudStorage/GoogleDrive-*/My Drive/PF/자산계산기(클로드).xlsx"))
if _env_xlsx and os.path.exists(os.path.expanduser(_env_xlsx)):
    warn("  xlsx 파일 (.env 지정, 선택사항)", _env_xlsx)
elif _gdrive_xlsx:
    warn("  xlsx 파일 (자동 탐지, 선택사항)", _gdrive_xlsx[0])
else:
    warn("  xlsx 없음 (선택사항)",
         "→ .gsheet가 있으면 Google Sheet 모드로 자동 전환")

# ── 7. portfolio.json 캐시 ────────────────────────────────────
pj = os.path.join(SCRIPT_DIR, "state", "portfolio.json")
chk("  portfolio.json 캐시", os.path.exists(pj), pj if os.path.exists(pj) else "없음 (최초 동기화 필요)")

# ── 8. state/ 폴더 ─────────────────────────────────────────────
print()
print(f"  {HEAD}[폴더 및 권한]{RST}")
state_dir = os.path.join(SCRIPT_DIR, "state")
chk("  state/ 폴더", os.path.isdir(state_dir))
if os.path.isdir(state_dir):
    chk("  state/ 쓰기 권한", os.access(state_dir, os.W_OK))

# ── 9. 하드코딩 경로 감지 ─────────────────────────────────────
print()
print(f"  {HEAD}[하드코딩 경로 잔존 여부]{RST}")
old_paths = ["miyoo1016@gmail.com"]
found_hard = []
skip = {"health_check.py", "SETUP_NEW_MAC.md"}
for pyfile in glob.glob(os.path.join(SCRIPT_DIR, "*.py")):
    if os.path.basename(pyfile) in skip:
        continue
    try:
        content = open(pyfile, encoding="utf-8").read()
        for pat in old_paths:
            if pat in content:
                found_hard.append(f"{os.path.basename(pyfile)}: {pat}")
    except Exception:
        pass
if found_hard:
    for f in found_hard:
        warn(f"  {f}")
else:
    chk("  하드코딩 이메일/경로 없음", True)

# ── 요약 ──────────────────────────────────────────────────────
print(f"\n{'━'*60}")
failed = [r for r in results if r is False]
if not failed:
    print(f"{OK} {HEAD}모든 필수 항목 정상{RST}")
else:
    print(f"{FAIL} {HEAD}점검 필요 항목: {len(failed)}개{RST}")
print(f"{'━'*60}\n")
