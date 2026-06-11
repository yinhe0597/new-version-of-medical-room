#!/bin/bash
# ============================================================
# 医务室诊疗管理系统 - Linux 启动脚本
# 用法: ./run.sh [start|stop|restart|status|log]
# ============================================================

APP_NAME="medical_room"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
EXECUTABLE="$APP_DIR/$APP_NAME"
PID_FILE="$APP_DIR/.medical_room.pid"
LOG_DIR="$APP_DIR/logs"
DATA_DIR="$APP_DIR/data"

# 创建必要目录
mkdir -p "$LOG_DIR" "$DATA_DIR" "$DATA_DIR/backups"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    echo ""
    return 1
}

start_app() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo -e "${YELLOW}系统已在运行中 (PID: $pid)${NC}"
        return 0
    fi

    if [ ! -f "$EXECUTABLE" ]; then
        echo -e "${RED}错误: 找不到可执行文件 $EXECUTABLE${NC}"
        exit 1
    fi

    chmod +x "$EXECUTABLE"

    echo -e "${GREEN}正在启动医务室诊疗管理系统...${NC}"
    nohup "$EXECUTABLE" > "$LOG_DIR/console.log" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 2
    local new_pid=$(get_pid)
    if [ -n "$new_pid" ]; then
        local LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        echo ""
        echo "============================================================"
        echo "    医务室诊疗管理系统 已启动"
        echo "============================================================"
        echo -e "  本机访问:   ${GREEN}http://127.0.0.1:5000${NC}"
        echo -e "  局域网访问: ${GREEN}http://${LOCAL_IP:-<本机IP>}:5000${NC}"
        echo "  数据库位置: $DATA_DIR/app.db"
        echo "  日志目录:   $LOG_DIR"
        echo "  进程 PID:   $new_pid"
        echo "============================================================"
        echo "  提示: 使用 ./run.sh stop 停止系统"
        echo "        使用 ./run.sh log  查看实时日志"
        echo "============================================================"
        echo ""
    else
        echo -e "${RED}启动失败，请查看 $LOG_DIR/console.log${NC}"
        exit 1
    fi
}

stop_app() {
    local pid=$(get_pid)
    if [ -z "$pid" ]; then
        echo -e "${YELLOW}系统未在运行${NC}"
        return 0
    fi

    echo -e "${GREEN}正在停止医务室诊疗管理系统 (PID: $pid)...${NC}"
    kill "$pid" 2>/dev/null

    # 等待进程退出（最多10秒）
    for i in $(seq 1 10); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo -e "${GREEN}系统已停止${NC}"
            return 0
        fi
        sleep 1
    done

    # 强制终止
    echo -e "${YELLOW}正在强制终止...${NC}"
    kill -9 "$pid" 2>/dev/null
    rm -f "$PID_FILE"
    echo -e "${GREEN}系统已停止${NC}"
}

status_app() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo -e "${GREEN}系统正在运行 (PID: $pid)${NC}"
        echo "  访问地址: http://127.0.0.1:5000"
    else
        echo -e "${RED}系统未运行${NC}"
    fi
}

show_log() {
    local log_file="$LOG_DIR/app.log"
    if [ -f "$log_file" ]; then
        tail -f "$log_file"
    else
        echo -e "${YELLOW}日志文件不存在: $log_file${NC}"
        echo "请先启动系统"
    fi
}

# 主逻辑
case "${1:-start}" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        stop_app
        sleep 1
        start_app
        ;;
    status)
        status_app
        ;;
    log)
        show_log
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|log}"
        echo ""
        echo "  start   - 启动系统（默认，后台运行）"
        echo "  stop    - 停止系统"
        echo "  restart - 重启系统"
        echo "  status  - 查看运行状态"
        echo "  log     - 查看实时日志"
        exit 1
        ;;
esac
