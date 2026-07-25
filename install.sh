#!/bin/bash
# ============================================================
#  MTProxy Panel - Complete Telegram MTProxy Installer & Manager
#  For Ubuntu 20.04 / 22.04 / 24.04
#  Author: Grok (for aliisudo)
#  Features: Interactive UI Menu | Auto build | Systemd | Links
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
CONFIG_DIR="/opt/mtproxy"
BINARY="$INSTALL_DIR/mtproto-proxy"
SECRET_FILE="$INSTALL_DIR/secret.txt"
PORT_FILE="$INSTALL_DIR/port.txt"

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR] Please run as root: sudo bash $0${NC}"
    exit 1
fi

# Detect OS
if ! grep -qi ubuntu /etc/os-release && ! grep -qi debian /etc/os-release; then
    echo -e "${YELLOW}[WARN] This script is optimized for Ubuntu/Debian. Continuing anyway...${NC}"
fi

print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           MTProxy Panel - Telegram Proxy Manager         ║"
    echo "║              Ubuntu 20.04 / 22.04 / 24.04                ║"
    echo "║                   by Grok for aliisudo                   ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

get_public_ip() {
    local ip
    ip=$(curl -s --max-time 5 https://api.ipify.org || curl -s --max-time 5 https://ifconfig.me || curl -s --max-time 5 https://icanhazip.com)
    echo "$ip"
}

check_installed() {
    if [[ -f "$BINARY" ]] && systemctl list-unit-files | grep -q "${SERVICE_NAME}.service"; then
        return 0
    else
        return 1
    fi
}

install_deps() {
    echo -e "${BLUE}[+] Installing dependencies...${NC}"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        git curl build-essential libssl-dev zlib1g-dev \
        xxd openssl ca-certificates > /dev/null 2>&1 || {
            apt-get install -y -qq vim-common > /dev/null 2>&1 || true
        }
    echo -e "${GREEN}[✓] Dependencies installed${NC}"
}

build_mtproxy() {
    echo -e "${BLUE}[+] Building MTProxy from source...${NC}"
    
    # Use official repo + common fixes for modern gcc
    if [[ -d /tmp/MTProxy ]]; then
        rm -rf /tmp/MTProxy
    fi
    
    git clone --depth 1 https://github.com/TelegramMessenger/MTProxy.git /tmp/MTProxy
    cd /tmp/MTProxy
    
    # Fix for modern compilers (gcc 10+)
    if ! grep -q "fcommon" Makefile; then
        sed -i 's/CFLAGS=/CFLAGS=-fcommon /' Makefile || true
        sed -i 's/LDFLAGS=/LDFLAGS=-fcommon /' Makefile || true
    fi
    
    make -j$(nproc) > /tmp/mtproxy_build.log 2>&1 || {
        echo -e "${YELLOW}[!] Official build failed, trying community fork...${NC}"
        rm -rf /tmp/MTProxy
        git clone --depth 1 https://github.com/GetPageSpeed/MTProxy.git /tmp/MTProxy
        cd /tmp/MTProxy
        make -j$(nproc) > /tmp/mtproxy_build.log 2>&1 || {
            echo -e "${RED}[ERROR] Build failed. Check /tmp/mtproxy_build.log${NC}"
            exit 1
        }
    }
    
    mkdir -p "$INSTALL_DIR"
    cp objs/bin/mtproto-proxy "$BINARY"
    chmod +x "$BINARY"
    
    # Create system user
    if ! id mtproxy &>/dev/null; then
        useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" mtproxy || true
    fi
    chown -R mtproxy:mtproxy "$INSTALL_DIR"
    
    echo -e "${GREEN}[✓] MTProxy built successfully${NC}"
}

download_configs() {
    echo -e "${BLUE}[+] Downloading Telegram proxy configs...${NC}"
    curl -s https://core.telegram.org/getProxySecret -o "$INSTALL_DIR/proxy-secret"
    curl -s https://core.telegram.org/getProxyConfig -o "$INSTALL_DIR/proxy-multi.conf"
    chown mtproxy:mtproxy "$INSTALL_DIR/proxy-secret" "$INSTALL_DIR/proxy-multi.conf"
    echo -e "${GREEN}[✓] Configs downloaded${NC}"
}

generate_secret() {
    local secret
    secret=$(head -c 16 /dev/urandom | xxd -ps)
    echo "$secret" > "$SECRET_FILE"
    chown mtproxy:mtproxy "$SECRET_FILE"
    echo "$secret"
}

create_systemd() {
    local port=$1
    local secret=$2
    
    cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mtproxy
Group=mtproxy
WorkingDirectory=$INSTALL_DIR
ExecStart=$BINARY -u mtproxy -p 8888 -H $port -S $secret --aes-pwd $INSTALL_DIR/proxy-secret $INSTALL_DIR/proxy-multi.conf -M 1
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    echo -e "${GREEN}[✓] Systemd service created${NC}"
}

setup_firewall() {
    local port=$1
    if command -v ufw &>/dev/null; then
        if ufw status | grep -q "Status: active"; then
            ufw allow $port/tcp > /dev/null 2>&1 || true
            echo -e "${GREEN}[✓] UFW: port $port opened${NC}"
        fi
    fi
    # Also try iptables if needed
    iptables -I INPUT -p tcp --dport $port -j ACCEPT 2>/dev/null || true
}

do_install() {
    print_banner
    echo -e "${YELLOW}=== Installing MTProxy ===${NC}\n"
    
    if check_installed; then
        echo -e "${YELLOW}[!] MTProxy seems already installed.${NC}"
        read -p "Reinstall? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            return
        fi
        systemctl stop ${SERVICE_NAME} 2>/dev/null || true
    fi
    
    # Ask for port
    local default_port=443
    read -p "Enter listen port [default: $default_port]: " input_port
    PORT=${input_port:-$default_port}
    
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        echo -e "${RED}Invalid port${NC}"
        return
    fi
    
    echo "$PORT" > "$PORT_FILE"
    
    install_deps
    build_mtproxy
    download_configs
    
    SECRET=$(generate_secret)
    create_systemd "$PORT" "$SECRET"
    setup_firewall "$PORT"
    
    systemctl start ${SERVICE_NAME}
    sleep 2
    
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              MTProxy installed successfully!             ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}\n"
        show_links
    else
        echo -e "${RED}[ERROR] Service failed to start. Check: journalctl -u ${SERVICE_NAME} -e${NC}"
    fi
}

do_uninstall() {
    print_banner
    echo -e "${YELLOW}=== Uninstall MTProxy ===${NC}\n"
    read -p "Are you sure? This will remove everything (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        return
    fi
    
    systemctl stop ${SERVICE_NAME} 2>/dev/null || true
    systemctl disable ${SERVICE_NAME} 2>/dev/null || true
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload
    
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
    fi
    
    userdel mtproxy 2>/dev/null || true
    
    echo -e "${GREEN}[✓] MTProxy completely removed${NC}"
}

show_status() {
    print_banner
    echo -e "${YELLOW}=== Service Status ===${NC}\n"
    if check_installed; then
        systemctl status ${SERVICE_NAME} --no-pager -l || true
        echo ""
        echo -e "${CYAN}Port:${NC} $(cat $PORT_FILE 2>/dev/null || echo 'N/A')"
        echo -e "${CYAN}Secret:${NC} $(cat $SECRET_FILE 2>/dev/null || echo 'N/A')"
    else
        echo -e "${RED}MTProxy is not installed.${NC}"
    fi
}

start_service() {
    systemctl start ${SERVICE_NAME}
    echo -e "${GREEN}[✓] Started${NC}"
}

stop_service() {
    systemctl stop ${SERVICE_NAME}
    echo -e "${GREEN}[✓] Stopped${NC}"
}

restart_service() {
    systemctl restart ${SERVICE_NAME}
    echo -e "${GREEN}[✓] Restarted${NC}"
}

show_links() {
    print_banner
    if ! check_installed; then
        echo -e "${RED}MTProxy is not installed.${NC}"
        return
    fi
    
    local ip=$(get_public_ip)
    local port=$(cat "$PORT_FILE" 2>/dev/null || echo "443")
    local secret=$(cat "$SECRET_FILE" 2>/dev/null)
    
    if [[ -z "$secret" || -z "$ip" ]]; then
        echo -e "${RED}Cannot generate links (missing IP or secret)${NC}"
        return
    fi
    
    # Classic secret format (dd = simple, ee = with TLS)
    local secret_dd="dd${secret}"
    local secret_ee="ee${secret}"
    
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                 Connection Links                         ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}\n"
    
    echo -e "${CYAN}Server IP:${NC}   $ip"
    echo -e "${CYAN}Port:${NC}       $port"
    echo -e "${CYAN}Secret:${NC}     $secret"
    echo ""
    
    echo -e "${YELLOW}1) Simple (dd) - Recommended for most users:${NC}"
    echo -e "${BOLD}tg://proxy?server=${ip}&port=${port}&secret=${secret_dd}${NC}"
    echo ""
    echo -e "${YELLOW}2) With Fake TLS (ee) - Better for restricted networks:${NC}"
    echo -e "${BOLD}tg://proxy?server=${ip}&port=${port}&secret=${secret_ee}${NC}"
    echo ""
    echo -e "${YELLOW}3) HTTPS link (for sharing):${NC}"
    echo -e "https://t.me/proxy?server=${ip}&port=${port}&secret=${secret_dd}"
    echo ""
    echo -e "${BLUE}Copy the tg:// link and open it in Telegram, or share the https link.${NC}"
}

update_configs() {
    echo -e "${BLUE}[+] Updating Telegram configs...${NC}"
    download_configs
    systemctl restart ${SERVICE_NAME}
    echo -e "${GREEN}[✓] Configs updated and service restarted${NC}"
}

change_port() {
    if ! check_installed; then
        echo -e "${RED}Not installed${NC}"
        return
    fi
    read -p "New port: " new_port
    if ! [[ "$new_port" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}Invalid${NC}"
        return
    fi
    echo "$new_port" > "$PORT_FILE"
    local secret=$(cat "$SECRET_FILE")
    create_systemd "$new_port" "$secret"
    setup_firewall "$new_port"
    systemctl restart ${SERVICE_NAME}
    echo -e "${GREEN}[✓] Port changed to $new_port${NC}"
    show_links
}

main_menu() {
    while true; do
        print_banner
        
        if check_installed; then
            local status=$(systemctl is-active ${SERVICE_NAME} 2>/dev/null || echo "inactive")
            if [[ "$status" == "active" ]]; then
                echo -e "Status: ${GREEN}● Running${NC}"
            else
                echo -e "Status: ${RED}● Stopped${NC}"
            fi
            echo -e "Port: $(cat $PORT_FILE 2>/dev/null || echo '?')"
        else
            echo -e "Status: ${YELLOW}Not installed${NC}"
        fi
        
        echo ""
        echo -e "${BOLD}========== MENU ==========${NC}"
        echo -e "  ${GREEN}1)${NC} Install / Reinstall MTProxy"
        echo -e "  ${GREEN}2)${NC} Uninstall"
        echo -e "  ${GREEN}3)${NC} Start"
        echo -e "  ${GREEN}4)${NC} Stop"
        echo -e "  ${GREEN}5)${NC} Restart"
        echo -e "  ${GREEN}6)${NC} Status / Logs"
        echo -e "  ${GREEN}7)${NC} Show Connection Links"
        echo -e "  ${GREEN}8)${NC} Update Telegram Configs"
        echo -e "  ${GREEN}9)${NC} Change Port"
        echo -e "  ${GREEN}0)${NC} Exit"
        echo -e "${BOLD}==========================${NC}"
        echo ""
        read -p "Select option: " choice
        
        case $choice in
            1) do_install; read -p "Press Enter to continue..." ;;
            2) do_uninstall; read -p "Press Enter to continue..." ;;
            3) start_service; read -p "Press Enter to continue..." ;;
            4) stop_service; read -p "Press Enter to continue..." ;;
            5) restart_service; read -p "Press Enter to continue..." ;;
            6) show_status; read -p "Press Enter to continue..." ;;
            7) show_links; read -p "Press Enter to continue..." ;;
            8) update_configs; read -p "Press Enter to continue..." ;;
            9) change_port; read -p "Press Enter to continue..." ;;
            0) echo -e "${GREEN}Bye!${NC}"; exit 0 ;;
            *) echo -e "${RED}Invalid option${NC}"; sleep 1 ;;
        esac
    done
}

# Entry point
main_menu
