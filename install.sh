#!/bin/bash
# ============================================================
#  MTProxy Panel - Complete Telegram MTProxy Installer & Manager
#  For Ubuntu 20.04 / 22.04 / 24.04
#  by @ali_sudo_of
#  Features: CLI Menu + Web UI + AD Tag (Sponsor Channel)
#  Version: 2.0
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

INSTALL_DIR="/opt/mtproxy"
SERVICE_NAME="mtproxy"
WEB_SERVICE="mtproxy-web"
BINARY="$INSTALL_DIR/mtproto-proxy"
SECRET_FILE="$INSTALL_DIR/secret.txt"
PORT_FILE="$INSTALL_DIR/port.txt"
ADTAG_FILE="$INSTALL_DIR/adtag.txt"
PANEL_DIR="/opt/mtproxy-panel"

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR] Please run as root: sudo bash $0${NC}"
    exit 1
fi

print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           MTProxy Panel - Telegram Proxy Manager         ║"
    echo "║              Ubuntu 20.04 / 22.04 / 24.04                ║"
    echo "║                     by @ali_sudo_of                      ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

get_public_ip() {
    curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
    curl -s --max-time 5 https://ifconfig.me 2>/dev/null || \
    curl -s --max-time 5 https://icanhazip.com 2>/dev/null || echo ""
}

check_installed() {
    [[ -f "$BINARY" ]] && [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]
}

install_deps() {
    echo -e "${BLUE}[+] Installing dependencies...${NC}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git curl build-essential libssl-dev zlib1g-dev \
        openssl ca-certificates libcap2-bin python3 python3-pip python3-venv > /dev/null 2>&1 || true
    if ! command -v xxd >/dev/null 2>&1; then
        apt-get install -y -qq xxd > /dev/null 2>&1 || apt-get install -y -qq vim-common > /dev/null 2>&1 || true
    fi
    echo -e "${GREEN}[✓] Dependencies installed${NC}"
}

build_mtproxy() {
    echo -e "${BLUE}[+] Building MTProxy from source...${NC}"
    rm -rf /tmp/MTProxy 2>/dev/null || true
    git clone --depth 1 https://github.com/TelegramMessenger/MTProxy.git /tmp/MTProxy
    cd /tmp/MTProxy
    if [[ -f Makefile ]] && ! grep -q "fcommon" Makefile; then
        sed -i 's/CFLAGS=/CFLAGS=-fcommon /' Makefile || true
        sed -i 's/LDFLAGS=/LDFLAGS=-fcommon /' Makefile || true
    fi
    if ! make -j"$(nproc)" > /tmp/mtproxy_build.log 2>&1; then
        echo -e "${YELLOW}[!] Official build failed, trying community fork...${NC}"
        rm -rf /tmp/MTProxy
        git clone --depth 1 https://github.com/GetPageSpeed/MTProxy.git /tmp/MTProxy
        cd /tmp/MTProxy
        if ! make -j"$(nproc)" > /tmp/mtproxy_build.log 2>&1; then
            echo -e "${RED}[ERROR] Build failed. Check /tmp/mtproxy_build.log${NC}"
            cat /tmp/mtproxy_build.log | tail -30
            exit 1
        fi
    fi
    mkdir -p "$INSTALL_DIR"
    cp -f objs/bin/mtproto-proxy "$BINARY"
    chmod 755 "$BINARY"
    if ! id mtproxy &>/dev/null; then
        useradd --system --no-create-home --shell /usr/sbin/nologin --home-dir "$INSTALL_DIR" mtproxy 2>/dev/null || \
        useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" mtproxy || true
    fi
    chown -R mtproxy:mtproxy "$INSTALL_DIR" 2>/dev/null || true
    echo -e "${GREEN}[✓] MTProxy built successfully${NC}"
}

download_configs() {
    echo -e "${BLUE}[+] Downloading Telegram proxy configs...${NC}"
    mkdir -p "$INSTALL_DIR"
    curl -s --max-time 15 https://core.telegram.org/getProxySecret -o "$INSTALL_DIR/proxy-secret" || { echo -e "${RED}Failed to download proxy-secret${NC}"; exit 1; }
    curl -s --max-time 15 https://core.telegram.org/getProxyConfig -o "$INSTALL_DIR/proxy-multi.conf" || { echo -e "${RED}Failed to download proxy-multi.conf${NC}"; exit 1; }
    chown mtproxy:mtproxy "$INSTALL_DIR/proxy-secret" "$INSTALL_DIR/proxy-multi.conf" 2>/dev/null || true
    echo -e "${GREEN}[✓] Configs downloaded${NC}"
}

generate_secret() {
    local secret=$(head -c 16 /dev/urandom | xxd -ps)
    echo "$secret" > "$SECRET_FILE"
    chown mtproxy:mtproxy "$SECRET_FILE" 2>/dev/null || true
    chmod 600 "$SECRET_FILE"
    echo "$secret"
}

create_systemd() {
    local port=$1
    local secret=$2
    local adtag=$3

    local adtag_arg=""
    [[ -n "$adtag" ]] && adtag_arg=" -P $adtag"

    # Always run as root for port 443 reliability
    cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$BINARY -u nobody -p 8888 -H $port -S $secret$adtag_arg --aes-pwd $INSTALL_DIR/proxy-secret $INSTALL_DIR/proxy-multi.conf -M 1
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
    echo -e "${GREEN}[✓] Systemd service created${NC}"
}

setup_firewall() {
    local port=$1
    if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
        ufw allow "${port}/tcp" >/dev/null 2>&1 || true
        ufw allow 8880/tcp >/dev/null 2>&1 || true
        echo -e "${GREEN}[✓] UFW ports opened${NC}"
    fi
    iptables -I INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || true
    iptables -I INPUT -p tcp --dport 8880 -j ACCEPT 2>/dev/null || true
}

install_web_panel() {
    echo -e "${BLUE}[+] Installing Web Panel...${NC}"
    mkdir -p "$PANEL_DIR"
    # Download the web app from the same repo
    curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/web/app.py -o "$PANEL_DIR/app.py"
    curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/web/requirements.txt -o "$PANEL_DIR/requirements.txt" 2>/dev/null || true

    python3 -m venv "$PANEL_DIR/venv" 2>/dev/null || true
    "$PANEL_DIR/venv/bin/pip" install --quiet flask 2>/dev/null || pip3 install --quiet flask

    # Create systemd for web panel
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

    # Default panel password
    echo "admin" > "$INSTALL_DIR/panel_pass.txt"
    chmod 600 "$INSTALL_DIR/panel_pass.txt"

    systemctl daemon-reload
    systemctl enable ${WEB_SERVICE} >/dev/null 2>&1 || true
    systemctl restart ${WEB_SERVICE} 2>/dev/null || systemctl start ${WEB_SERVICE}
    echo -e "${GREEN}[✓] Web Panel installed on port 8880${NC}"
}

do_install() {
    print_banner
    echo -e "${YELLOW}=== Installing MTProxy + Web Panel ===${NC}\n"

    if check_installed; then
        echo -e "${YELLOW}[!] Already installed.${NC}"
        read -p "Reinstall? (y/N): " confirm
        [[ ! "$confirm" =~ ^[Yy]$ ]] && return
        systemctl stop ${SERVICE_NAME} 2>/dev/null || true
    fi

    local default_port=443
    read -p "Enter listen port [default: $default_port]: " input_port
    local PORT=${input_port:-$default_port}

    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        echo -e "${RED}Invalid port${NC}"
        return
    fi

    read -p "AD Tag / Sponsor Channel (optional, from @MTProxybot): " ADTAG

    mkdir -p "$INSTALL_DIR"
    install_deps
    build_mtproxy
    download_configs

    echo "$PORT" > "$PORT_FILE"
    [[ -n "$ADTAG" ]] && echo "$ADTAG" > "$ADTAG_FILE" || true

    local SECRET=$(generate_secret)
    create_systemd "$PORT" "$SECRET" "$ADTAG"
    setup_firewall "$PORT"
    install_web_panel

    systemctl start ${SERVICE_NAME}
    sleep 2

    if systemctl is-active --quiet ${SERVICE_NAME}; then
        local IP=$(get_public_ip)
        echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              MTProxy + Web Panel installed!              ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}\n"
        echo -e "${CYAN}Web Panel:${NC}  http://${IP}:8880"
        echo -e "${CYAN}Password:${NC}   admin"
        echo ""
        echo -e "${YELLOW}1) Simple (dd):${NC}"
        echo -e "tg://proxy?server=${IP}&port=${PORT}&secret=dd${SECRET}"
        echo ""
        echo -e "${YELLOW}2) Fake TLS (ee):${NC}"
        echo -e "tg://proxy?server=${IP}&port=${PORT}&secret=ee${SECRET}"
        echo ""
    else
        echo -e "${RED}[ERROR] Service failed to start${NC}"
        journalctl -u ${SERVICE_NAME} -n 15 --no-pager || true
    fi
}

do_uninstall() {
    print_banner
    read -p "Are you sure? This removes everything (y/N): " confirm
    [[ ! "$confirm" =~ ^[Yy]$ ]] && return

    systemctl stop ${SERVICE_NAME} ${WEB_SERVICE} 2>/dev/null || true
    systemctl disable ${SERVICE_NAME} ${WEB_SERVICE} 2>/dev/null || true
    rm -f /etc/systemd/system/${SERVICE_NAME}.service /etc/systemd/system/${WEB_SERVICE}.service
    systemctl daemon-reload 2>/dev/null || true
    rm -rf "$INSTALL_DIR" "$PANEL_DIR"
    userdel mtproxy 2>/dev/null || true
    echo -e "${GREEN}[✓] Completely removed${NC}"
}

show_links() {
    print_banner
    if ! check_installed; then
        echo -e "${RED}Not installed${NC}"
        return
    fi
    local IP=$(get_public_ip)
    local PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "443")
    local SECRET=$(cat "$SECRET_FILE" 2>/dev/null)
    local ADTAG=$(cat "$ADTAG_FILE" 2>/dev/null || echo "")

    echo -e "${CYAN}Server IP:${NC} $IP"
    echo -e "${CYAN}Port:${NC}     $PORT"
    echo -e "${CYAN}Secret:${NC}   $SECRET"
    [[ -n "$ADTAG" ]] && echo -e "${CYAN}AD Tag:${NC}   $ADTAG"
    echo ""
    echo -e "${YELLOW}1) Simple (dd):${NC}"
    echo "tg://proxy?server=${IP}&port=${PORT}&secret=dd${SECRET}"
    echo ""
    echo -e "${YELLOW}2) Fake TLS (ee):${NC}"
    echo "tg://proxy?server=${IP}&port=${PORT}&secret=ee${SECRET}"
    echo ""
    echo -e "${CYAN}Web Panel:${NC} http://${IP}:8880  (password: admin)"
}

main_menu() {
    while true; do
        print_banner
        if check_installed; then
            local status=$(systemctl is-active ${SERVICE_NAME} 2>/dev/null || echo "inactive")
            if [[ "$status" == "active" ]]; then
                echo -e "Status: ${GREEN}● Running${NC} | Port: $(cat $PORT_FILE 2>/dev/null || echo '?')"
            else
                echo -e "Status: ${RED}● Stopped${NC}"
            fi
            local web_status=$(systemctl is-active ${WEB_SERVICE} 2>/dev/null || echo "inactive")
            echo -e "Web Panel: $web_status (port 8880)"
        else
            echo -e "Status: ${YELLOW}Not installed${NC}"
        fi
        echo ""
        echo -e "${BOLD}========== MENU ==========${NC}"
        echo -e "  ${GREEN}1)${NC} Install / Reinstall (CLI + Web Panel)"
        echo -e "  ${GREEN}2)${NC} Uninstall"
        echo -e "  ${GREEN}3)${NC} Start"
        echo -e "  ${GREEN}4)${NC} Stop"
        echo -e "  ${GREEN}5)${NC} Restart"
        echo -e "  ${GREEN}6)${NC} Status"
        echo -e "  ${GREEN}7)${NC} Show Links + Web Panel URL"
        echo -e "  ${GREEN}8)${NC} Update Telegram Configs"
        echo -e "  ${GREEN}0)${NC} Exit"
        echo -e "${BOLD}==========================${NC}"
        echo ""
        read -p "Select: " choice
        case $choice in
            1) do_install; read -p "Press Enter..." ;;
            2) do_uninstall; read -p "Press Enter..." ;;
            3) systemctl start ${SERVICE_NAME}; echo -e "${GREEN}Started${NC}"; read -p "Press Enter..." ;;
            4) systemctl stop ${SERVICE_NAME}; echo -e "${GREEN}Stopped${NC}"; read -p "Press Enter..." ;;
            5) systemctl restart ${SERVICE_NAME}; echo -e "${GREEN}Restarted${NC}"; read -p "Press Enter..." ;;
            6) systemctl status ${SERVICE_NAME} --no-pager -l; read -p "Press Enter..." ;;
            7) show_links; read -p "Press Enter..." ;;
            8) download_configs; systemctl restart ${SERVICE_NAME}; echo -e "${GREEN}Updated${NC}"; read -p "Press Enter..." ;;
            0) exit 0 ;;
            *) sleep 1 ;;
        esac
    done
}

main_menu
