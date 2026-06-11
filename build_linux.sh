#!/bin/bash
# ============================================================
# 医务室诊疗管理系统 - Linux 一键构建脚本
# 输出两种格式:
#   1. tar.gz  - 自包含压缩包 + run.sh 启动脚本（适用于任意 Linux）
#   2. AppImage - 单文件可执行（双击即运行，无需安装）
#
# 前置条件:
#   - Python 3.8+
#   - Node.js 16+ (用于前端构建)
#   - pip / npm
#
# 用法: bash build_linux.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="0.0.16"
APP_NAME="medical_room"
DIST_NAME="医务室管理系统-v${VERSION}-linux"
BUILD_DIR="$SCRIPT_DIR/build_linux"
OUTPUT_DIR="$SCRIPT_DIR/dist_linux"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${CYAN}[STEP]${NC} $1"; }

# 清理旧构建
cleanup() {
    log_step "清理旧构建产物..."
    rm -rf "$BUILD_DIR" "$OUTPUT_DIR"
    mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"
}

# 检查前置依赖
check_deps() {
    log_step "检查构建依赖..."

    # Python
    if ! command -v python3 &>/dev/null; then
        log_error "未找到 python3，请先安装 Python 3.8+"
        exit 1
    fi
    log_info "Python: $(python3 --version)"

    # Node.js
    if ! command -v node &>/dev/null; then
        log_error "未找到 node，请先安装 Node.js 16+"
        exit 1
    fi
    log_info "Node.js: $(node --version)"

    # npm
    if ! command -v npm &>/dev/null; then
        log_error "未找到 npm"
        exit 1
    fi

    # pip
    if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null; then
        log_error "未找到 pip，请先安装 pip"
        exit 1
    fi
}

# 安装 Python 依赖
install_python_deps() {
    log_step "安装 Python 依赖..."
    python3 -m pip install --quiet -r backend/requirements.txt
    python3 -m pip install --quiet pyinstaller
    log_info "Python 依赖安装完成"
}

# 构建前端
build_frontend() {
    log_step "构建前端..."
    cd frontend
    npm install --silent 2>/dev/null || npm install
    npm run build
    cd "$SCRIPT_DIR"
    log_info "前端构建完成"
}

# PyInstaller 打包
build_executable() {
    log_step "使用 PyInstaller 打包（Linux 单文件模式）..."
    python3 -m PyInstaller \
        --clean \
        --noconfirm \
        medical_room_linux.spec

    if [ ! -f "dist/$APP_NAME" ]; then
        log_error "PyInstaller 打包失败，未找到 dist/$APP_NAME"
        exit 1
    fi

    log_info "可执行文件生成: dist/$APP_NAME ($(du -h dist/$APP_NAME | cut -f1))"
}

# ============================================================
# 格式 1: tar.gz 自包含压缩包
# ============================================================
package_tarball() {
    log_step "打包 tar.gz 格式..."

    local STAGING="$BUILD_DIR/${DIST_NAME}"
    mkdir -p "$STAGING"

    # 复制可执行文件
    cp "dist/$APP_NAME" "$STAGING/"
    chmod +x "$STAGING/$APP_NAME"

    # 复制启动脚本
    cp run.sh "$STAGING/"
    chmod +x "$STAGING/run.sh"

    # 创建使用说明
    cat > "$STAGING/README.txt" << 'EOF'
============================================================
  医务室诊疗管理系统 - Linux 版
============================================================

【快速启动】
  chmod +x run.sh
  ./run.sh start

【命令说明】
  ./run.sh start   - 启动系统（后台运行）
  ./run.sh stop    - 停止系统
  ./run.sh restart - 重启系统
  ./run.sh status  - 查看运行状态
  ./run.sh log     - 查看实时日志

【直接运行（前台模式，可看控制台输出）】
  ./medical_room

【访问地址】
  本机:     http://127.0.0.1:5000
  局域网:   http://<本机IP>:5000

【默认账号】
  管理员: admin / 123456
  医生:   doctor / 123456
  护士:   nurse / 123456

【数据目录】
  数据库和日志自动创建在本程序同级目录:
  - data/        数据库文件
  - logs/        运行日志
  - data/backups/ 自动备份

【系统要求】
  - Linux x86_64 (glibc 2.17+)
  - 无需安装 Python 或其他依赖
============================================================
EOF

    # 打包
    local TAR_FILE="$OUTPUT_DIR/${DIST_NAME}.tar.gz"
    tar -czf "$TAR_FILE" -C "$BUILD_DIR" "${DIST_NAME}"
    log_info "tar.gz 打包完成: $TAR_FILE ($(du -h "$TAR_FILE" | cut -f1))"
}

# ============================================================
# 格式 2: AppImage 单文件可执行
# ============================================================
package_appimage() {
    log_step "打包 AppImage 格式..."

    # 检查 appimagetool
    local APPIMAGETOOL="$BUILD_DIR/appimagetool-x86_64.AppImage"
    if [ ! -f "$APPIMAGETOOL" ]; then
        log_info "下载 appimagetool..."
        wget -q -O "$APPIMAGETOOL" \
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
            2>/dev/null || {
            log_warn "appimagetool 下载失败，尝试备用地址..."
            curl -sL -o "$APPIMAGETOOL" \
                "https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage" \
                2>/dev/null || {
                log_warn "AppImage 工具下载失败，跳过 AppImage 打包"
                log_warn "可手动下载 appimagetool 后重新运行本脚本"
                return 0
            }
        }
        chmod +x "$APPIMAGETOOL"
    fi

    # 构建 AppDir 结构
    local APPDIR="$BUILD_DIR/${APP_NAME}.AppDir"
    mkdir -p "$APPDIR/usr/bin"

    # 复制可执行文件
    cp "dist/$APP_NAME" "$APPDIR/usr/bin/"
    chmod +x "$APPDIR/usr/bin/$APP_NAME"

    # 创建 AppRun（AppImage 入口）
    cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
export APP_ROOT="$SELF_DIR"
mkdir -p "$SELF_DIR/data/backups" "$SELF_DIR/logs"
exec "$SELF_DIR/usr/bin/medical_room" "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"

    # 创建 .desktop 文件
    cat > "$APPDIR/${APP_NAME}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=医务室管理系统
Name[en]=Medical Room Manager
Comment=医务室诊疗管理系统
Exec=medical_room
Icon=medical_room
Terminal=true
Categories=Office;Medical;
StartupNotify=false
EOF

    # 创建简单图标（如果项目没有图标，用文字占位）
    if [ -f "docs/images/logo.png" ]; then
        cp "docs/images/logo.png" "$APPDIR/medical_room.png"
    else
        # 创建一个最小的 1x1 PNG 占位
        echo -n "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" \
            | base64 -d > "$APPDIR/medical_room.png"
    fi

    # 生成 AppImage
    local APPIMAGE_FILE="$OUTPUT_DIR/${DIST_NAME}.AppImage"
    ARCH=x86_64 "$APPIMAGETOOL" --no-appindicator "$APPDIR" "$APPIMAGE_FILE" 2>/dev/null || {
        log_warn "AppImage 生成失败（可能缺少 FUSE），尝试解压模式..."
        # 在无 FUSE 环境（如 Docker）中，解压 appimagetool 再运行
        cd "$BUILD_DIR"
        chmod +x appimagetool-x86_64.AppImage
        ./appimagetool-x86_64.AppImage --appimage-extract 2>/dev/null
        if [ -d "squashfs-root" ]; then
            ARCH=x86_64 ./squashfs-root/AppRun --no-appindicator "$APPDIR" "$APPIMAGE_FILE" 2>/dev/null || true
        fi
        cd "$SCRIPT_DIR"
    }

    if [ -f "$APPIMAGE_FILE" ]; then
        chmod +x "$APPIMAGE_FILE"
        log_info "AppImage 打包完成: $APPIMAGE_FILE ($(du -h "$APPIMAGE_FILE" | cut -f1))"
    else
        log_warn "AppImage 生成失败，仅保留 tar.gz 格式"
    fi
}

# 输出汇总
print_summary() {
    echo ""
    echo "============================================================"
    echo -e "${GREEN}  构建完成！${NC}"
    echo "============================================================"
    echo ""
    echo "  输出目录: $OUTPUT_DIR/"
    echo ""

    if [ -f "$OUTPUT_DIR/${DIST_NAME}.tar.gz" ]; then
        echo -e "  ${CYAN}[格式1] tar.gz 压缩包${NC}"
        echo "    文件: ${DIST_NAME}.tar.gz"
        echo "    大小: $(du -h "$OUTPUT_DIR/${DIST_NAME}.tar.gz" | cut -f1)"
        echo "    用法: tar xzf ${DIST_NAME}.tar.gz && cd ${DIST_NAME} && ./run.sh start"
        echo "    场景: 服务器部署、远程机器、systemd 管理"
        echo ""
    fi

    if [ -f "$OUTPUT_DIR/${DIST_NAME}.AppImage" ]; then
        echo -e "  ${CYAN}[格式2] AppImage 单文件${NC}"
        echo "    文件: ${DIST_NAME}.AppImage"
        echo "    大小: $(du -h "$OUTPUT_DIR/${DIST_NAME}.AppImage" | cut -f1)"
        echo "    用法: chmod +x ${DIST_NAME}.AppImage && ./${DIST_NAME}.AppImage"
        echo "    场景: 桌面 Linux、U盘携带、双击运行"
        echo ""
    fi

    echo "============================================================"
}

# ============================================================
# 主流程
# ============================================================
echo ""
echo "============================================================"
echo "  医务室诊疗管理系统 - Linux 构建脚本"
echo "  版本: v${VERSION}"
echo "============================================================"
echo ""

cleanup
check_deps
install_python_deps
build_frontend
build_executable
package_tarball
package_appimage
print_summary
