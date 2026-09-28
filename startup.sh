#!/bin/bash
# 리듬 마스터 챌린지 기동 스크립트 (Ubuntu)
#
#   ./startup.sh              # 기존 프로세스 종료 → git pull → 의존성 → 서버 기동 (포트 15002)
#   ./startup.sh --no-pull    # git pull 없이 재기동
#   ./startup.sh stop | status
#   ./startup.sh dev          # Flask 개발 서버(포그라운드, 자동 리로드)
#
# 실제 동작은 공통 런처 scripts/scs-run.sh 가 담당한다.
#   프로젝트  /scsrun/app/rhythm-master-challenge
#   PID      /scsrun/pid/rhythm-master-challenge.pid
#   로그     /scslog/app/rhythm-master-challenge/app.log
# 설정(포트·워커 수 등)은 scsrun.conf 참고.

APP_NAME="rhythm-master-challenge"
SELF_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

if [ "${1:-}" = "dev" ]; then
    cd "$SELF_DIR" || exit 1
    [ -x venv/bin/python ] || python3 -m venv venv || exit 1
    venv/bin/pip install --disable-pip-version-check -q -r requirements.txt || exit 1
    FLASK_DEBUG=1 PORT="${PORT:-15002}" exec venv/bin/python app.py
fi

# 이 스크립트가 있는 디렉토리를 프로젝트로 사용 (/scsrun/app 밖에서 clone 해도 동작)
export SCS_APP_DIR="${SCS_APP_DIR:-$SELF_DIR}"
exec "$SELF_DIR/scripts/scs-run.sh" "$APP_NAME" "$@"
