#!/bin/bash
# ============================================================
#  MTProxy Panel v2.1 - Professional Edition
#  by @ali_sudo_of
#  Auto-rebuild | Multi-client | Web UI | AD Tag
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="/opt/mtproxy"
PANEL_DIR="/opt/mtproxy-panel"
SERVICE_NAME="mtproxy"
WEB_SERVICE="mtproxy-web"
BINARY="$INSTALL_DIR/mtproto-proxy"

# Non-interactive if already installed or AUTO=1
AUTO_MODE=0
[[ "$1" == "--auto" || "$1" == "-y" ]] && AUTO_MODE=1

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR] Run as root${NC}"
    exit 1
fi

print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           MTProxy Panel v2.1 - Professional              ║"
    echo "║                     by @ali_sudo_of                      ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

get_public_ip() {
    curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
    curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo ""
}

is_installed() {
    [[ -f "$BINARY" ]] && [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]
}

install_deps() {
    echo -e "${BLUE}[+] Installing dependencies...${NC}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git curl build-essential libssl-dev zlib1g-dev \
        openssl ca-certificates python3 python3-pip python3-venv > /dev/null 2>&1 || true
    if ! command -v xxd >/dev/null 2>&1; then
        apt-get install -y -qq xxd >/dev/null 2>&1 || apt-get install -y -qq vim-common >/dev/null 2>&1 || true
    fi
    echo -e "${GREEN}[✓] Dependencies ready${NC}"
}

build_mtproxy() {
    echo -e "${BLUE}[+] Building MTProxy...${NC}"
    rm -rf /tmp/MTProxy 2>/dev/null || true
    git clone --depth 1 https://github.com/TelegramMessenger/MTProxy.git /tmp/MTProxy
    cd /tmp/MTProxy
    if [[ -f Makefile ]] && ! grep -q "fcommon" Makefile; then
        sed -i 's/CFLAGS=/CFLAGS=-fcommon /' Makefile || true
        sed -i 's/LDFLAGS=/LDFLAGS=-fcommon /' Makefile || true
    fi
    if ! make -j"$(nproc)" > /tmp/mtproxy_build.log 2>&1; then
        echo -e "${YELLOW}[!] Trying community fork...${NC}"
        rm -rf /tmp/MTProxy
        git clone --depth 1 https://github.com/GetPageSpeed/MTProxy.git /tmp/MTProxy
        cd /tmp/MTProxy
        make -j"$(nproc)" > /tmp/mtproxy_build.log 2>&1 || {
            echo -e "${RED}Build failed${NC}"
            tail -20 /tmp/mtproxy_build.log
            exit 1
        }
    fi
    mkdir -p "$INSTALL_DIR"
    cp -f objs/bin/mtproto-proxy "$BINARY"
    chmod 755 "$BINARY"
    echo -e "${GREEN}[✓] Binary ready${NC}"
}

download_configs() {
    echo -e "${BLUE}[+] Downloading configs...${NC}"
    mkdir -p "$INSTALL_DIR"
    curl -s --max-time 15 https://core.telegram.org/getProxySecret -o "$INSTALL_DIR/proxy-secret"
    curl -s --max-time 15 https://core.telegram.org/getProxyConfig -o "$INSTALL_DIR/proxy-multi.conf"
    echo -e "${GREEN}[✓] Configs ready${NC}"
}

install_web() {
    echo -e "${BLUE}[+] Installing Web Panel...${NC}"
    mkdir -p "$PANEL_DIR"
    curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/web/app.py -o "$PANEL_DIR/app.py"

    python3 -m venv "$PANEL_DIR/venv" 2>/dev/null || true
    "$PANEL_DIR/venv/bin/pip" install --quiet --upgrade pip flask 2>/dev/null || pip3 install --quiet flask

    cat > /etc/systemd/system/${WEB_SERVICE}.service <<EOF
[Unit]
Description=MTProxy Web Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=$PANEL_DIR
ExecStart=$PANEL_DIR/venv/bin/python3 $PANEL_DIR/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    [[ ! -f "$INSTALL_DIR/panel_pass.txt" ]] && echo "admin" > "$INSTALL_DIR/panel_pass.txt"
    chmod 600 "$INSTALL_DIR/panel_pass.txt" 2>/dev/null || true

    systemctl daemon-reload
    systemctl enable ${WEB_SERVICE} >/dev/null 2>&1 || true
    systemctl restart ${WEB_SERVICE} 2>/dev/null || systemctl start ${WEB_SERVICE}
    echo -e "${GREEN}[✓] Web Panel on :8880${NC}"
}

do_full_install() {
    local PORT=${1:-443}
    local ADTAG=${2:-""}

    print_banner
    echo -e "${YELLOW}=== Installing / Updating MTProxy + Web Panel ===${NC}\n"

    # Stop old if exists
    systemctl stop ${SERVICE_NAME} 2>/dev/null || true

    install_deps
    build_mtproxy
    download_configs

    # Keep existing secret/clients if present, otherwise create new
    if [[ ! -f "$INSTALL_DIR/clients.json" && ! -f "$INSTALL_DIR/secret.txt" ]]; then
        local SECRET=$(head -c 16 /dev/urandom | xxd -ps)
        echo "$SECRET" > "$INSTALL_DIR/secret.txt"
        cat > "$INSTALL_DIR/clients.json" <<EOC
[
  {
    "id": "main",
    "name": "Main Client",
    "secret": "$SECRET",
    "enabled": true,
    "created": "$(date -Iseconds)"
  }
]
EOC
    fi

    echo "$PORT" > "$INSTALL_DIR/port.txt"
    [[ -n "$ADTAG" ]] && echo "$ADTAG" > "$INSTALL_DIR/adtag.txt" || true

    # Build service with current clients
    local SECRETS=""
    if [[ -f "$INSTALL_DIR/clients.json" ]]; then
        SECRETS=$(python3 -c "
import json
try:
    clients = json.load(open('$INSTALL_DIR/clients.json'))
    print(' '.join(['-S '+c['secret'] for c in clients if c.get('enabled',True)]))
except: pass
" 2>/dev/null || true)
    fi
    if [[ -z "$SECRETS" && -f "$INSTALL_DIR/secret.txt" ]]; then
        SECRETS="-S $(cat $INSTALL_DIR/secret.txt)"
    fi

    local ADTAG_ARG=""
    [[ -f "$INSTALL_DIR/adtag.txt" && -s "$INSTALL_DIR/adtag.txt" ]] && ADTAG_ARG=" -P $(cat $INSTALL_DIR/adtag.txt)"

    cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$BINARY -u nobody -p 8888 -H $PORT $SECRETS$ADTAG_ARG --aes-pwd $INSTALL_DIR/proxy-secret $INSTALL_DIR/proxy-multi.conf -M 1
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME} >/dev/null 2>&1 || true

    # Firewall
    if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
        ufw allow ${PORT}/tcp >/dev/null 2>&1 || true
        ufw allow 8880/tcp >/dev/null 2>&1 || true
    fi

    install_web

    systemctl start ${SERVICE_NAME}
    sleep 2

    local IP=$(get_public_ip)
    local SECRET=$(python3 -c "
import json,sys
try:
    c=json.load(open('$INSTALL_DIR/clients.json'))[0]['secret']
    print(c)
except:
    print(open('$INSTALL_DIR/secret.txt').read().strip() if __import__('os').path.exists('$INSTALL_DIR/secret.txt') else '')
" 2>/dev/null)

    echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                 Installation Complete                    ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}\n"
    echo -e "${CYAN}Web Panel:${NC}   http://${IP}:8880"
    echo -e "${CYAN}Password:${NC}    admin"
    echo -e "${CYAN}Port:${NC}        $PORT"
    echo ""
    echo -e "${YELLOW}Connection links:${NC}"
    echo "tg://proxy?server=${IP}&port=${PORT}&secret=dd${SECRET}"
    echo "tg://proxy?server=${IP}&port=${PORT}&secret=ee${SECRET}"
    echo ""
}

# ========== Main ==========
print_banner

if is_installed; then
    echo -e "${YELLOW}[!] MTProxy already installed → Auto rebuilding / updating...${NC}\n"
    # Keep current port
    CURRENT_PORT=$(cat "$INSTALL_DIR/port.txt" 2>/dev/null || echo "443")
    CURRENT_ADTAG=$(cat "$INSTALL_DIR/adtag.txt" 2>/dev/null || echo "")
    do_full_install "$CURRENT_PORT" "$CURRENT_ADTAG"
else
    # Fresh install
    if [[ $AUTO_MODE -eq 1 ]]; then
        do_full_install 443 ""
    else
        read -p "Port [443]: " input_port
        PORT=${input_port:-443}
        read -p "AD Tag (optional): " ADTAG
        do_full_install "$PORT" "$ADTAG"
    fi
fi
