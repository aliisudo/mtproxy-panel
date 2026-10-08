#!/bin/bash
# ============================================================
#  MTProxy Panel v2.2 - Professional Edition
#  by @ali_sudo_of
#  Auto-rebuild | Multi-client | Web UI | AD Tag | Fake-TLS
# ============================================================

set -e

INSTALL_DIR="/opt/mtproxy"
PANEL_DIR="/opt/mtproxy-panel"
SERVICE_NAME="mtproxy"
WEB_SERVICE="mtproxy-web"
BINARY="$INSTALL_DIR/mtproto-proxy"
LOG="/var/log/mtproxy-install.log"
WARN_FILE=$(mktemp)
VERSION="2.2"

# Non-interactive if already installed or AUTO=1
AUTO_MODE=0
[[ "$1" == "--auto" || "$1" == "-y" ]] && AUTO_MODE=1

# ---------- Terminal UI ----------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BOLD=$'\e[1m'; DIM=$'\e[2m'; NC=$'\e[0m'
    RED=$'\e[38;5;203m'; GREEN=$'\e[38;5;78m'; YELLOW=$'\e[38;5;221m'
    CYAN=$'\e[38;5;117m'; PURPLE=$'\e[38;5;141m'; GRAY=$'\e[38;5;244m'
else
    BOLD=""; DIM=""; NC=""; RED=""; GREEN=""; YELLOW=""; CYAN=""; PURPLE=""; GRAY=""
fi
STEP=0
TOTAL_STEPS=6
STARTED_AT=$SECONDS

cleanup() {
    rm -f "$WARN_FILE"
    [[ -t 1 ]] && printf '\e[?25h'   # show the cursor again
    return 0
}
trap cleanup EXIT

print_banner() {
    [[ -t 1 ]] && clear
    echo ""
    echo "  ${PURPLE}╭──────────────────────────────────────────────────╮${NC}"
    echo "  ${PURPLE}│${NC}  ${PURPLE}${BOLD}◆${NC}  ${BOLD}MTProxy Panel${NC}                          ${GRAY}v${VERSION}${NC}  ${PURPLE}│${NC}"
    echo "  ${PURPLE}│${NC}     ${GRAY}Telegram proxy + web panel · @ali_sudo_of${NC}    ${PURPLE}│${NC}"
    echo "  ${PURPLE}╰──────────────────────────────────────────────────╯${NC}"
    echo ""
}

info()  { echo "  ${CYAN}›${NC} $*"; }
fail()  { echo "  ${RED}✗${NC} $*"; }
# Steps run in a subshell with output in $LOG; they report notes through warn()
warn()  { echo "$*" >> "$WARN_FILE"; }

# Ask a question with a default; the answer goes into the variable named $1
ask() {
    local __answer
    printf "  ${PURPLE}?${NC} ${BOLD}%s${NC} ${GRAY}%s${NC} " "$2" "$3"
    read -r __answer
    printf -v "$1" '%s' "$__answer"
}

# run_step "Label" function: spinner while it runs, ✓ or ✗ with the elapsed time
run_step() {
    local label=$1; shift
    STEP=$((STEP + 1))
    local start=$SECONDS
    echo "=== [$STEP/$TOTAL_STEPS] $label ===" >> "$LOG"
    ( set -e; "$@" ) >> "$LOG" 2>&1 &
    local pid=$!
    if [[ -t 1 ]]; then
        local frames=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏) i=0
        printf '\e[?25l'
        while kill -0 "$pid" 2>/dev/null; do
            printf "\r  ${PURPLE}%s${NC} ${GRAY}%d/%d${NC}  %s ${GRAY}%ds${NC}\e[K" \
                "${frames[i++ % 10]}" "$STEP" "$TOTAL_STEPS" "$label" $((SECONDS - start))
            sleep 0.08
        done
        printf '\e[?25h'
    fi
    if wait "$pid"; then
        printf "\r  ${GREEN}✓${NC} ${GRAY}%d/%d${NC}  %s ${GRAY}%ds${NC}\e[K\n" \
            "$STEP" "$TOTAL_STEPS" "$label" $((SECONDS - start))
        if [[ -s "$WARN_FILE" ]]; then
            while IFS= read -r line; do echo "        ${YELLOW}!${NC} ${GRAY}$line${NC}"; done < "$WARN_FILE"
            : > "$WARN_FILE"
        fi
    else
        printf "\r  ${RED}✗${NC} ${GRAY}%d/%d${NC}  %s ${RED}failed${NC}\e[K\n\n" "$STEP" "$TOTAL_STEPS" "$label"
        [[ -s "$WARN_FILE" ]] && while IFS= read -r line; do echo "    ${RED}$line${NC}"; done < "$WARN_FILE"
        echo "    ${GRAY}Last lines of $LOG:${NC}"
        tail -n 12 "$LOG" | sed "s/^/    ${DIM}│${NC} /"
        echo ""
        exit 1
    fi
}

if [[ $EUID -ne 0 ]]; then
    fail "Run as root (try: sudo -i)"
    exit 1
fi

get_public_ip() {
    curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
    curl -s --max-time 5 https://ifconfig.me 2>/dev/null || \
    hostname -I 2>/dev/null | awk '{print $1}'
}

is_installed() {
    [[ -f "$BINARY" ]] && [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]
}

has_enabled_clients() {
    python3 -c "
import json, sys
c = json.load(open('$INSTALL_DIR/clients.json'))
sys.exit(0 if any(x.get('enabled', True) for x in c) else 1)
" 2>/dev/null
}

# ---------- Steps ----------
install_deps() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq || warn "apt-get update reported errors, continuing"
    apt-get install -y -qq git curl build-essential libssl-dev zlib1g-dev \
        openssl ca-certificates python3 python3-pip python3-venv || true
    if ! command -v xxd >/dev/null 2>&1; then
        apt-get install -y -qq xxd || apt-get install -y -qq vim-common || true
    fi
    # Optional: prints the connection link as a QR code at the end
    apt-get install -y -qq qrencode || true
    for cmd in git make gcc curl python3 xxd; do
        command -v "$cmd" >/dev/null || { warn "Missing required tool: $cmd"; exit 1; }
    done
}

build_mtproxy() {
    rm -rf /tmp/MTProxy 2>/dev/null || true
    git clone --depth 1 https://github.com/TelegramMessenger/MTProxy.git /tmp/MTProxy
    cd /tmp/MTProxy
    if [[ -f Makefile ]] && ! grep -q "fcommon" Makefile; then
        # GCC 10+ needs -fcommon; the Makefile writes "CFLAGS = ..." with spaces
        sed -i -E 's/^(CFLAGS[[:space:]]*=)/\1 -fcommon/; s/^(LDFLAGS[[:space:]]*=)/\1 -fcommon/' Makefile || true
    fi
    if ! make -j"$(nproc)"; then
        warn "Official source did not build, used the GetPageSpeed fork"
        rm -rf /tmp/MTProxy
        git clone --depth 1 https://github.com/GetPageSpeed/MTProxy.git /tmp/MTProxy
        cd /tmp/MTProxy
        make -j"$(nproc)"
    fi
    mkdir -p "$INSTALL_DIR"
    cp -f objs/bin/mtproto-proxy "$BINARY"
    chmod 755 "$BINARY"
}

write_config_updater() {
    mkdir -p "$INSTALL_DIR"
    cat > "$INSTALL_DIR/update-config.sh" <<'EOF'
#!/bin/bash
# Refresh Telegram's proxy secret and server list. Telegram changes them over
# time, so a stale copy slowly breaks connections. Restarts only on change.
DIR=/opt/mtproxy
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsS --max-time 20 https://core.telegram.org/getProxySecret -o "$TMP/proxy-secret" || exit 1
curl -fsS --max-time 20 https://core.telegram.org/getProxyConfig -o "$TMP/proxy-multi.conf" || exit 1
[[ -s "$TMP/proxy-secret" ]] && grep -q "proxy_for" "$TMP/proxy-multi.conf" || exit 1
changed=0
for f in proxy-secret proxy-multi.conf; do
    cmp -s "$TMP/$f" "$DIR/$f" || { cp -f "$TMP/$f" "$DIR/$f"; changed=1; }
done
if [[ $changed -eq 1 && "$1" != "--no-restart" ]] && systemctl is-active --quiet mtproxy; then
    systemctl restart mtproxy
fi
exit 0
EOF
    chmod 755 "$INSTALL_DIR/update-config.sh"

    cat > /etc/systemd/system/mtproxy-config.service <<EOF
[Unit]
Description=Refresh MTProxy Telegram configs
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$INSTALL_DIR/update-config.sh
EOF

    cat > /etc/systemd/system/mtproxy-config.timer <<EOF
[Unit]
Description=Refresh MTProxy Telegram configs daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable --now mtproxy-config.timer >/dev/null 2>&1 || true
}

download_configs() {
    write_config_updater
    if ! "$INSTALL_DIR/update-config.sh" --no-restart; then
        if [[ -s "$INSTALL_DIR/proxy-secret" && -s "$INSTALL_DIR/proxy-multi.conf" ]]; then
            warn "Could not reach core.telegram.org, kept the existing configs"
        else
            warn "Could not download configs from core.telegram.org"
            exit 1
        fi
    fi
}

configure_proxy() {
    systemctl stop ${SERVICE_NAME} 2>/dev/null || true

    # Keep existing secret/clients if present, otherwise create new
    if [[ ! -f "$INSTALL_DIR/clients.json" && ! -f "$INSTALL_DIR/secret.txt" ]]; then
        local SECRET
        SECRET=$(head -c 16 /dev/urandom | xxd -ps)
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
    printf '%s' "$DOMAIN" > "$INSTALL_DIR/tls_domain.txt"

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
    # Fall back to the legacy single secret only before clients.json exists;
    # otherwise an all-disabled client list would bring the old secret back.
    if [[ -z "$SECRETS" && ! -f "$INSTALL_DIR/clients.json" && -f "$INSTALL_DIR/secret.txt" ]]; then
        SECRETS="-S $(cat $INSTALL_DIR/secret.txt)"
    fi

    local ADTAG_ARG=""
    [[ -f "$INSTALL_DIR/adtag.txt" && -s "$INSTALL_DIR/adtag.txt" ]] && ADTAG_ARG=" -P $(cat $INSTALL_DIR/adtag.txt)"
    # A TLS domain switches the proxy to Fake-TLS (ee) only
    local DOMAIN_ARG=""
    [[ -n "$DOMAIN" ]] && DOMAIN_ARG=" -D $DOMAIN"

    cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$BINARY -u nobody -p 8888 -H $PORT $SECRETS$ADTAG_ARG$DOMAIN_ARG --aes-pwd $INSTALL_DIR/proxy-secret $INSTALL_DIR/proxy-multi.conf -M 1
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
        warn "Opened ports $PORT and 8880 in ufw"
    fi
}

install_web() {
    mkdir -p "$PANEL_DIR"
    local TMP_APP
    TMP_APP=$(mktemp)
    if curl -fsSL --max-time 30 https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/web/app.py -o "$TMP_APP" \
            && grep -q "Flask" "$TMP_APP"; then
        chmod 644 "$TMP_APP"
        mv -f "$TMP_APP" "$PANEL_DIR/app.py"
    else
        rm -f "$TMP_APP"
        if [[ -f "$PANEL_DIR/app.py" ]]; then
            warn "Could not download the panel, kept the existing one"
        else
            warn "Could not download the web panel"
            exit 1
        fi
    fi

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
}

start_services() {
    if has_enabled_clients; then
        systemctl start ${SERVICE_NAME}
        sleep 2
        systemctl is-active --quiet ${SERVICE_NAME} || { warn "The proxy did not stay up, see: journalctl -u ${SERVICE_NAME}"; exit 1; }
    else
        systemctl disable ${SERVICE_NAME} >/dev/null 2>&1 || true
        warn "No enabled clients, so the proxy was not started. Enable one in the panel."
    fi
}

# ---------- Summary ----------
print_summary() {
    local IP SECRET LINK PASS took
    IP=$(get_public_ip)
    SECRET=$(python3 -c "
import json,sys
try:
    c=json.load(open('$INSTALL_DIR/clients.json'))[0]['secret']
    print(c)
except:
    print(open('$INSTALL_DIR/secret.txt').read().strip() if __import__('os').path.exists('$INSTALL_DIR/secret.txt') else '')
" 2>/dev/null)
    if [[ -n "$DOMAIN" ]]; then
        LINK="tg://proxy?server=${IP}&port=${PORT}&secret=ee${SECRET}$(printf '%s' "$DOMAIN" | xxd -p | tr -d '\n')"
    else
        LINK="tg://proxy?server=${IP}&port=${PORT}&secret=dd${SECRET}"
    fi
    PASS=$(cat "$INSTALL_DIR/panel_pass.txt" 2>/dev/null || echo admin)
    took=$((SECONDS - STARTED_AT))

    echo ""
    if has_enabled_clients; then
        echo "  ${GREEN}${BOLD}✓ MTProxy is ready${NC} ${GRAY}in $((took / 60))m $((took % 60))s${NC}"
    else
        echo "  ${YELLOW}${BOLD}! Installed, proxy not started${NC} ${GRAY}enable a client in the panel${NC}"
    fi
    echo ""
    echo "  ${BOLD}Web panel${NC}"
    echo "    ${GRAY}URL       ${NC}${CYAN}http://${IP}:8880${NC}"
    echo "    ${GRAY}Password  ${NC}${PASS}"
    echo ""
    echo "  ${BOLD}Proxy${NC}"
    echo "    ${GRAY}Port      ${NC}${PORT}"
    if [[ -n "$DOMAIN" ]]; then
        echo "    ${GRAY}Mode      ${NC}Fake-TLS ${GRAY}(looks like HTTPS to ${DOMAIN})${NC}"
    else
        echo "    ${GRAY}Mode      ${NC}Secure ${GRAY}(dd, random padding)${NC}"
    fi
    echo ""
    echo "  ${BOLD}Connection link${NC}"
    echo "    ${PURPLE}${LINK}${NC}"
    if command -v qrencode >/dev/null 2>&1 && [[ -t 1 ]]; then
        echo ""
        qrencode -t ANSIUTF8 -m 1 "$LINK" | sed 's/^/    /'
        echo "    ${GRAY}Scan with your phone to add the proxy to Telegram${NC}"
    fi
    echo ""
    echo "  ${GRAY}Install log: ${LOG}${NC}"
    echo ""
}

do_full_install() {
    PORT=${1:-443}
    ADTAG=${2:-""}
    DOMAIN=${3:-""}

    echo ""
    run_step "Installing system packages"     install_deps
    run_step "Building MTProxy from source"   build_mtproxy
    run_step "Fetching Telegram configs"      download_configs
    run_step "Configuring the proxy service"  configure_proxy
    run_step "Installing the web panel"       install_web
    run_step "Starting services"              start_services

    print_summary
}

# ========== Main ==========
print_banner
: > "$LOG"

if is_installed; then
    CURRENT_PORT=$(cat "$INSTALL_DIR/port.txt" 2>/dev/null || echo "443")
    CURRENT_ADTAG=$(cat "$INSTALL_DIR/adtag.txt" 2>/dev/null || echo "")
    CURRENT_DOMAIN=$(cat "$INSTALL_DIR/tls_domain.txt" 2>/dev/null || echo "")
    info "Existing install found, updating it. Clients and settings are kept."
    do_full_install "$CURRENT_PORT" "$CURRENT_ADTAG" "$CURRENT_DOMAIN"
else
    # Fresh install
    if [[ $AUTO_MODE -eq 1 ]]; then
        do_full_install 443 "" ""
    else
        while true; do
            ask PORT "Proxy port" "[443]"
            PORT=${PORT:-443}
            [[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) && break
            echo "    ${RED}Enter a number between 1 and 65535${NC}"
        done
        ask ADTAG "AD Tag from @MTProxybot" "[optional]"
        while true; do
            ask DOMAIN "Fake-TLS domain, e.g. www.cloudflare.com" "[optional]"
            DOMAIN=$(echo "$DOMAIN" | tr 'A-Z' 'a-z' | tr -d ' ')
            [[ -z "$DOMAIN" || "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$ ]] && break
            echo "    ${RED}That doesn't look like a domain. Leave it empty to skip.${NC}"
        done
        do_full_install "$PORT" "$ADTAG" "$DOMAIN"
    fi
fi
