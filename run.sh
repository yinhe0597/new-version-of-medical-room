#!/bin/bash

APP_NAME="medical_room"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
EXECUTABLE="$APP_DIR/$APP_NAME"
if [ -z "${APP_ROOT:-}" ]; then
    if [ -w "$APP_DIR" ]; then
        APP_ROOT="$APP_DIR"
    else
        XDG_BASE="${XDG_DATA_HOME:-${XDG_STATE_HOME:-${HOME:-/tmp}/.local/share}}"
        APP_ROOT="$XDG_BASE/medical-room"
    fi
fi

PID_FILE="$APP_ROOT/.medical_room.pid"
LOCK_FILE="$APP_ROOT/.medical_room.lock"
LOG_DIR="$APP_ROOT/logs"
DATA_DIR="$APP_ROOT/data"
READY_URL="${MEDICAL_ROOM_READY_URL:-http://127.0.0.1:5000/api/health/ready}"
DEFAULT_READY_URL="http://127.0.0.1:5000/api/health/ready"
STARTUP_TIMEOUT_SECONDS="${MEDICAL_ROOM_STARTUP_TIMEOUT:-60}"
LOCK_WAIT_SECONDS="${MEDICAL_ROOM_LOCK_TIMEOUT:-30}"

export APP_ROOT
if [ -z "${MEDICAL_ROOM_ENV_FILE:-}" ] && [ -f "$APP_DIR/.env" ]; then
    export MEDICAL_ROOM_ENV_FILE="$APP_DIR/.env"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

RECORD_PID=""
RECORD_START_TICKS=""
RECORD_TOKEN=""

ensure_control_dir() {
    if ! mkdir -p "$APP_ROOT"; then
        echo -e "${RED}错误: APP_ROOT 不可写: $APP_ROOT${NC}" >&2
        return 1
    fi
}

ensure_runtime_dirs() {
    if ! mkdir -p "$LOG_DIR" "$DATA_DIR" "$DATA_DIR/backups"; then
        echo -e "${RED}错误: 无法创建运行目录: $APP_ROOT${NC}" >&2
        return 1
    fi
}

generate_process_token() {
    local token=""
    if [ -r /dev/urandom ] && command -v od >/dev/null 2>&1; then
        token=$(od -An -N16 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')
    fi
    if [ -z "$token" ]; then
        token="$$-$(date +%s 2>/dev/null)-${RANDOM:-0}"
    fi
    printf '%s\n' "$token"
}

process_start_ticks() {
    local pid="$1"
    local stat_line rest
    [ -r "/proc/$pid/stat" ] || return 1
    IFS= read -r stat_line < "/proc/$pid/stat" || return 1
    rest="${stat_line##*) }"
    local fields=()
    read -r -a fields <<< "$rest"
    [ "${#fields[@]}" -ge 20 ] || return 1
    printf '%s\n' "${fields[19]}"
}

process_has_token() {
    local pid="$1"
    local token="$2"
    [ -r "/proc/$pid/environ" ] || return 1
    tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null |
        grep -Fqx "MEDICAL_ROOM_PROCESS_TOKEN=$token"
}

load_pid_record() {
    local extra=""
    RECORD_PID=""
    RECORD_START_TICKS=""
    RECORD_TOKEN=""
    [ -f "$PID_FILE" ] || return 1
    IFS='|' read -r RECORD_PID RECORD_START_TICKS RECORD_TOKEN extra < "$PID_FILE" || return 1
    case "$RECORD_PID" in
        ''|*[!0-9]*) return 1 ;;
    esac
    case "$RECORD_START_TICKS" in
        ''|*[!0-9]*) return 1 ;;
    esac
    case "$RECORD_TOKEN" in
        ''|*[!A-Za-z0-9._-]*) return 1 ;;
    esac
    [ -z "$extra" ] || return 1
    return 0
}

record_matches_process() {
    local current_start
    kill -0 "$RECORD_PID" 2>/dev/null || return 1
    current_start=$(process_start_ticks "$RECORD_PID") || return 1
    [ "$current_start" = "$RECORD_START_TICKS" ] || return 1
    process_has_token "$RECORD_PID" "$RECORD_TOKEN"
}

# Returns 0 for a verified managed process, 1 for no live process, and 2 when
# the PID file points at a live process whose identity cannot be verified.
managed_process_status() {
    local raw_pid=""
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    if ! load_pid_record; then
        IFS='|' read -r raw_pid _ < "$PID_FILE" 2>/dev/null || true
        case "$raw_pid" in
            ''|*[!0-9]*)
                rm -f "$PID_FILE"
                return 1
                ;;
        esac
        if kill -0 "$raw_pid" 2>/dev/null; then
            RECORD_PID="$raw_pid"
            return 2
        fi
        rm -f "$PID_FILE"
        return 1
    fi
    if ! kill -0 "$RECORD_PID" 2>/dev/null; then
        rm -f "$PID_FILE"
        return 1
    fi
    if record_matches_process; then
        return 0
    fi
    return 2
}

write_pid_record() {
    local pid="$1"
    local start_ticks="$2"
    local token="$3"
    local temp_file="${PID_FILE}.tmp.$$"
    umask 077
    if ! printf '%s|%s|%s\n' "$pid" "$start_ticks" "$token" > "$temp_file"; then
        rm -f "$temp_file"
        return 1
    fi
    if ! mv -f "$temp_file" "$PID_FILE"; then
        rm -f "$temp_file"
        return 1
    fi
}

# Returns 0 for HTTP 200, 1 for an occupied/reachable endpoint that is not
# ready (including HTTP 503), 2 only when no listener can be reached, and 3
# when the configured probe cannot be executed safely.
probe_readiness() {
    local status="" rc=0 output=""
    if command -v curl >/dev/null 2>&1; then
        status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
            --max-time 2 "$READY_URL" 2>/dev/null)
        rc=$?
        case "$status" in
            200) return 0 ;;
            [0-9][0-9][0-9]) [ "$status" != "000" ] && return 1 ;;
        esac
        case "$rc" in
            6) return 3 ;; # DNS/configuration failure
            7) return 2 ;; # connection refused/no listener
            *) return 1 ;; # timeout, TLS error, empty HTTP response: fail closed
        esac
    fi
    if command -v wget >/dev/null 2>&1; then
        output=$(wget --server-response --spider --timeout=2 --tries=1 \
            "$READY_URL" 2>&1)
        rc=$?
        status=$(printf '%s\n' "$output" | awk '/^[[:space:]]*HTTP\// {code=$2} END {print code}')
        case "$status" in
            200) return 0 ;;
            [0-9][0-9][0-9]) return 1 ;;
        esac
        if printf '%s\n' "$output" | grep -Eqi 'connection refused|failed: Connection refused'; then
            return 2
        fi
        [ "$rc" -eq 0 ] && return 1
        return 1
    fi
    if command -v timeout >/dev/null 2>&1; then
        [ "$READY_URL" = "$DEFAULT_READY_URL" ] || return 3
        timeout 2 bash -c '
            if ! exec 3<>/dev/tcp/127.0.0.1/5000; then exit 2; fi
            printf "GET /api/health/ready HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n" >&3
            if ! IFS= read -r status <&3; then exit 1; fi
            [[ "$status" == *" 200 "* ]] && exit 0
            exit 1
        ' >/dev/null 2>&1
        rc=$?
        [ "$rc" -eq 0 ] && return 0
        [ "$rc" -eq 2 ] && return 2
        return 1
    fi
    return 3
}

database_label() {
    local configured_uri="${DATABASE_URL:-${SQLALCHEMY_DATABASE_URI:-}}"
    if [ -n "$configured_uri" ] && [[ "${configured_uri,,}" != sqlite* ]]; then
        echo "外部数据库（环境变量配置）"
        return
    fi
    if [ -f "$APP_DIR/.env" ] && grep -Eiq \
        '^[[:space:]]*(DATABASE_URL|SQLALCHEMY_DATABASE_URI)[[:space:]]*=[[:space:]]*mysql' \
        "$APP_DIR/.env"; then
        echo "外部数据库（.env 配置）"
        return
    fi
    echo "$DATA_DIR/app.db"
}

report_verified_process() {
    local readiness_status
    probe_readiness
    readiness_status=$?
    case "$readiness_status" in
        0)
            echo -e "${GREEN}系统正在运行且已就绪 (PID: $RECORD_PID)${NC}"
            return 0
            ;;
        1)
            echo -e "${YELLOW}系统进程存活，但 readiness 尚未返回 200 (PID: $RECORD_PID)${NC}"
            return 1
            ;;
        2)
            echo -e "${YELLOW}系统进程存活，但 readiness 端口尚未监听 (PID: $RECORD_PID)${NC}"
            return 1
            ;;
        *)
            echo -e "${YELLOW}系统进程存活，但缺少可用的 readiness 探针工具 (PID: $RECORD_PID)${NC}"
            return 1
            ;;
    esac
}

terminate_recorded_process() {
    local pid="$RECORD_PID"
    local signal_name="${1:-TERM}"
    if ! record_matches_process; then
        echo -e "${RED}拒绝发送 $signal_name：PID $pid 的进程身份与 PID 文件不匹配${NC}" >&2
        return 1
    fi
    kill -s "$signal_name" "$pid" 2>/dev/null
}

stop_unready_process() {
    local pid="$RECORD_PID"
    terminate_recorded_process TERM || return 1
    local i
    for ((i = 0; i < 50; i++)); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            return 0
        fi
        if ! record_matches_process; then
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 0.1
    done
    if record_matches_process; then
        terminate_recorded_process KILL || return 1
    fi
    rm -f "$PID_FILE"
}

start_app() {
    local process_state
    managed_process_status
    process_state=$?
    if [ "$process_state" -eq 0 ]; then
        report_verified_process
        return $?
    fi
    if [ "$process_state" -eq 2 ]; then
        echo -e "${RED}拒绝启动：PID 文件指向存活但身份不匹配的进程 (PID: $RECORD_PID)${NC}" >&2
        return 1
    fi

    if [ ! -f "$EXECUTABLE" ]; then
        echo -e "${RED}错误: 找不到可执行文件 $EXECUTABLE${NC}" >&2
        return 1
    fi
    chmod +x "$EXECUTABLE" || return 1
    case "$STARTUP_TIMEOUT_SECONDS" in
        ''|*[!0-9]*|0)
            echo -e "${RED}错误: MEDICAL_ROOM_STARTUP_TIMEOUT 必须是正整数${NC}" >&2
            return 1
            ;;
    esac

    local existing_probe
    probe_readiness
    existing_probe=$?
    case "$existing_probe" in
        0|1)
            echo -e "${RED}拒绝启动：$READY_URL 已有进程占用或返回 HTTP 响应${NC}" >&2
            return 1
            ;;
        3)
            echo -e "${RED}拒绝启动：无法安全探测 $READY_URL${NC}" >&2
            return 1
            ;;
    esac

    ensure_runtime_dirs || return 1
    local token new_pid start_ticks="" i
    token=$(generate_process_token)
    echo -e "${GREEN}正在启动医务室管理系统...${NC}"
    nohup env MEDICAL_ROOM_PROCESS_TOKEN="$token" "$EXECUTABLE" \
        9>&- > "$LOG_DIR/console.log" 2>&1 &
    new_pid=$!

    for ((i = 0; i < 20; i++)); do
        if ! kill -0 "$new_pid" 2>/dev/null; then
            break
        fi
        start_ticks=$(process_start_ticks "$new_pid" 2>/dev/null || true)
        if [ -n "$start_ticks" ] && process_has_token "$new_pid" "$token"; then
            break
        fi
        start_ticks=""
        sleep 0.1
    done
    if [ -z "$start_ticks" ]; then
        kill "$new_pid" 2>/dev/null || true
        echo -e "${RED}启动失败：无法建立可靠的进程身份记录${NC}" >&2
        tail -n 30 "$LOG_DIR/console.log" 2>/dev/null || true
        return 1
    fi
    if ! write_pid_record "$new_pid" "$start_ticks" "$token"; then
        kill "$new_pid" 2>/dev/null || true
        echo -e "${RED}启动失败：无法写入 PID 文件${NC}" >&2
        return 1
    fi
    load_pid_record || return 1

    local elapsed=0 readiness_status
    while [ "$elapsed" -lt "$STARTUP_TIMEOUT_SECONDS" ]; do
        if ! record_matches_process; then
            if ! kill -0 "$new_pid" 2>/dev/null; then
                rm -f "$PID_FILE"
                echo -e "${RED}启动失败：新进程已退出，请检查 $LOG_DIR/console.log${NC}" >&2
            else
                echo -e "${RED}启动失败：新进程身份校验失败，未向该 PID 发送信号${NC}" >&2
            fi
            tail -n 30 "$LOG_DIR/console.log" 2>/dev/null || true
            return 1
        fi
        probe_readiness
        readiness_status=$?
        if [ "$readiness_status" -eq 0 ]; then
            local local_ip
            local_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
            echo ""
            echo "============================================================"
            echo "    医务室管理系统已启动"
            echo "============================================================"
            echo -e "  本机访问:   ${GREEN}http://127.0.0.1:5000${NC}"
            echo -e "  局域网访问: ${GREEN}http://${local_ip:-<本机IP>}:5000${NC}"
            echo "  数据库位置: $(database_label)"
            echo "  日志目录:   $LOG_DIR"
            echo "  进程 PID:   $new_pid"
            echo "============================================================"
            return 0
        fi
        if [ "$readiness_status" -eq 3 ]; then
            echo -e "${RED}启动检查失败：缺少可用的 readiness 探针工具${NC}" >&2
            stop_unready_process
            return 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    echo -e "${RED}启动超时：${STARTUP_TIMEOUT_SECONDS} 秒内未通过 $READY_URL${NC}" >&2
    stop_unready_process
    tail -n 30 "$LOG_DIR/console.log" 2>/dev/null || true
    return 1
}

stop_app() {
    local process_state pid i
    managed_process_status
    process_state=$?
    if [ "$process_state" -eq 1 ]; then
        echo -e "${YELLOW}系统未在运行${NC}"
        return 0
    fi
    if [ "$process_state" -eq 2 ]; then
        echo -e "${RED}拒绝停止：PID 文件无法证明 PID $RECORD_PID 属于本系统${NC}" >&2
        return 1
    fi
    pid="$RECORD_PID"
    echo -e "${GREEN}正在停止医务室管理系统 (PID: $pid)...${NC}"
    terminate_recorded_process TERM || return 1
    for ((i = 0; i < 100; i++)); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo -e "${GREEN}系统已停止${NC}"
            return 0
        fi
        if ! record_matches_process; then
            rm -f "$PID_FILE"
            echo -e "${GREEN}原系统进程已退出；未向复用该 PID 的进程发送信号${NC}"
            return 0
        fi
        sleep 0.1
    done
    echo -e "${YELLOW}进程未按时退出，准备强制停止...${NC}"
    if record_matches_process; then
        terminate_recorded_process KILL || return 1
    else
        echo -e "${RED}进程身份已变化，拒绝发送 KILL${NC}" >&2
        return 1
    fi
    rm -f "$PID_FILE"
    echo -e "${GREEN}系统已停止${NC}"
}

status_app() {
    local process_state endpoint_state
    managed_process_status
    process_state=$?
    if [ "$process_state" -eq 0 ]; then
        report_verified_process
        return $?
    fi
    if [ "$process_state" -eq 2 ]; then
        echo -e "${RED}PID 文件存在，但无法验证 PID $RECORD_PID 的进程身份${NC}" >&2
        return 2
    fi
    probe_readiness
    endpoint_state=$?
    if [ "$endpoint_state" -eq 0 ] || [ "$endpoint_state" -eq 1 ]; then
        echo -e "${RED}没有受管进程，但 $READY_URL 已被其他进程占用${NC}" >&2
        return 2
    fi
    echo -e "${RED}系统未运行${NC}"
    return 3
}

restart_app() {
    stop_app || return 1
    sleep 1
    start_app
}

show_log() {
    local log_file="$LOG_DIR/app.log"
    if [ -f "$log_file" ]; then
        tail -f "$log_file"
    else
        echo -e "${YELLOW}日志文件尚不存在: $log_file${NC}"
    fi
}

exit_locked_on_signal() {
    local exit_code="$1"
    trap - HUP INT TERM
    flock -u 9 2>/dev/null || true
    exec 9>&-
    exit "$exit_code"
}

run_locked() {
    ensure_control_dir || return 1
    case "$LOCK_WAIT_SECONDS" in
        ''|*[!0-9]*|0)
            echo -e "${RED}错误: MEDICAL_ROOM_LOCK_TIMEOUT 必须是正整数${NC}" >&2
            return 1
            ;;
    esac
    if ! command -v flock >/dev/null 2>&1; then
        echo -e "${RED}操作失败：缺少 flock，无法安全管理系统进程${NC}" >&2
        return 1
    fi
    exec 9> "$LOCK_FILE" || return 1
    if ! flock -w "$LOCK_WAIT_SECONDS" 9; then
        echo -e "${RED}操作失败：等待进程管理锁超时${NC}" >&2
        exec 9>&-
        return 1
    fi
    trap 'exit_locked_on_signal 129' HUP
    trap 'exit_locked_on_signal 130' INT
    trap 'exit_locked_on_signal 143' TERM
    "$@"
    local result=$?
    trap - HUP INT TERM
    flock -u 9 2>/dev/null || true
    exec 9>&-
    return "$result"
}

case "${1:-start}" in
    start) run_locked start_app ;;
    stop) run_locked stop_app ;;
    restart) run_locked restart_app ;;
    status) run_locked status_app ;;
    log) show_log ;;
    *)
        echo "用法: $0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac
