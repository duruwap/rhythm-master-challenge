#!/bin/bash
# 통계 배치 실행 스크립트 (cron 등록용)
#   */10 * * * * /scsrun/app/rhythm-master-challenge/batch/run_summary.sh
# 로그: /scslog/app/rhythm-master-challenge/batch.log
set -u
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
APP_NAME="rhythm-master-challenge"
LOG_DIR="${SCS_LOG_ROOT:-/scslog/app}/$APP_NAME"
PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"
mkdir -p "$LOG_DIR"
# 서버와 같은 DB 경로 (scsrun.conf 의 RMC_DATABASE 기본값과 동일)
export RMC_DATABASE="${RMC_DATABASE:-$APP_DIR/instance/rhythm_master.sqlite3}"
cd "$APP_DIR" && exec "$PYTHON" -m batch.build_summary >> "$LOG_DIR/batch.log" 2>&1
