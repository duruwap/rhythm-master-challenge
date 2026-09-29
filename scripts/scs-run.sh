#!/bin/bash
# =============================================================================
#  scs-run.sh — /scsrun 공통 앱 기동 스크립트
#
#  사용법:
#    scs-run.sh <앱이름> [start|stop|restart|status] [--no-pull]
#
#    start   (기본) 기존 프로세스 종료 → git pull → venv/의존성 준비 → 서버 기동
#    restart start 와 동일
#    stop    프로세스 종료
#    status  실행 여부 확인
#    --no-pull  git pull 생략
#
#  디렉토리 규칙:
#    프로젝트  /scsrun/app/<앱이름>
#    PID      /scsrun/pid/<앱이름>.pid
#    로그     /scslog/app/<앱이름>/app.log
#    데이터   /scsdat/app/<앱이름>        (DB 등 보존 데이터, 앱에 SCS_DATA_DIR 로 전달)
#    가상환경  /scsrun/app/<앱이름>/venv
#
#  프로젝트별 설정(선택): <프로젝트>/scsrun.conf 를 source 한다. 정의 가능 항목
#    APP_CMD     실행 명령 (기본: "$PYTHON $APP_DIR/app.py")
#    HEALTH_URL  기동 후 확인할 URL (curl 이 있을 때만)
#    그 외 export 한 환경 변수는 앱에 그대로 전달된다.
#
#  경로 재정의(테스트용): SCS_APP_ROOT, SCS_PID_DIR, SCS_LOG_ROOT, SCS_DATA_ROOT, SCS_APP_DIR
# =============================================================================
set -u

APP_NAME="${1:-}"
ACTION="start"
DO_PULL=1
shift || true
for arg in "$@"; do
    case "$arg" in
        start|stop|restart|status) ACTION="$arg" ;;
        --no-pull) DO_PULL=0 ;;
        *) echo "알 수 없는 인자: $arg"; exit 2 ;;
    esac
done
if [ -z "$APP_NAME" ]; then
    echo "사용법: $0 <앱이름> [start|stop|restart|status] [--no-pull]"
    exit 2
fi

APP_DIR="${SCS_APP_DIR:-${SCS_APP_ROOT:-/scsrun/app}/$APP_NAME}"
PID_DIR="${SCS_PID_DIR:-/scsrun/pid}"
PID_FILE="$PID_DIR/$APP_NAME.pid"
LOG_DIR="${SCS_LOG_ROOT:-/scslog/app}/$APP_NAME"
LOG="$LOG_DIR/app.log"
export SCS_DATA_DIR="${SCS_DATA_ROOT:-/scsdat/app}/$APP_NAME"
VENV="$APP_DIR/venv"
PYTHON="$VENV/bin/python"
APP_CMD=""
HEALTH_URL=""

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] [$APP_NAME] $*"; }

[ -d "$APP_DIR" ] || { log "프로젝트 디렉토리가 없습니다: $APP_DIR"; exit 1; }

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

stop_app() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            log "기존 프로세스(PID: $OLD_PID) 종료 중..."
            kill "$OLD_PID"
            # 최대 10초 정상 종료 대기 (gunicorn 워커 정리 시간)
            for _ in $(seq 1 20); do
                kill -0 "$OLD_PID" 2>/dev/null || break
                sleep 0.5
            done
            if kill -0 "$OLD_PID" 2>/dev/null; then
                log "강제 종료(SIGKILL) 실행..."
                kill -9 "$OLD_PID"
            fi
            log "프로세스 종료 완료"
        else
            log "PID 파일은 있으나 실행 중인 프로세스 없음 (PID: $OLD_PID)"
        fi
        rm -f "$PID_FILE"
    else
        log "PID 파일 없음. 기존 프로세스 건너뜀."
    fi
}

git_pull() {
    if [ "$DO_PULL" -eq 0 ]; then
        log "git pull 생략 (--no-pull)"
        return 0
    fi
    log "git pull 실행 중..."
    if ! git -C "$APP_DIR" pull --ff-only; then
        log "git pull 실패. 스크립트를 중단합니다."
        exit 1
    fi
    log "git pull 완료"
}

prepare_venv() {
    if [ ! -x "$PYTHON" ]; then
        log "가상환경 생성: $VENV"
        if ! python3 -m venv "$VENV"; then
            rm -rf "$VENV"
            log "venv 생성 실패. 먼저 실행: sudo apt install -y python3-venv"
            exit 1
        fi
    fi
    local req="$APP_DIR/requirements.txt"
    [ -f "$req" ] || return 0
    local stamp="$VENV/.requirements.sha256"
    local want
    want="$(sha256sum "$req" | cut -d' ' -f1)"
    if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$want" ]; then
        log "의존성 설치 중 (requirements.txt 변경 감지)..."
        if ! "$VENV/bin/pip" install --disable-pip-version-check -q -r "$req"; then
            log "의존성 설치 실패. 스크립트를 중단합니다."
            exit 1
        fi
        echo "$want" > "$stamp"
        log "의존성 설치 완료"
    fi
}

load_conf() {
    # git pull 이후에 읽어야 최신 설정이 반영된다
    if [ -f "$APP_DIR/scsrun.conf" ]; then
        # shellcheck disable=SC1091
        . "$APP_DIR/scsrun.conf"
    fi
    [ -n "$APP_CMD" ] || APP_CMD="$PYTHON $APP_DIR/app.py"
}

start_app() {
    mkdir -p "$PID_DIR" "$LOG_DIR" "$SCS_DATA_DIR"
    log "서버 기동 중..."
    log "명령: $APP_CMD"
    cd "$APP_DIR" || exit 1
    echo "===== [$(ts)] $APP_NAME 기동 =====" >> "$LOG"
    # exec 로 실행해 PID 파일에 실제 서버 프로세스 PID 가 기록되게 한다
    nohup bash -c "exec $APP_CMD" >> "$LOG" 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"
    sleep 2
    if ! kill -0 "$NEW_PID" 2>/dev/null; then
        log "서버가 바로 종료되었습니다. 최근 로그:"
        tail -n 20 "$LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
    if [ -n "$HEALTH_URL" ] && command -v curl >/dev/null 2>&1; then
        local ok=0
        for _ in $(seq 1 10); do
            if curl -fsS -o /dev/null "$HEALTH_URL"; then ok=1; break; fi
            sleep 1
        done
        if [ "$ok" -eq 1 ]; then log "헬스 체크 성공: $HEALTH_URL"
        else log "경고: 헬스 체크 실패 ($HEALTH_URL). 로그를 확인하세요."; fi
    fi
    log "서버 기동 완료 (PID: $NEW_PID)"
    log "PID 파일: $PID_FILE"
    log "로그 파일: $LOG"
}

case "$ACTION" in
    start|restart)
        stop_app
        git_pull
        prepare_venv
        load_conf
        start_app
        ;;
    stop)
        stop_app
        ;;
    status)
        if is_running; then log "실행 중 (PID: $(cat "$PID_FILE")), 로그: $LOG"
        else log "중지됨"; exit 3; fi
        ;;
esac
