#!/usr/bin/env python3
# MTProxy Web Panel - by @ali_sudo_of

import os
import subprocess
import secrets
import hashlib
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

INSTALL_DIR = "/opt/mtproxy"
BINARY = f"{INSTALL_DIR}/mtproto-proxy"
SECRET_FILE = f"{INSTALL_DIR}/secret.txt"
PORT_FILE = f"{INSTALL_DIR}/port.txt"
ADTAG_FILE = f"{INSTALL_DIR}/adtag.txt"
SERVICE = "mtproxy"
PANEL_PASS_FILE = "/opt/mtproxy/panel_pass.txt"

# Simple password (default: admin / change it)
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

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def is_installed():
    return os.path.exists(BINARY) and os.path.exists(f"/etc/systemd/system/{SERVICE}.service")

def get_status():
    if not is_installed():
        return "not_installed"
    ok, out = run_cmd(f"systemctl is-active {SERVICE}")
    return "active" if "active" in out else "inactive"

def get_port():
    if os.path.exists(PORT_FILE):
        with open(PORT_FILE) as f:
            return f.read().strip()
    return "443"

def get_secret():
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE) as f:
            return f.read().strip()
    return ""

def get_adtag():
    if os.path.exists(ADTAG_FILE):
        with open(ADTAG_FILE) as f:
            return f.read().strip()
    return ""

def get_public_ip():
    ok, out = run_cmd("curl -s --max-time 4 https://api.ipify.org || curl -s --max-time 4 https://ifconfig.me || echo ''")
    return out.strip() if ok else ""

def rebuild_service(port, secret, adtag=""):
    """Recreate systemd service with current settings"""
    adtag_arg = f" -P {adtag}" if adtag else ""
    # Always run as root for reliability on port 443
    service_content = f"""[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={INSTALL_DIR}
ExecStart={BINARY} -u nobody -p 8888 -H {port} -S {secret}{adtag_arg} --aes-pwd {INSTALL_DIR}/proxy-secret {INSTALL_DIR}/proxy-multi.conf -M 1
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    with open(f"/etc/systemd/system/{SERVICE}.service", "w") as f:
        f.write(service_content)
    run_cmd("systemctl daemon-reload")
    run_cmd(f"systemctl enable {SERVICE}")

# ==================== HTML Templates ====================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTProxy Panel - Login</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0f0f13; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .card { background: #1a1a22; border: 1px solid #2a2a35; border-radius: 16px; padding: 40px; width: 100%; max-width: 380px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
        h1 { text-align: center; margin-bottom: 8px; font-size: 1.6rem; color: #fff; }
        .sub { text-align: center; color: #888; margin-bottom: 30px; font-size: 0.9rem; }
        input { width: 100%; padding: 14px 16px; border-radius: 10px; border: 1px solid #333; background: #121218; color: #fff; font-size: 1rem; margin-bottom: 16px; }
        input:focus { outline: none; border-color: #5b5bff; }
        button { width: 100%; padding: 14px; border: none; border-radius: 10px; background: linear-gradient(135deg, #5b5bff, #7b5bff); color: white; font-size: 1rem; font-weight: 600; cursor: pointer; }
        button:hover { opacity: 0.9; }
        .error { background: #3a1a1a; color: #ff6b6b; padding: 12px; border-radius: 8px; margin-bottom: 16px; text-align: center; font-size: 0.9rem; }
        .footer { text-align: center; margin-top: 24px; color: #555; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="card">
        <h1>MTProxy Panel</h1>
        <div class="sub">by @ali_sudo_of</div>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Password" required autofocus>
            <button type="submit">Login</button>
        </form>
        <div class="footer">Default password: admin</div>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTProxy Panel</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0f0f13; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }
        .header { background: #1a1a22; border-bottom: 1px solid #2a2a35; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 1.3rem; color: #fff; }
        .header .brand { color: #888; font-size: 0.85rem; }
        .container { max-width: 900px; margin: 0 auto; padding: 24px; }
        .status-card { background: #1a1a22; border: 1px solid #2a2a35; border-radius: 14px; padding: 24px; margin-bottom: 20px; }
        .status-row { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 16px; }
        .badge { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 20px; font-size: 0.9rem; font-weight: 600; }
        .badge.active { background: #14301f; color: #3dd68c; }
        .badge.inactive { background: #301414; color: #ff6b6b; }
        .badge.not_installed { background: #302814; color: #ffb84d; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 16px; }
        .info-item { background: #121218; padding: 12px 16px; border-radius: 10px; }
        .info-item label { display: block; color: #888; font-size: 0.75rem; margin-bottom: 4px; }
        .info-item value { font-family: monospace; font-size: 0.95rem; word-break: break-all; }
        .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
        .btn { padding: 10px 18px; border: none; border-radius: 10px; font-size: 0.9rem; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
        .btn-green { background: #1a3a2a; color: #3dd68c; }
        .btn-red { background: #3a1a1a; color: #ff6b6b; }
        .btn-blue { background: #1a1a3a; color: #7b8cff; }
        .btn-orange { background: #3a2a1a; color: #ffb84d; }
        .btn-gray { background: #2a2a35; color: #ccc; }
        .btn:hover { opacity: 0.85; }
        .section { background: #1a1a22; border: 1px solid #2a2a35; border-radius: 14px; padding: 24px; margin-bottom: 20px; }
        .section h2 { font-size: 1.1rem; margin-bottom: 16px; color: #fff; }
        .form-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        input, select { flex: 1; min-width: 160px; padding: 12px 14px; border-radius: 10px; border: 1px solid #333; background: #121218; color: #fff; font-size: 0.95rem; }
        input:focus { outline: none; border-color: #5b5bff; }
        .links { background: #121218; border-radius: 10px; padding: 16px; margin-top: 12px; }
        .link-item { margin-bottom: 12px; }
        .link-item label { display: block; color: #888; font-size: 0.8rem; margin-bottom: 4px; }
        .link-item code { display: block; background: #0a0a0e; padding: 10px; border-radius: 8px; font-size: 0.85rem; word-break: break-all; color: #7b8cff; }
        .flash { padding: 12px 16px; border-radius: 10px; margin-bottom: 16px; }
        .flash.success { background: #14301f; color: #3dd68c; }
        .flash.error { background: #301414; color: #ff6b6b; }
        .flash.info { background: #1a1a3a; color: #7b8cff; }
        .logout { color: #888; text-decoration: none; font-size: 0.9rem; }
        .logout:hover { color: #fff; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>MTProxy Panel</h1>
            <div class="brand">by @ali_sudo_of</div>
        </div>
        <a href="{{ url_for('logout') }}" class="logout">Logout</a>
    </div>

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
                <div class="flash {{ category }}">{{ message }}</div>
            {% endfor %}
        {% endwith %}

        <div class="status-card">
            <div class="status-row">
                {% if status == 'active' %}
                    <span class="badge active"><span class="dot"></span> Running</span>
                {% elif status == 'inactive' %}
                    <span class="badge inactive"><span class="dot"></span> Stopped</span>
                {% else %}
                    <span class="badge not_installed"><span class="dot"></span> Not Installed</span>
                {% endif %}
            </div>

            {% if status != 'not_installed' %}
            <div class="info-grid">
                <div class="info-item">
                    <label>Server IP</label>
                    <value>{{ ip or 'N/A' }}</value>
                </div>
                <div class="info-item">
                    <label>Port</label>
                    <value>{{ port }}</value>
                </div>
                <div class="info-item">
                    <label>Secret</label>
                    <value>{{ secret[:16] }}...</value>
                </div>
                <div class="info-item">
                    <label>AD Tag (Sponsor)</label>
                    <value>{{ adtag or 'Not set' }}</value>
                </div>
            </div>

            <div class="actions">
                {% if status == 'active' %}
                    <form method="POST" action="{{ url_for('action', act='stop') }}" style="display:inline">
                        <button class="btn btn-red" type="submit">Stop</button>
                    </form>
                    <form method="POST" action="{{ url_for('action', act='restart') }}" style="display:inline">
                        <button class="btn btn-orange" type="submit">Restart</button>
                    </form>
                {% else %}
                    <form method="POST" action="{{ url_for('action', act='start') }}" style="display:inline">
                        <button class="btn btn-green" type="submit">Start</button>
                    </form>
                {% endif %}
                <a href="{{ url_for('dashboard') }}" class="btn btn-gray">Refresh</a>
            </div>
            {% endif %}
        </div>

        {% if status != 'not_installed' %}
        <div class="section">
            <h2>Connection Links</h2>
            <div class="links">
                <div class="link-item">
                    <label>Simple (dd) - Recommended</label>
                    <code>tg://proxy?server={{ ip }}&port={{ port }}&secret=dd{{ secret }}</code>
                </div>
                <div class="link-item">
                    <label>Fake TLS (ee)</label>
                    <code>tg://proxy?server={{ ip }}&port={{ port }}&secret=ee{{ secret }}</code>
                </div>
                <div class="link-item">
                    <label>HTTPS Share Link</label>
                    <code>https://t.me/proxy?server={{ ip }}&port={{ port }}&secret=dd{{ secret }}</code>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Settings</h2>
            <form method="POST" action="{{ url_for('save_settings') }}">
                <div class="form-row">
                    <input type="number" name="port" value="{{ port }}" placeholder="Port" min="1" max="65535" required>
                    <input type="text" name="adtag" value="{{ adtag }}" placeholder="AD Tag (from @MTProxybot) - optional">
                </div>
                <div class="form-row">
                    <button class="btn btn-blue" type="submit">Save & Restart</button>
                </div>
            </form>
            <p style="color:#888;font-size:0.85rem;margin-top:12px;">
                Get your AD Tag from Telegram bot <b>@MTProxybot</b> → create proxy → get the tag.
            </p>
        </div>

        <div class="section">
            <h2>Danger Zone</h2>
            <form method="POST" action="{{ url_for('action', act='uninstall') }}" onsubmit="return confirm('Are you sure? This will completely remove MTProxy.')">
                <button class="btn btn-red" type="submit">Uninstall MTProxy</button>
            </form>
        </div>
        {% else %}
        <div class="section">
            <h2>Install MTProxy</h2>
            <p style="color:#aaa;margin-bottom:16px;">MTProxy is not installed on this server.</p>
            <form method="POST" action="{{ url_for('action', act='install') }}">
                <div class="form-row">
                    <input type="number" name="port" value="443" placeholder="Port" min="1" max="65535">
                    <input type="text" name="adtag" placeholder="AD Tag (optional)">
                </div>
                <button class="btn btn-green" type="submit">Install MTProxy</button>
            </form>
        </div>
        {% endif %}

        <div class="section">
            <h2>Change Panel Password</h2>
            <form method="POST" action="{{ url_for('change_password') }}">
                <div class="form-row">
                    <input type="password" name="new_password" placeholder="New password" required>
                    <button class="btn btn-blue" type="submit">Change Password</button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
"""

# ==================== Routes ====================

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
    status = get_status()
    return render_template_string(DASHBOARD_HTML,
        status=status,
        ip=get_public_ip(),
        port=get_port(),
        secret=get_secret(),
        adtag=get_adtag()
    )

@app.route("/action/<act>", methods=["POST"])
@login_required
def action(act):
    if act == "start":
        ok, msg = run_cmd(f"systemctl start {SERVICE}")
        flash("Service started" if ok else f"Failed: {msg}", "success" if ok else "error")
    elif act == "stop":
        ok, msg = run_cmd(f"systemctl stop {SERVICE}")
        flash("Service stopped" if ok else f"Failed: {msg}", "success" if ok else "error")
    elif act == "restart":
        ok, msg = run_cmd(f"systemctl restart {SERVICE}")
        flash("Service restarted" if ok else f"Failed: {msg}", "success" if ok else "error")
    elif act == "uninstall":
        run_cmd(f"systemctl stop {SERVICE}")
        run_cmd(f"systemctl disable {SERVICE}")
        run_cmd(f"rm -f /etc/systemd/system/{SERVICE}.service")
        run_cmd("systemctl daemon-reload")
        run_cmd(f"rm -rf {INSTALL_DIR}")
        run_cmd("userdel mtproxy 2>/dev/null || true")
        flash("MTProxy completely removed", "success")
    elif act == "install":
        port = request.form.get("port", "443")
        adtag = request.form.get("adtag", "").strip()
        # Call the main installer logic via shell for simplicity
        flash("Please use the main install script for first-time installation. Web install coming in next update.", "info")
    return redirect(url_for("dashboard"))

@app.route("/settings", methods=["POST"])
@login_required
def save_settings():
    port = request.form.get("port", "443").strip()
    adtag = request.form.get("adtag", "").strip()

    if not port.isdigit() or not (1 <= int(port) <= 65535):
        flash("Invalid port", "error")
        return redirect(url_for("dashboard"))

    secret = get_secret()
    if not secret:
        flash("Secret not found", "error")
        return redirect(url_for("dashboard"))

    with open(PORT_FILE, "w") as f:
        f.write(port)
    with open(ADTAG_FILE, "w") as f:
        f.write(adtag)

    rebuild_service(port, secret, adtag)
    run_cmd(f"systemctl restart {SERVICE}")
    flash("Settings saved and service restarted", "success")
    return redirect(url_for("dashboard"))

@app.route("/password", methods=["POST"])
@login_required
def change_password():
    new_pass = request.form.get("new_password", "").strip()
    if len(new_pass) < 4:
        flash("Password too short (min 4 chars)", "error")
        return redirect(url_for("dashboard"))
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(PANEL_PASS_FILE, "w") as f:
        f.write(new_pass)
    flash("Panel password changed", "success")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    # Run on all interfaces, port 8880
    app.run(host="0.0.0.0", port=8880, debug=False)
