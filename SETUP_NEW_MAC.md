# Jason Market — 새 Mac 설치 가이드

새 Mac에서 처음 설치할 때 이 순서대로 진행하세요.

---

## 1. 전제 조건

### Xcode Command Line Tools (필수)
```bash
xcode-select --install
```

### Homebrew 설치 (선택 — Python 3.11+ 원할 경우)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
> **왜 Homebrew Python?**  
> macOS 기본 Python 3.9 (CommandLineTools)는 LibreSSL을 사용해  
> `urllib3 v2 only supports OpenSSL 1.1.1+` 경고가 발생합니다.  
> Homebrew Python 3.11+는 OpenSSL을 사용해 이 경고가 없습니다.  
> 기능에는 영향 없으므로 경고가 허용된다면 시스템 Python 3.9로도 됩니다.

---

## 2. 프로젝트 클론

```bash
cd ~
git clone https://github.com/miyoo1016/jason_market.git
cd jason_market
```

---

## 3. venv 재생성 (중요 — 복사된 venv는 사용 금지)

기존 Mac에서 통째로 복사했더라도 **venv는 반드시 새로 생성**해야 합니다.

```bash
cd ~/jason_market

# 기존 venv 삭제 (복사된 것 포함)
rm -rf venv

# 권장: Homebrew Python 3.11 사용 (경고 없음)
# /opt/homebrew/bin/python3.11 -m venv venv

# 또는: 시스템 Python 3.9 사용 (경고 있지만 동작함)
python3 -m venv venv

# 활성화
source venv/bin/activate

# 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. .env 파일 생성

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 입력하세요:

```
ANTHROPIC_API_KEY=sk-ant-...   # 필수 (Claude AI 기능용)
FRED_API_KEY=                  # 선택 (거시경제 지표)
NEWSAPI_KEY=                   # 선택 (뉴스)
```

Google Drive xlsx 경로가 자동 탐지되지 않을 경우:
```
GOOGLE_DRIVE_XLSX_PATH=~/Library/CloudStorage/GoogleDrive-your@gmail.com/내 드라이브/PF/자산계산기(클로드).xlsx
```

---

## 5. Google Drive 데스크톱 앱

포트폴리오 데이터는 Google Drive xlsx에서 읽습니다.

1. [Google Drive 데스크톱 앱 다운로드](https://www.google.com/drive/download/)
2. 설치 후 miyoo1016@gmail.com 계정으로 로그인
3. 동기화 완료 확인

설치 후 xlsx 파일 예상 경로:
```
~/Library/CloudStorage/GoogleDrive-miyoo1016@gmail.com/내 드라이브/PF/자산계산기(클로드).xlsx
```

---

## 6. gspread 인증 (구글시트 직접 API 연동)

gspread를 사용하면 xlsx 없이도 구글시트에서 바로 데이터를 읽습니다.

### credentials.json 준비
**방법 A: 기존 Mac에서 복사 (권장)**
```bash
# 기존 Mac에서 실행
scp ~/.config/gspread/credentials.json new-mac:~/.config/gspread/credentials.json
```

**방법 B: Google Cloud Console에서 재발급**
1. https://console.cloud.google.com/apis/credentials
2. OAuth 2.0 클라이언트 ID → JSON 다운로드
3. `~/.config/gspread/credentials.json` 으로 저장

### 최초 인증 (credentials.json 준비 후 1회만)
```bash
mkdir -p ~/.config/gspread
# credentials.json 복사 후
python3 xlsx_sync.py   # 브라우저가 열리고 Google 계정 인증
```
인증 완료 시 `~/.config/gspread/authorized_user.json` 이 생성됩니다.

> ⚠️ `credentials.json`, `authorized_user.json`은 개인 인증 파일입니다.  
> Git에 절대 커밋하지 마세요 (.gitignore에 이미 포함됨).

---

## 7. `jm` alias 등록

```bash
# ~/.zshrc 에 추가
echo "alias jm='bash ~/jason_market/run.sh'" >> ~/.zshrc
source ~/.zshrc
```

> **기존 alias 방식 (`./venv/bin/python3 menu.py`) 대신 `run.sh`를 사용**  
> `run.sh`는 어느 디렉토리에서 실행해도 프로젝트 루트를 자동으로 찾습니다.

---

## 8. 환경 점검

```bash
cd ~/jason_market
source venv/bin/activate
python3 health_check.py
```

모든 항목이 ✅ 이면 준비 완료입니다.

---

## 9. 실행 검증

```bash
# 방법 1: alias (추천)
jm

# 방법 2: run.sh 직접
~/jason_market/run.sh

# 방법 3: 기존 방식
cd ~/jason_market && ./venv/bin/python3 menu.py
```

**메뉴 1번** 가격 조회 → 정상 작동 확인  
**메뉴 2번** 포트폴리오 손익:
- Google Drive/gspread 연결 전: "캐시(portfolio.json) 사용 중" 표시 → 정상
- Google Drive/gspread 연결 후: "데이터 출처: 구글드라이브 자산계산기.xlsx (실시간)" 표시

---

## 10. 데이터 파일 목록 (Git 미포함 — 직접 확보 필요)

| 파일 | 경로 | 설명 | 확보 방법 |
|------|------|------|-----------|
| `credentials.json` | `~/.config/gspread/credentials.json` | Google OAuth 클라이언트 | 기존 Mac 복사 또는 Cloud Console 재발급 |
| `authorized_user.json` | `~/.config/gspread/authorized_user.json` | OAuth 토큰 캐시 | credentials.json 후 `python3 xlsx_sync.py` 실행 |
| `.env` | `~/jason_market/.env` | API 키 모음 | 기존 Mac 복사 또는 새로 작성 |
| `portfolio.json` | `~/jason_market/state/portfolio.json` | 포트폴리오 캐시 | 기존 Mac 복사 또는 xlsx 동기화로 생성 |

---

## 11. urllib3 LibreSSL 경고 해결 (선택)

macOS 기본 Python 3.9 사용 시 이 경고가 출력됩니다:
```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the ssl module is compiled with LibreSSL 2.8.3.
```

해결 (Homebrew Python 3.11+ 사용):
```bash
brew install python@3.11
rm -rf ~/jason_market/venv
/opt/homebrew/bin/python3.11 -m venv ~/jason_market/venv
source ~/jason_market/venv/bin/activate
pip install -r ~/jason_market/requirements.txt
```
