#!/usr/bin/env bash
# run.sh — 어느 디렉토리에서 실행해도 프로젝트 루트를 기준으로 jason_market 실행
# 사용법: ./run.sh  또는  bash ~/jason_market/run.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
MENU="$SCRIPT_DIR/menu.py"

if [ ! -f "$VENV_PYTHON" ]; then
    echo ""
    echo "  ⚠ venv가 없습니다. 아래 명령어로 생성하세요:"
    echo ""
    echo "    cd $SCRIPT_DIR"
    echo "    python3 -m venv venv"
    echo "    source venv/bin/activate"
    echo "    pip install -r requirements.txt"
    echo ""
    exit 1
fi

cd "$SCRIPT_DIR"
exec "$VENV_PYTHON" "$MENU" "$@"
