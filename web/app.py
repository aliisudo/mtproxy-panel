#!/usr/bin/env python3
# MTProxy Professional Web Panel
# by @ali_sudo_of

import os
import re
import json
import subprocess
import secrets
import time
from functools import wraps
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

INSTALL_DIR = "/opt/mtproxy"
BINARY = f"{INSTALL_DIR}/mtproto-proxy"
SECRET_FILE = f"{INSTALL_DIR}/secret.txt"          # main secret (legacy)
CLIENTS_FILE = f"{INSTALL_DIR}/clients.json"       # multi clients
PORT_FILE = f"{INSTALL_DIR}/port.txt"
ADTAG_FILE = f"{INSTALL_DIR}/adtag.txt"
PANEL_PASS_FILE = f"{INSTALL_DIR}/panel_pass.txt"
TLS_DOMAIN_FILE = f"{INSTALL_DIR}/tls_domain.txt"  # set => Fake-TLS (ee) mode
SERVICE = "mtproxy"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

def get_panel_password():
    if os.path.exists(PANEL_PASS_FILE):
        with open(PANEL_PASS_FILE) as f:
            return f.read().strip()
    return "admin"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def run_cmd(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, str(e)

def is_installed():
    return os.path.exists(BINARY) and os.path.exists(f"/etc/systemd/system/{SERVICE}.service")

def get_status():
    if not is_installed():
        return "not_installed"
    ok, out = run_cmd(f"systemctl is-active {SERVICE}")
    # "inactive" contains "active", so compare the whole word
    return "active" if out.strip() == "active" else "inactive"

def get_port():
    if os.path.exists(PORT_FILE):
        return open(PORT_FILE).read().strip()
    return "443"

def get_adtag():
    if os.path.exists(ADTAG_FILE):
        return open(ADTAG_FILE).read().strip()
    return ""

def get_tls_domain():
    if os.path.exists(TLS_DOMAIN_FILE):
        return open(TLS_DOMAIN_FILE).read().strip()
    return ""

def link_context():
    """Values every page needs to build connection links."""
    domain = get_tls_domain()
    return {"ip": get_public_ip(), "port": get_port(), "tls_domain": domain, "tls_hex": domain.encode().hex()}

_ip_cache = {"ip": "", "until": 0}

def get_public_ip():
    # Looking the IP up on every page load made each page wait for the lookup
    if time.time() < _ip_cache["until"]:
        return _ip_cache["ip"]
    ok, out = run_cmd("curl -s --max-time 4 https://api.ipify.org || curl -s --max-time 4 https://ifconfig.me || echo ''")
    ip = out.strip() if ok else ""
    _ip_cache.update(ip=ip, until=time.time() + (3600 if ip else 300))
    return ip

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE) as f:
                return json.load(f)
        except:
            pass
    # migrate old single secret
    if os.path.exists(SECRET_FILE):
        s = open(SECRET_FILE).read().strip()
        if s:
            clients = [{"id": "main", "name": "Main Client", "secret": s, "enabled": True, "created": datetime.now().isoformat()}]
            save_clients(clients)
            return clients
    return []

def save_clients(clients):
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)

def rebuild_service():
    """Rebuild systemd unit with all enabled secrets + adtag"""
    port = get_port()
    adtag = get_adtag()
    domain = get_tls_domain()
    clients = [c for c in load_clients() if c.get("enabled", True)]
    if not clients:
        return False, "No enabled clients"

    secrets_args = " ".join([f"-S {c['secret']}" for c in clients])
    adtag_arg = f" -P {adtag}" if adtag else ""
    domain_arg = f" -D {domain}" if domain else ""

    content = f"""[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={INSTALL_DIR}
ExecStart={BINARY} -u nobody -p 8888 -H {port} {secrets_args}{adtag_arg}{domain_arg} --aes-pwd {INSTALL_DIR}/proxy-secret {INSTALL_DIR}/proxy-multi.conf -M 1
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    with open(f"/etc/systemd/system/{SERVICE}.service", "w") as f:
        f.write(content)
    run_cmd("systemctl daemon-reload")
    run_cmd(f"systemctl enable {SERVICE}")
    return True, "ok"

def apply_service():
    """Rewrite the unit and restart. With no enabled client the old unit would
    keep serving the disabled secrets, so stop the proxy instead."""
    ok, _ = rebuild_service()
    if ok:
        run_cmd(f"systemctl restart {SERVICE}")
        return True
    run_cmd(f"systemctl stop {SERVICE}")
    return False

# ==================== TEMPLATES ====================

def _svg(*parts, size=20, width=2):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + "".join(p if p.startswith("<") else f'<path d="{p}"/>' for p in parts) + "</svg>")

ICONS = {
    "logo": _svg("M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z", "M9 12l2 2 4-4", size=18, width=2.2),
    "logo_lg": _svg("M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z", "M9 12l2 2 4-4", size=32, width=2),
    "play": _svg("M7 5l12 7-12 7V5z", size=16),
    "stop": _svg('<rect x="6" y="6" width="12" height="12" rx="2"/>', size=16),
    "restart": _svg("M20 12a8 8 0 1 1-2.3-5.7", "M20 4v5h-5", size=16),
    "plus": _svg("M12 5v14", "M5 12h14", size=16, width=2.4),
    "copy": _svg('<rect x="9" y="9" width="11" height="11" rx="2.5"/>', "M15 9V6.5A2.5 2.5 0 0 0 12.5 4h-6A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15H9", size=16),
    "check": _svg("M5 12.5l4.5 4.5L19 7", size=16, width=2.6),
    "x": _svg("M7 7l10 10", "M17 7L7 17", size=14, width=2.8),
    "check_sm": _svg("M5 12.5l4.5 4.5L19 7", size=14, width=3),
    "chev_right": _svg("M9 6l6 6-6 6", size=16, width=2.4),
    "chev_left": _svg("M15 5l-7 7 7 7", size=20, width=2.4),
    "logout": _svg("M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3", "M10 8l-4 4 4 4", "M6 12h10", size=18),
    "eye": _svg("M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", '<circle cx="12" cy="12" r="3"/>', size=18),
    "send": _svg("M7 17L17 7", "M8 7h9v9", size=18, width=2.4),
    "users": _svg('<circle cx="9" cy="8" r="3.5"/>', "M2.5 20c0-3.6 2.9-6.5 6.5-6.5s6.5 2.9 6.5 6.5", "M16 4.5a3.5 3.5 0 0 1 0 7", "M18.5 13.8c1.8.9 3 2.9 3 5.2", size=26),
    "terminal": _svg("M4 17l6-5-6-5", "M12 19h8", size=26),
    "trash": _svg("M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12", "M9 7V4h6v3", size=16),
}

CSS = """
:root {
  color-scheme: light dark;
  --spring: cubic-bezier(0.34, 1.4, 0.64, 1);
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --bg: #f2f2f7;
  --surface: #ffffff;
  --surface-2: #f2f2f7;
  --fill: rgba(120, 120, 128, 0.12);
  --fill-2: rgba(120, 120, 128, 0.24);
  --separator: rgba(60, 60, 67, 0.14);
  --text: #1c1c1e;
  --text-2: rgba(60, 60, 67, 0.64);
  --text-3: rgba(60, 60, 67, 0.4);
  --accent: #5856d6;
  --accent-press: #4846c4;
  --accent-tint: rgba(88, 86, 214, 0.12);
  --green: #248a3d;
  --green-tint: rgba(52, 199, 89, 0.15);
  --red: #d70015;
  --red-tint: rgba(255, 59, 48, 0.12);
  --orange: #c93400;
  --orange-tint: rgba(255, 149, 0, 0.15);
  --switch-on: #34c759;
  --nav: rgba(242, 242, 247, 0.72);
  --toast: rgba(255, 255, 255, 0.86);
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 6px 24px rgba(0, 0, 0, 0.05);
  --avatar-l: 42%;
  --r-lg: 22px;
  --r-md: 14px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #000000;
    --surface: #1c1c1e;
    --surface-2: #2c2c2e;
    --fill: rgba(120, 120, 128, 0.24);
    --fill-2: rgba(120, 120, 128, 0.36);
    --separator: rgba(84, 84, 88, 0.55);
    --text: #f5f5f7;
    --text-2: rgba(235, 235, 245, 0.62);
    --text-3: rgba(235, 235, 245, 0.32);
    --accent: #7d7aff;
    --accent-press: #6b68f0;
    --accent-tint: rgba(125, 122, 255, 0.18);
    --green: #30d158;
    --green-tint: rgba(48, 209, 88, 0.16);
    --red: #ff453a;
    --red-tint: rgba(255, 69, 58, 0.16);
    --orange: #ff9f0a;
    --orange-tint: rgba(255, 159, 10, 0.16);
    --switch-on: #30d158;
    --nav: rgba(0, 0, 0, 0.62);
    --toast: rgba(44, 44, 46, 0.86);
    --shadow: none;
    --avatar-l: 72%;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-text-size-adjust: 100%; }
body {
  font: 15px/1.47 var(--font);
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -webkit-tap-highlight-color: transparent;
}
a { color: inherit; text-decoration: none; }
button, input, select { font: inherit; color: inherit; }
svg { display: block; flex: none; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.mono { font-family: var(--mono); }

/* Navigation: translucent material, content scrolls underneath */
.nav {
  position: sticky; top: 0; z-index: 40;
  background: var(--nav);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  box-shadow: 0 0.5px 0 transparent;
  transition: box-shadow 250ms ease, background-color 250ms ease;
}
/* Scroll edge: the divider only appears once content slides under the bar */
.nav.scrolled { box-shadow: 0 0.5px 0 var(--separator), 0 8px 24px -12px rgba(0, 0, 0, 0.25); }
.nav-inner {
  max-width: 1080px; margin: 0 auto; height: 56px; padding: 0 16px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 17px; letter-spacing: -0.01em; }
.logo {
  width: 30px; height: 30px; border-radius: 9px; flex: none;
  display: grid; place-items: center; color: #fff;
  background: linear-gradient(140deg, #7d7aff, #5856d6 45%, #0a84ff);
  box-shadow: inset 0 0.5px 0 rgba(255, 255, 255, 0.45), 0 2px 8px rgba(88, 86, 214, 0.3);
}
.nav-link {
  display: inline-flex; align-items: center; gap: 4px; color: var(--accent);
  font-size: 16px; font-weight: 500; padding: 8px 10px; margin: 0 -10px; border-radius: 10px;
  transition: opacity 150ms ease;
}
.nav-link:active { opacity: 0.5; }

/* Page */
.page { max-width: 1080px; margin: 0 auto; padding: 28px 16px 56px; }
.page-head { margin-bottom: 22px; }
.eyebrow { font-size: 13px; font-weight: 600; color: var(--text-2); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px; }
h1 { font-size: 34px; line-height: 1.12; font-weight: 700; letter-spacing: -0.025em; }
h2 { font-size: 20px; line-height: 1.25; font-weight: 650; letter-spacing: -0.015em; }
.layout { display: grid; gap: 20px; align-items: start; }
@media (min-width: 900px) { .layout { grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr); } }
.col { display: grid; gap: 20px; min-width: 0; }
.card { background: var(--surface); border-radius: var(--r-lg); padding: 20px; box-shadow: var(--shadow); min-width: 0; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.card-sub { color: var(--text-2); font-size: 14px; margin-top: 2px; }
.foot { text-align: center; color: var(--text-3); font-size: 12px; margin-top: 32px; }

/* Status */
.status {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px 6px 11px; border-radius: 999px; font-weight: 600; font-size: 14px;
}
.status .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; position: relative; }
.status--active { color: var(--green); background: var(--green-tint); }
.status--active .dot::after {
  content: ""; position: absolute; inset: 0; border-radius: 50%; background: currentColor;
  animation: pulse 2s cubic-bezier(0.22, 1, 0.36, 1) infinite;
}
@keyframes pulse { from { transform: scale(1); opacity: 0.55; } to { transform: scale(3.2); opacity: 0; } }
.status--inactive { color: var(--red); background: var(--red-tint); }
.status--not_installed { color: var(--orange); background: var(--orange-tint); }

/* Hero */
.hero-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.hero-actions { display: flex; gap: 8px; }
.hero-actions form { display: contents; }
.address { margin: 24px 0 20px; }
.label { display: block; font-size: 13px; color: var(--text-2); margin-bottom: 4px; }
.address-value {
  font-family: var(--mono); font-size: clamp(24px, 6vw, 32px); font-weight: 600;
  letter-spacing: -0.03em; line-height: 1.15; word-break: break-all;
}
.address-value .port { color: var(--text-3); }
.stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
@media (min-width: 560px) { .stats { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.stat { background: var(--surface-2); border-radius: var(--r-md); padding: 12px 14px; min-width: 0; }
.stat .label { font-size: 12px; margin-bottom: 2px; }
.stat-value { font-size: 22px; font-weight: 650; letter-spacing: -0.02em; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat-value.small { font-size: 15px; font-family: var(--mono); font-weight: 500; letter-spacing: 0; line-height: 1.8; }
.stat-value.none { color: var(--text-3); }

/* Buttons: feedback on press, not on release */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  height: 40px; padding: 0 16px; border: 0; border-radius: 999px;
  font-size: 15px; font-weight: 600; white-space: nowrap; cursor: pointer;
  user-select: none; -webkit-user-select: none; touch-action: manipulation;
  position: relative;
  transition: transform 450ms var(--spring), background-color 150ms ease, opacity 150ms ease, box-shadow 250ms ease;
}
.btn:active { transform: scale(0.95); transition-duration: 90ms, 150ms, 150ms, 250ms; transition-timing-function: ease-out; }
.btn-primary { box-shadow: 0 4px 14px -4px var(--accent); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-tinted { background: var(--accent-tint); color: var(--accent); }
.btn-green { background: var(--green-tint); color: var(--green); }
.btn-red { background: var(--red-tint); color: var(--red); }
.btn-gray { background: var(--fill); color: var(--text); }
@media (hover: hover) {
  .btn-primary:hover { background: var(--accent-press); }
  .btn-tinted:hover, .btn-green:hover, .btn-red:hover, .btn-gray:hover { opacity: 0.8; }
}
.btn-sm { height: 34px; padding: 0 13px; font-size: 14px; }
.btn-icon { width: 34px; padding: 0; }
.btn-lg { height: 50px; width: 100%; border-radius: 14px; font-size: 17px; }
.btn-block { width: 100%; }
.stack { display: grid; gap: 10px; margin-top: 16px; }

/* Client list */
.list { list-style: none; margin: 0 -10px; }
.list li { position: relative; }
.list li + li::before { content: ""; position: absolute; top: 0; left: 64px; right: 10px; height: 0.5px; background: var(--separator); }
.row {
  display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 14px;
  transition: background-color 150ms ease, transform 100ms ease-out;
}
.row:active { background: var(--fill); transform: scale(0.985); transition-duration: 90ms; }
@media (hover: hover) { .row:hover { background: var(--fill); } }
.avatar {
  width: 42px; height: 42px; border-radius: 50%; flex: none;
  display: grid; place-items: center; font-weight: 650; font-size: 17px;
  color: hsl(var(--h) 70% var(--avatar-l)); background: hsl(var(--h) 85% 60% / 0.16);
}
.row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.row-title { font-weight: 600; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-sub { color: var(--text-2); font-size: 13px; font-family: var(--mono); }
.tag { font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px; white-space: nowrap; }
.tag--on { color: var(--green); background: var(--green-tint); }
.tag--off { color: var(--text-2); background: var(--fill); }
.chev { color: var(--text-3); }

.empty { text-align: center; padding: 20px 8px 8px; }
.empty-icon {
  width: 60px; height: 60px; border-radius: 18px; margin: 0 auto 14px;
  display: grid; place-items: center; background: var(--accent-tint); color: var(--accent);
}
.empty h3 { font-size: 17px; font-weight: 600; }
.empty p { color: var(--text-2); margin: 4px auto 18px; max-width: 320px; }

/* Copy rows */
.copy {
  display: flex; align-items: center; gap: 12px; width: 100%; text-align: left;
  background: var(--surface-2); border: 0; border-radius: var(--r-md); padding: 12px 12px 12px 14px;
  cursor: pointer; touch-action: manipulation;
  transition: transform 100ms ease-out, background-color 150ms ease;
}
.copy + .copy { margin-top: 8px; }
.copy:active { transform: scale(0.975); transition-duration: 90ms; }
.copy-main { flex: 1; min-width: 0; }
.copy-label { display: block; font-size: 13px; font-weight: 600; }
.copy-text {
  display: block; margin-top: 2px; font-family: var(--mono); font-size: 12.5px; color: var(--text-2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.copy-icon {
  position: relative; width: 34px; height: 34px; border-radius: 50%; flex: none;
  display: grid; place-items: center; background: var(--accent-tint); color: var(--accent);
  transition: background-color 200ms ease, color 200ms ease;
}
.copy-icon > span { grid-area: 1 / 1; display: grid; transition: opacity 150ms ease, transform 250ms cubic-bezier(0.22, 1, 0.36, 1); }
.copy-icon .i-check { opacity: 0; transform: scale(0.4); }
.copy.copied .copy-icon { background: var(--green-tint); color: var(--green); }
.copy.copied .i-copy { opacity: 0; transform: scale(0.4); }
.copy.copied .i-check { opacity: 1; transform: scale(1); }

/* Forms */
.field { display: block; margin-bottom: 14px; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--text-2); margin-bottom: 6px; }
.input {
  width: 100%; height: 48px; padding: 0 14px; border-radius: 12px;
  border: 1px solid transparent; background: var(--surface-2); font-size: 16px; outline: none;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.input::placeholder { color: var(--text-3); }
.input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-tint); }
.hint { font-size: 12.5px; color: var(--text-3); margin-top: 6px; }

.switch-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 12px 10px 14px; background: var(--surface-2); border-radius: 12px; margin-bottom: 14px; cursor: pointer;
}
.switch-row .sub { display: block; font-size: 13px; color: var(--text-2); }
.switch { position: relative; width: 51px; height: 31px; flex: none; }
.switch input { position: absolute; inset: 0; opacity: 0; margin: 0; cursor: pointer; z-index: 1; }
.switch .track { position: absolute; inset: 0; border-radius: 999px; background: var(--fill-2); transition: background-color 200ms ease; }
.switch .thumb {
  position: absolute; top: 2px; left: 2px; width: 27px; height: 27px; border-radius: 999px; background: #fff;
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.15), 0 1px 1px rgba(0, 0, 0, 0.16);
  transition: transform 400ms var(--spring), width 250ms var(--ease-out);
}
.switch input:checked ~ .track { background: var(--switch-on); }
.switch input:checked ~ .thumb { transform: translateX(20px); }
/* Like iOS, the thumb stretches toward its destination while pressed */
.switch input:active ~ .thumb { width: 33px; }
.switch input:checked:active ~ .thumb { transform: translateX(14px); }
.switch input:focus-visible ~ .track { box-shadow: 0 0 0 4px var(--accent-tint); }

/* Toasts enter and leave along the same path */
.toasts {
  position: fixed; top: 66px; left: 50%; transform: translateX(-50%); z-index: 60;
  display: grid; gap: 8px; width: min(420px, calc(100% - 32px)); pointer-events: none;
}
.toast {
  pointer-events: auto; cursor: pointer; display: flex; align-items: center; gap: 10px;
  padding: 12px 16px 12px 12px; border-radius: 16px; font-size: 14px; font-weight: 500;
  background: var(--toast); -webkit-backdrop-filter: saturate(180%) blur(20px); backdrop-filter: saturate(180%) blur(20px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.14), 0 0 0 0.5px var(--separator);
  animation: toast-in 450ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
.toast.leaving { animation: toast-out 250ms cubic-bezier(0.64, 0, 0.78, 0) forwards; }
@keyframes toast-in { from { opacity: 0; transform: translateY(-20px) scale(0.96); } }
@keyframes toast-out { to { opacity: 0; transform: translateY(-20px) scale(0.96); } }
.toast .ti { width: 24px; height: 24px; border-radius: 50%; flex: none; display: grid; place-items: center; color: #fff; background: var(--accent); }
.toast--success .ti { background: var(--green); }
.toast--error .ti { background: var(--red); }

/* Profile (client page) */
.profile { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; min-width: 0; }
.profile .avatar { width: 64px; height: 64px; font-size: 26px; }
.profile h1 { font-size: 30px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.profile .tag { display: inline-block; margin-top: 6px; }
.narrow { max-width: 520px; }

/* Sign in */
.auth { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; }
.auth-card { width: 100%; max-width: 380px; text-align: center; }
.auth .logo { width: 68px; height: 68px; border-radius: 20px; margin: 0 auto 20px; }
.auth h1 { font-size: 30px; }
.auth .sub { color: var(--text-2); margin: 6px 0 28px; }
.auth form { display: grid; gap: 12px; }
.pw { position: relative; }
.pw .input { padding-right: 52px; }
.eye {
  position: absolute; right: 6px; top: 6px; width: 36px; height: 36px; border: 0; border-radius: 50%;
  background: transparent; color: var(--text-3); cursor: pointer; display: grid; place-items: center;
  transition: color 150ms ease;
}
.eye.on { color: var(--accent); }
.auth-error {
  color: var(--red); background: var(--red-tint); border-radius: 12px; padding: 10px 14px;
  font-size: 14px; font-weight: 500; margin-bottom: 12px; animation: shake 420ms ease-out;
}
@keyframes shake { 20%, 60% { transform: translateX(-6px); } 40%, 80% { transform: translateX(6px); } }

/* ---------- Motion ---------- */
/* Ambient light that drifts very slowly behind everything */
body::before {
  content: ""; position: fixed; inset: -25%; z-index: -1; pointer-events: none;
  background:
    radial-gradient(32% 28% at 18% 12%, var(--glow-1), transparent 70%),
    radial-gradient(30% 26% at 85% 18%, var(--glow-2), transparent 70%),
    radial-gradient(36% 32% at 55% 92%, var(--glow-3), transparent 70%);
  animation: drift 48s ease-in-out infinite alternate;
}
@keyframes drift {
  0% { transform: translate3d(0, 0, 0) rotate(0deg); }
  50% { transform: translate3d(3%, 2%, 0) rotate(6deg); }
  100% { transform: translate3d(-3%, 3%, 0) rotate(-4deg); }
}
:root { --glow-1: rgba(88, 86, 214, 0.16); --glow-2: rgba(10, 132, 255, 0.12); --glow-3: rgba(52, 199, 89, 0.08); }
@media (prefers-color-scheme: dark) {
  :root { --glow-1: rgba(125, 122, 255, 0.22); --glow-2: rgba(10, 132, 255, 0.14); --glow-3: rgba(48, 209, 88, 0.08); }
}

/* Content rises into place, one surface after another */
.reveal { animation: rise 700ms var(--ease-out) backwards; animation-delay: calc(var(--i, 0) * 70ms); }
@keyframes rise { from { opacity: 0; transform: translateY(18px) scale(0.985); } }

/* Surfaces respond to the pointer with a soft spotlight */
.card, .copy { isolation: isolate; }
.card { position: relative; transition: transform 500ms var(--ease-out), box-shadow 500ms var(--ease-out); }
.card::after, .copy::after {
  content: ""; position: absolute; inset: 0; border-radius: inherit; z-index: -1; pointer-events: none;
  background: radial-gradient(420px circle at var(--mx, 50%) var(--my, 50%), var(--accent-tint), transparent 45%);
  opacity: 0; transition: opacity 300ms ease;
}
.copy { position: relative; }
@media (hover: hover) {
  .card:hover::after, .copy:hover::after { opacity: 1; }
  .card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lift); }
  .row:hover .chev { transform: translateX(3px); color: var(--text-2); }
  .row:hover .avatar { transform: scale(1.06); }
  .btn-primary:hover { box-shadow: 0 8px 22px -6px var(--accent); transform: translateY(-1px); }
}
:root { --shadow-lift: 0 2px 4px rgba(0, 0, 0, 0.04), 0 18px 40px -12px rgba(0, 0, 0, 0.14); }
@media (prefers-color-scheme: dark) { :root { --shadow-lift: 0 18px 40px -16px rgba(0, 0, 0, 0.8); } }
.chev, .avatar { transition: transform 400ms var(--spring), color 200ms ease; }

/* Running status: the whole hero breathes gently */
.hero--active { box-shadow: var(--shadow), 0 0 0 1px var(--green-tint), 0 0 40px -10px var(--green-tint); }

/* Copy: a little pop when it lands */
.copy.copied { animation: pop 450ms var(--spring); }
@keyframes pop { 40% { transform: scale(1.025); } }

/* Logo catches the light */
.logo { position: relative; overflow: hidden; }
.logo::after {
  content: ""; position: absolute; inset: -50%;
  background: linear-gradient(115deg, transparent 40%, rgba(255, 255, 255, 0.55) 50%, transparent 60%);
  transform: translateX(-100%); animation: shine 1.4s 0.3s var(--ease-out) both;
}
@keyframes shine { to { transform: translateX(100%); } }
.auth .logo { animation: float 6s ease-in-out infinite; }
@keyframes float { 50% { transform: translateY(-6px); } }

/* Submitting: the pressed button turns into a spinner */
.btn.loading { pointer-events: none; color: transparent !important; }
.btn.loading::before {
  content: ""; position: absolute; width: 18px; height: 18px; border-radius: 50%;
  border: 2.5px solid var(--spin, #fff); border-right-color: transparent;
  animation: spin 700ms linear infinite;
}
.btn-tinted, .btn-gray { --spin: var(--text); }
.btn-green { --spin: var(--green); }
.btn-red { --spin: var(--red); }
@keyframes spin { to { transform: rotate(360deg); } }

/* Numbers settle with a tiny lift as they count up */
.stat-value[data-count] { display: inline-block; }

@media (max-width: 420px) {
  h1 { font-size: 30px; }
  .card { padding: 18px 16px; border-radius: 20px; }
  .hide-sm { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 1ms !important; animation-iteration-count: 1 !important; transition-duration: 1ms !important; }
  .status--active .dot::after { display: none; }
  .btn:active, .row:active, .copy:active { transform: none; }
  body::before, .auth .logo, .logo::after { animation: none !important; }
  .card:hover, .btn-primary:hover { transform: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .nav { background: var(--bg); -webkit-backdrop-filter: none; backdrop-filter: none; }
  .toast { background: var(--surface); -webkit-backdrop-filter: none; backdrop-filter: none; }
}
@media (prefers-contrast: more) {
  :root { --separator: rgba(60, 60, 67, 0.5); --text-2: rgba(60, 60, 67, 0.9); --text-3: rgba(60, 60, 67, 0.7); }
  .card, .stat, .copy, .input { box-shadow: 0 0 0 1px var(--separator); }
}
@media (prefers-contrast: more) and (prefers-color-scheme: dark) {
  :root { --separator: rgba(235, 235, 245, 0.45); --text-2: rgba(235, 235, 245, 0.85); --text-3: rgba(235, 235, 245, 0.6); }
}
"""

JS = """
<script>
(function () {
  function copyText(text) {
    // The panel is usually served over plain http, where navigator.clipboard is unavailable.
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta);
      ok ? resolve() : reject();
    });
  }
  function dismiss(toast) {
    if (toast.dataset.gone) return;
    toast.dataset.gone = '1';
    toast.classList.add('leaving');
    setTimeout(function () { toast.remove(); }, 260);
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (btn) {
      copyText(btn.getAttribute('data-copy')).then(function () {
        btn.classList.add('copied');
        clearTimeout(btn._t);
        btn._t = setTimeout(function () { btn.classList.remove('copied'); }, 1600);
      });
      return;
    }
    var toast = e.target.closest('.toast');
    if (toast) { dismiss(toast); return; }
    var eye = e.target.closest('[data-toggle-pw]');
    if (eye) {
      var input = document.getElementById(eye.getAttribute('data-toggle-pw'));
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      eye.classList.toggle('on', show);
      eye.setAttribute('aria-pressed', show ? 'true' : 'false');
    }
  });
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Stagger surfaces in on load
  document.querySelectorAll('.page-head, .profile, .card, .auth-card').forEach(function (el, i) {
    el.classList.add('reveal');
    el.style.setProperty('--i', i);
  });

  // Count numbers up from zero
  if (!reduce) {
    document.querySelectorAll('[data-count]').forEach(function (el) {
      var end = parseInt(el.getAttribute('data-count'), 10) || 0, start = performance.now(), dur = 900;
      (function tick(now) {
        var t = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - t, 4);
        el.textContent = Math.round(end * e);
        if (t < 1) requestAnimationFrame(tick);
      })(start);
    });
  }

  // Spotlight follows the pointer across cards and links
  document.addEventListener('pointermove', function (e) {
    var el = e.target.closest && e.target.closest('.card, .copy');
    if (!el) return;
    var r = el.getBoundingClientRect();
    el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    el.style.setProperty('--my', (e.clientY - r.top) + 'px');
  }, { passive: true });

  // Divider under the nav only once content scrolls beneath it
  var nav = document.querySelector('.nav');
  if (nav) {
    var onScroll = function () { nav.classList.toggle('scrolled', window.scrollY > 4); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // The pressed submit button shows progress until the next page arrives
  document.addEventListener('submit', function (e) {
    if (e.defaultPrevented) return;
    var btn = e.submitter || e.target.querySelector('button[type=submit]');
    if (btn) btn.classList.add('loading');
  });
  // Coming back via the back button restores pages from cache: clear spinners
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('.btn.loading').forEach(function (b) { b.classList.remove('loading'); });
  });

  document.querySelectorAll('.toast').forEach(function (t, i) {
    setTimeout(function () { dismiss(t); }, 3500 + i * 400);
  });
})();
</script>
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f2f2f7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
<title>%%TITLE%%</title>
<style>%%CSS%%</style>
</head>
<body>
"""

NAV = """<nav class="nav"><div class="nav-inner">
  <a href="{{ url_for('dashboard') }}" class="brand"><span class="logo">%%logo%%</span>MTProxy</a>
  <a href="{{ url_for('logout') }}" class="nav-link">%%logout%%<span class="hide-sm">Log out</span></a>
</div></nav>
"""

NAV_BACK = """<nav class="nav"><div class="nav-inner">
  <a href="{{ url_for('dashboard') }}" class="nav-link">%%chev_left%%Overview</a>
  <span class="logo">%%logo%%</span>
</div></nav>
"""

TOASTS = """{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}
<div class="toasts" role="status" aria-live="polite">
  {% for cat, msg in messages %}
  <div class="toast toast--{{ cat }}"><span class="ti">{% if cat == 'error' %}%%x%%{% else %}%%check_sm%%{% endif %}</span><span>{{ msg }}</span></div>
  {% endfor %}
</div>
{% endif %}{% endwith %}
"""

# A tappable row that copies `value`; label/value are Jinja expressions.
def _copy_row(label, value):
    return (f'<button type="button" class="copy" data-copy="{value}" aria-label="Copy {label}">'
            f'<span class="copy-main"><span class="copy-label">{label}</span><span class="copy-text">{value}</span></span>'
            f'<span class="copy-icon"><span class="i-copy">%%copy%%</span><span class="i-check">%%check%%</span></span>'
            f'</button>')

def _page(title, body):
    html = HEAD.replace("%%TITLE%%", title) + body + "%%JS%%\n</body>\n</html>\n"
    html = html.replace("%%CSS%%", CSS).replace("%%JS%%", JS)
    for name, svg in ICONS.items():
        html = html.replace(f"%%{name}%%", svg)
    return html

# With a TLS domain the proxy runs with -D and only accepts Fake-TLS clients, whose
# secret is "ee" + secret + hex(domain); without one it serves "dd" (random padding).
LINK_SECRET = "{% set sec = ('ee' ~ c.secret ~ tls_hex) if tls_domain else ('dd' ~ c.secret) %}"
LINK_LABEL = "{{ 'Fake TLS (ee)' if tls_domain else 'Secure (dd)' }}"
LINK_TG = "tg://proxy?server={{ ip }}&port={{ port }}&secret={{ sec }}"
LINK_SHARE = "https://t.me/proxy?server={{ ip }}&port={{ port }}&secret={{ sec }}"

LOGIN_HTML = _page("Sign in · MTProxy", """
<main class="auth">
  <div class="auth-card">
    <span class="logo">%%logo_lg%%</span>
    <h1>MTProxy Panel</h1>
    <p class="sub">Sign in to manage your proxy</p>
    {% if error %}<div class="auth-error" role="alert">{{ error }}</div>{% endif %}
    <form method="POST">
      <div class="pw">
        <input class="input" id="password" type="password" name="password" placeholder="Password" required autofocus autocomplete="current-password">
        <button type="button" class="eye" data-toggle-pw="password" aria-label="Show password" aria-pressed="false">%%eye%%</button>
      </div>
      <button class="btn btn-primary btn-lg" type="submit">Sign In</button>
    </form>
    <p class="foot">Default: admin · by @ali_sudo_of</p>
  </div>
</main>
""")

DASHBOARD_HTML = _page("MTProxy Panel", NAV + TOASTS + """
<main class="page">
  <header class="page-head">
    <p class="eyebrow">MTProxy Panel</p>
    <h1>Overview</h1>
  </header>

  {% if status == 'not_installed' %}
  <section class="card narrow">
    <div class="empty">
      <div class="empty-icon">%%terminal%%</div>
      <h3>MTProxy is not installed</h3>
      <p>Run the install script on the server first, then refresh this page.</p>
    </div>
    """ + _copy_row("Install command", "bash &lt;(curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh)") + """
    <div class="stack"><a href="{{ url_for('dashboard') }}" class="btn btn-gray btn-lg">%%restart%%Refresh</a></div>
  </section>
  {% else %}
  <div class="layout">
    <div class="col">
      <section class="card{% if status == 'active' %} hero--active{% endif %}">
        <div class="hero-top">
          <span class="status status--{{ status }}"><span class="dot"></span>{{ 'Running' if status == 'active' else 'Stopped' }}</span>
          <div class="hero-actions">
            {% if status == 'active' %}
              <form method="POST" action="{{ url_for('action', act='restart') }}"><button class="btn btn-gray btn-sm" type="submit">%%restart%%Restart</button></form>
              <form method="POST" action="{{ url_for('action', act='stop') }}"><button class="btn btn-red btn-sm" type="submit">%%stop%%Stop</button></form>
            {% else %}
              <form method="POST" action="{{ url_for('action', act='start') }}"><button class="btn btn-green btn-sm" type="submit">%%play%%Start</button></form>
            {% endif %}
          </div>
        </div>
        <div class="address">
          <span class="label">Server address</span>
          <div class="address-value">{{ ip or 'Unknown IP' }}<span class="port">:{{ port }}</span></div>
        </div>
        <div class="stats">
          <div class="stat"><span class="label">Clients</span><div class="stat-value" data-count="{{ clients|length }}">{{ clients|length }}</div></div>
          {% set enabled_count = clients|selectattr('enabled')|list|length %}
          <div class="stat"><span class="label">Enabled</span><div class="stat-value" data-count="{{ enabled_count }}">{{ enabled_count }}</div></div>
          <div class="stat"><span class="label">Port</span><div class="stat-value">{{ port }}</div></div>
          <div class="stat"><span class="label">AD Tag</span>
            {% if adtag %}<div class="stat-value small" title="{{ adtag }}">{{ adtag[:8] }}…</div>{% else %}<div class="stat-value small none">Not set</div>{% endif %}
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div><h2>Clients</h2><p class="card-sub">Each client has its own secret and links.</p></div>
          <a href="{{ url_for('add_client') }}" class="btn btn-tinted btn-sm">%%plus%%New</a>
        </div>
        {% if clients %}
        <ul class="list">
          {% for c in clients %}
          <li>
            <a class="row" href="{{ url_for('client_detail', cid=c.id) }}">
              <span class="avatar" style="--h: {{ ((c.id[:2]|int(0, 16)) * 1.41)|round|int }}">{{ c.name[:1]|upper }}</span>
              <span class="row-main"><span class="row-title">{{ c.name }}</span><span class="row-sub">{{ c.secret[:10] }}…</span></span>
              {% if c.enabled %}<span class="tag tag--on">Enabled</span>{% else %}<span class="tag tag--off">Disabled</span>{% endif %}
              <span class="chev">%%chev_right%%</span>
            </a>
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <div class="empty">
          <div class="empty-icon">%%users%%</div>
          <h3>No clients yet</h3>
          <p>Create a client to get a secret and connection links you can share.</p>
          <a href="{{ url_for('add_client') }}" class="btn btn-primary">%%plus%%Create Client</a>
        </div>
        {% endif %}
      </section>
    </div>

    <div class="col">
      {% if clients %}{% set c = clients[0] %}""" + LINK_SECRET + """
      <section class="card">
        <div class="card-head"><div><h2>Quick Connect</h2><p class="card-sub">{{ c.name }} · tap a link to copy it</p></div></div>
        """ + _copy_row(LINK_LABEL, LINK_TG) + _copy_row("Share link", LINK_SHARE) + """
        <div class="stack"><a class="btn btn-primary btn-lg" href=\"""" + LINK_TG + """\">%%send%%Open in Telegram</a></div>
      </section>
      {% endif %}

      <section class="card">
        <div class="card-head"><div><h2>Settings</h2><p class="card-sub">Saving restarts the proxy.</p></div></div>
        <form method="POST" action="{{ url_for('save_settings') }}">
          <label class="field"><span class="field-label">Port</span>
            <input class="input" type="number" name="port" value="{{ port }}" min="1" max="65535" required inputmode="numeric"></label>
          <label class="field"><span class="field-label">AD Tag</span>
            <input class="input mono" type="text" name="adtag" value="{{ adtag }}" placeholder="Optional 32-char tag" autocomplete="off" spellcheck="false">
            <span class="hint">Sponsor channel tag from @MTProxybot.</span></label>
          <label class="field"><span class="field-label">Fake-TLS domain</span>
            <input class="input mono" type="text" name="tls_domain" value="{{ tls_domain }}" placeholder="Optional, e.g. www.cloudflare.com" autocomplete="off" spellcheck="false" autocapitalize="off">
            <span class="hint">Makes traffic look like HTTPS to this site. When set, only ee links work.</span></label>
          <button class="btn btn-primary btn-block" type="submit">Save &amp; Apply</button>
        </form>
      </section>

      <section class="card">
        <div class="card-head"><div><h2>Panel Password</h2></div></div>
        <form method="POST" action="{{ url_for('change_password') }}">
          <label class="field"><span class="field-label">New password</span>
            <input class="input" type="password" name="new_password" placeholder="At least 4 characters" required minlength="4" autocomplete="new-password"></label>
          <button class="btn btn-gray btn-block" type="submit">Change Password</button>
        </form>
      </section>

      <section class="card">
        <div class="card-head"><div><h2>Danger Zone</h2><p class="card-sub">Removes MTProxy, this panel and every client.</p></div></div>
        <form method="POST" action="{{ url_for('action', act='uninstall') }}" onsubmit="return confirm('Completely remove MTProxy and all clients?')">
          <button class="btn btn-red btn-block" type="submit">%%trash%%Uninstall Everything</button>
        </form>
      </section>
    </div>
  </div>
  {% endif %}
  <p class="foot">by @ali_sudo_of</p>
</main>
""")

CLIENT_HTML = _page("{{ client.name }} · MTProxy", NAV_BACK + TOASTS + """
{% set c = client %}""" + LINK_SECRET + """
<main class="page">
  <header class="profile">
    <span class="avatar" style="--h: {{ ((c.id[:2]|int(0, 16)) * 1.41)|round|int }}">{{ c.name[:1]|upper }}</span>
    <div style="min-width:0">
      <h1>{{ c.name }}</h1>
      {% if c.enabled %}<span class="tag tag--on">Enabled</span>{% else %}<span class="tag tag--off">Disabled</span>{% endif %}
    </div>
  </header>

  <div class="layout">
    <div class="col">
      <section class="card">
        <div class="card-head"><div><h2>Connection Links</h2><p class="card-sub">Tap a link to copy it.</p></div></div>
        """ + _copy_row(LINK_LABEL, LINK_TG) + _copy_row("Share link", LINK_SHARE) + """
        <div class="stack"><a class="btn btn-primary btn-lg" href=\"""" + LINK_TG + """\">%%send%%Open in Telegram</a></div>
      </section>
      <section class="card">
        <div class="card-head"><div><h2>Secret</h2></div></div>
        """ + _copy_row("Secret", "{{ c.secret }}") + """
      </section>
    </div>

    <div class="col">
      <section class="card">
        <div class="card-head"><div><h2>Edit Client</h2><p class="card-sub">Saving restarts the proxy.</p></div></div>
        <form method="POST">
          <label class="field"><span class="field-label">Name</span>
            <input class="input" type="text" name="name" value="{{ c.name }}" required></label>
          <label class="switch-row">
            <span><span>Enabled</span><span class="sub">Disabled clients can't connect.</span></span>
            <span class="switch">
              <input type="checkbox" name="enabled" value="1" role="switch" {% if c.enabled %}checked{% endif %}>
              <span class="track"></span><span class="thumb"></span>
            </span>
          </label>
          <input type="hidden" name="enabled" value="0">
          <div class="stack" style="margin-top:0">
            <button class="btn btn-primary btn-lg" type="submit">Save</button>
            <button class="btn btn-red btn-block" name="delete" value="1" type="submit" onclick="return confirm('Delete this client?')">%%trash%%Delete Client</button>
          </div>
        </form>
      </section>
    </div>
  </div>
</main>
""")

ADD_CLIENT_HTML = _page("New Client · MTProxy", NAV_BACK + TOASTS + """
<main class="page">
  <header class="page-head">
    <p class="eyebrow">Clients</p>
    <h1>New Client</h1>
  </header>
  <section class="card narrow">
    <form method="POST">
      <label class="field"><span class="field-label">Name</span>
        <input class="input" type="text" name="name" placeholder="e.g. Mobile, Friend, Work" required autofocus></label>
      <label class="field"><span class="field-label">Custom secret</span>
        <input class="input mono" type="text" name="secret" placeholder="Leave empty to generate one" pattern="[0-9a-fA-F]{0,32}" autocomplete="off" spellcheck="false">
        <span class="hint">Optional. 32 hex characters (0-9, a-f).</span></label>
      <button class="btn btn-primary btn-lg" type="submit">%%plus%%Create Client</button>
    </form>
  </section>
</main>
""")


# ==================== ROUTES ====================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == get_panel_password():
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        return render_template_string(LOGIN_HTML, error="Wrong password")
    return render_template_string(LOGIN_HTML, error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML,
        status=get_status(),
        adtag=get_adtag(),
        clients=load_clients(),
        **link_context()
    )

@app.route("/action/<act>", methods=["POST"])
@login_required
def action(act):
    if act in ("start", "restart") and not any(c.get("enabled", True) for c in load_clients()):
        flash("Enable a client first", "error")
    elif act == "start":
        ok, msg = run_cmd(f"systemctl start {SERVICE}")
        flash("Started" if ok else msg, "success" if ok else "error")
    elif act == "stop":
        ok, msg = run_cmd(f"systemctl stop {SERVICE}")
        flash("Stopped" if ok else msg, "success" if ok else "error")
    elif act == "restart":
        ok, msg = run_cmd(f"systemctl restart {SERVICE}")
        flash("Restarted" if ok else msg, "success" if ok else "error")
    elif act == "uninstall":
        run_cmd(f"systemctl stop {SERVICE} mtproxy-web mtproxy-config.timer")
        run_cmd(f"systemctl disable {SERVICE} mtproxy-web mtproxy-config.timer")
        run_cmd(f"rm -f /etc/systemd/system/{SERVICE}.service /etc/systemd/system/mtproxy-web.service"
                " /etc/systemd/system/mtproxy-config.service /etc/systemd/system/mtproxy-config.timer")
        run_cmd("systemctl daemon-reload")
        run_cmd(f"rm -rf {INSTALL_DIR} /opt/mtproxy-panel")
        run_cmd("userdel mtproxy 2>/dev/null || true")
        flash("Everything removed", "success")
    return redirect(url_for("dashboard"))

@app.route("/settings", methods=["POST"])
@login_required
def save_settings():
    port = request.form.get("port", "443").strip()
    adtag = request.form.get("adtag", "").strip()
    domain = request.form.get("tls_domain", "").strip().lower()
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        flash("Invalid port", "error")
        return redirect(url_for("dashboard"))
    if domain and not DOMAIN_RE.match(domain):
        flash("Invalid TLS domain", "error")
        return redirect(url_for("dashboard"))
    open(PORT_FILE, "w").write(port)
    open(ADTAG_FILE, "w").write(adtag)
    open(TLS_DOMAIN_FILE, "w").write(domain)
    if apply_service():
        flash("Settings applied", "success")
    else:
        flash("Settings saved. No enabled clients, so the proxy is stopped", "info")
    return redirect(url_for("dashboard"))

@app.route("/password", methods=["POST"])
@login_required
def change_password():
    new_pass = request.form.get("new_password", "").strip()
    if len(new_pass) < 4:
        flash("Min 4 characters", "error")
        return redirect(url_for("dashboard"))
    os.makedirs(INSTALL_DIR, exist_ok=True)
    open(PANEL_PASS_FILE, "w").write(new_pass)
    flash("Password changed", "success")
    return redirect(url_for("dashboard"))

@app.route("/client/add", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        name = request.form.get("name", "Client").strip()
        custom = request.form.get("secret", "").strip().lower()
        if custom and (len(custom) != 32 or any(c not in "0123456789abcdef" for c in custom)):
            flash("Secret must be 32 hex characters", "error")
            return redirect(url_for("add_client"))
        secret = custom if custom else secrets.token_hex(16)
        clients = load_clients()
        cid = secrets.token_hex(4)
        clients.append({
            "id": cid,
            "name": name,
            "secret": secret,
            "enabled": True,
            "created": datetime.now().isoformat()
        })
        save_clients(clients)
        apply_service()
        flash(f"Client '{name}' created", "success")
        return redirect(url_for("client_detail", cid=cid))
    return render_template_string(ADD_CLIENT_HTML)

@app.route("/client/<cid>", methods=["GET", "POST"])
@login_required
def client_detail(cid):
    clients = load_clients()
    client = next((c for c in clients if c["id"] == cid), None)
    if not client:
        flash("Client not found", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if request.form.get("delete"):
            clients = [c for c in clients if c["id"] != cid]
            save_clients(clients)
            if apply_service():
                flash("Client deleted", "success")
            else:
                flash("Client deleted. No enabled clients left, so the proxy is stopped", "info")
            return redirect(url_for("dashboard"))

        client["name"] = request.form.get("name", client["name"]).strip()
        client["enabled"] = request.form.get("enabled") == "1"
        save_clients(clients)
        if apply_service():
            flash("Client updated", "success")
        else:
            flash("Client updated. No enabled clients left, so the proxy is stopped", "info")
        return redirect(url_for("client_detail", cid=cid))

    return render_template_string(CLIENT_HTML,
        client=client,
        **link_context()
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8880, debug=False)
