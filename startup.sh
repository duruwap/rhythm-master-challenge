#!/usr/bin/env bash
# 리듬 마스터 챌린지 실행 스크립트 (Ubuntu)
#
#   ./startup.sh            # 포그라운드 실행 (gunicorn, 0.0.0.0:15002)
#   ./startup.sh start      # 백그라운드(데몬) 실행, 로그: logs/server.log
#   ./startup.sh stop       # 백그라운드 서버 중지
#   ./startup.sh restart    # 재시작
#   ./startup.sh status     # 상태 확인
#   ./startup.sh dev        # Flask 개발 서버 (자동 리로드)
#
# 환경 변수: PORT(기본 15002), HOST(기본 0.0.0.0), WORKERS(기본 2),
#            RMC_DATABASE(SQLite 경로, 기본 instance/rhythm_master.sqlite3)
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
APP_DIR="$(pwd)"
VENV="$APP_DIR/.venv"
PORT="${PORT:-15002}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-2}"
PID_FILE="$APP_DIR/logs/server.pid"
LOG_FILE="$APP_DIR/logs/server.log"

info()  { printf '\033[1;35m[rhythm]\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31m[rhythm]\033[0m %s\n' "$*" >&2; exit 1; }

ensure_python() {
  command -v python3 >/dev/null 2>&1 || fail "python3 가 없습니다: sudo apt update && sudo apt install -y python3 python3-venv"
  if [ ! -x "$VENV/bin/python" ]; then
    info "가상환경 생성: $VENV"
    if ! python3 -m venv "$VENV" 2>/dev/null; then
      rm -rf "$VENV"
      fail "venv 생성 실패. 다음을 먼저 실행하세요: sudo apt install -y python3-venv"
    fi
  fi
  local stamp="$VENV/.requirements.sha"
  local want; want="$(sha256sum requirements.txt | cut -d' ' -f1)"
  if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$want" ]; then
    info "의존성 설치 중..."
    "$VENV/bin/pip" install --disable-pip-version-check -q --upgrade pip
    "$VENV/bin/pip" install --disable-pip-version-check -q -r requirements.txt
    echo "$want" > "$stamp"
  fi
  mkdir -p "$APP_DIR/logs" "$APP_DIR/instance"
}

is_running() {
  [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

port_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN
  else
    return 1
  fi
}

gunicorn_args() {
  echo "--bind $HOST:$PORT --workers $WORKERS --threads 4 --timeout 30 --access-logfile - app:app"
}

print_urls() {
  info "접속 주소: http://localhost:$PORT"
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')" || true
  [ -n "${ip:-}" ] && info "같은 네트워크의 모바일/태블릿: http://$ip:$PORT"
  return 0
}

cmd="${1:-run}"
case "$cmd" in
  run|"")
    ensure_python
    port_in_use && fail "포트 $PORT 가 이미 사용 중입니다. (./startup.sh status / stop 확인)"
    print_urls
    # shellcheck disable=SC2046
    exec "$VENV/bin/gunicorn" $(gunicorn_args)
    ;;
  start)
    ensure_python
    is_running && { info "이미 실행 중 (PID $(cat "$PID_FILE"))"; print_urls; exit 0; }
    port_in_use && fail "포트 $PORT 가 이미 사용 중입니다."
    # shellcheck disable=SC2046
    nohup "$VENV/bin/gunicorn" $(gunicorn_args) >>"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1
    is_running || fail "서버 시작 실패. 로그 확인: $LOG_FILE"
    info "백그라운드 실행 (PID $(cat "$PID_FILE")), 로그: $LOG_FILE"
    print_urls
    ;;
  stop)
    if is_running; then
      kill "$(cat "$PID_FILE")"
      for _ in $(seq 1 20); do is_running || break; sleep 0.25; done
      is_running && kill -9 "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
      info "중지했습니다."
    else
      rm -f "$PID_FILE"
      info "실행 중인 서버가 없습니다."
    fi
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    if is_running; then info "실행 중 (PID $(cat "$PID_FILE"), 포트 $PORT)"; print_urls
    else info "중지됨"; fi
    ;;
  dev)
    ensure_python
    print_urls
    FLASK_DEBUG=1 PORT="$PORT" HOST="$HOST" exec "$VENV/bin/python" app.py
    ;;
  *)
    fail "사용법: $0 [run|start|stop|restart|status|dev]"
    ;;
esac
