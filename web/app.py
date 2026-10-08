#!/usr/bin/env python3
# MTProxy Professional Web Panel
# by @ali_sudo_of

import os
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
SERVICE = "mtproxy"

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
    return "active" if "active" in out.strip() else "inactive"

def get_port():
    if os.path.exists(PORT_FILE):
        return open(PORT_FILE).read().strip()
    return "443"

def get_adtag():
    if os.path.exists(ADTAG_FILE):
        return open(ADTAG_FILE).read().strip()
    return ""

def get_public_ip():
    ok, out = run_cmd("curl -s --max-time 4 https://api.ipify.org || curl -s --max-time 4 https://ifconfig.me || echo ''")
    return out.strip() if ok else ""

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
    clients = [c for c in load_clients() if c.get("enabled", True)]
    if not clients:
        return False, "No clients"

    secrets_args = " ".join([f"-S {c['secret']}" for c in clients])
    adtag_arg = f" -P {adtag}" if adtag else ""

    content = f"""[Unit]
Description=Telegram MTProxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={INSTALL_DIR}
ExecStart={BINARY} -u nobody -p 8888 -H {port} {secrets_args}{adtag_arg} --aes-pwd {INSTALL_DIR}/proxy-secret {INSTALL_DIR}/proxy-multi.conf -M 1
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

# ==================== TEMPLATES ====================

BASE_CSS = """
:root {
  color-scheme: dark;
  --bg: #0b0b0f;
  --card: #14141c;
  --inset: #0e0e14;
  --ghost: #1e1e28;
  --border: #252532;
  --text: #e8e8f0;
  --muted: #8b8b9e;
  --primary: #6c5ce7;
  --primary-hover: #7f71f0;
  --link: #a29bfe;
  --success: #00b894;
  --danger: #ff6b6b;
  --warning: #fdcb6e;
  --header-bg: rgba(20, 20, 28, 0.72);
  --radius: 14px;
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --bg: #f5f5f7;
    --card: #ffffff;
    --inset: #f0f0f4;
    --ghost: #e8e8ee;
    --border: #e2e2ea;
    --text: #1d1d1f;
    --muted: #6e6e7a;
    --primary: #5b4bd6;
    --primary-hover: #4a3bc4;
    --link: #5b4bd6;
    --success: #00875f;
    --danger: #d63c3c;
    --warning: #9a6a00;
    --header-bg: rgba(255, 255, 255, 0.72);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  min-height: 100vh;
  line-height: 1.5;
  -webkit-tap-highlight-color: transparent;
}
a { color: inherit; text-decoration: none; }
h1 { letter-spacing: -0.02em; line-height: 1.2; }
h2 { letter-spacing: -0.01em; line-height: 1.3; }
:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.container { max-width: 960px; margin: 0 auto; padding: 16px; }
.header {
  background: var(--header-bg);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid var(--border);
  padding: 14px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 50;
}
.header h1 { font-size: 1.15rem; font-weight: 700; }
.header .sub { font-size: 0.75rem; color: var(--muted); }
.header a { padding: 8px 4px; transition: color 150ms ease; }
@media (hover: hover) { .header a:hover { color: var(--text) !important; } }
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}
.card h2 { font-size: 1rem; margin-bottom: 14px; font-weight: 600; }
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.badge .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.badge.active { background: rgba(0,184,148,0.15); color: var(--success); }
.badge.inactive { background: rgba(255,107,107,0.15); color: var(--danger); }
.badge.not_installed { background: rgba(253,203,110,0.15); color: var(--warning); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
.info-box {
  background: var(--inset);
  border-radius: 10px;
  padding: 12px;
}
.info-box label { display: block; font-size: 0.7rem; color: var(--muted); margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.03em; }
.info-box .val { font-family: ui-monospace, monospace; font-size: 0.9rem; word-break: break-all; }
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  touch-action: manipulation;
  transition: transform 100ms ease-out, background-color 150ms ease;
}
.btn:active { transform: scale(0.97); }
.btn-primary { background: var(--primary); color: #fff; }
@media (hover: hover) { .btn-primary:hover { background: var(--primary-hover); } }
.btn-success { background: rgba(0,184,148,0.2); color: var(--success); }
.btn-danger { background: rgba(255,107,107,0.2); color: var(--danger); }
.btn-warning { background: rgba(253,203,110,0.2); color: var(--warning); }
.btn-ghost { background: var(--ghost); color: var(--muted); }
.btn-block { width: 100%; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
input, select, textarea {
  width: 100%;
  padding: 11px 14px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--inset);
  color: var(--text);
  font-size: 1rem;
  transition: border-color 150ms ease;
}
input:focus, select:focus { outline: none; border-color: var(--primary); }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 5px; }
.flash {
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 14px;
  font-size: 0.9rem;
}
.flash.success { background: rgba(0,184,148,0.15); color: var(--success); }
.flash.error { background: rgba(255,107,107,0.15); color: var(--danger); }
.flash.info { background: rgba(108,92,231,0.15); color: #a29bfe; }
.table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.table th { text-align: left; color: var(--muted); font-weight: 500; padding: 8px 6px; border-bottom: 1px solid var(--border); font-size: 0.75rem; }
.table td { padding: 12px 6px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.table tr:last-child td { border-bottom: none; }
.link-box {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: var(--inset);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  word-break: break-all;
  color: var(--link);
  cursor: pointer;
  touch-action: manipulation;
  transition: transform 100ms ease-out, border-color 150ms ease;
}
.link-box:active { transform: scale(0.99); }
@media (hover: hover) { .link-box:hover { border-color: var(--border); } }
.link-box .link-label { display: flex; justify-content: space-between; color: var(--muted); font-size: 0.7rem; margin-bottom: 4px; font-family: system-ui; cursor: inherit; }
.link-box .copy-hint { color: var(--muted); }
.link-box.copied { border-color: var(--success); }
.link-box.copied .copy-hint { color: var(--success); }
.mobile-nav { display: none; }
@media (max-width: 640px) {
  .header h1 { font-size: 1rem; }
  .container { padding: 12px; }
  .card { padding: 16px; }
  .actions { flex-direction: column; }
  .btn { width: 100%; }
  .table { font-size: 0.8rem; }
  .hide-mobile { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
  .btn:active, .link-box:active { transform: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .header { background: var(--card); -webkit-backdrop-filter: none; backdrop-filter: none; }
}
@media (prefers-contrast: more) {
  :root { --border: #6e6e80; --muted: #b4b4c4; }
}
@media (prefers-contrast: more) and (prefers-color-scheme: light) {
  :root { --border: #8a8a96; --muted: #4a4a55; }
}
"""

COPY_JS = """
<script>
document.addEventListener('click', function (e) {
  var box = e.target.closest('.link-box');
  if (!box) return;
  var text = box.querySelector('.link-text').textContent.trim();
  var done = function () {
    var hint = box.querySelector('.copy-hint');
    box.classList.add('copied');
    hint.textContent = 'Copied';
    clearTimeout(box._t);
    box._t = setTimeout(function () {
      box.classList.remove('copied');
      hint.textContent = 'Tap to copy';
    }, 1500);
  };
  // The panel is usually served over plain http, where navigator.clipboard is unavailable.
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done);
  } else {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    if (document.execCommand('copy')) done();
    document.body.removeChild(ta);
  }
});
</script>
"""

LOGIN_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MTProxy Panel</title>
<style>{BASE_CSS}
.login-wrap {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }}
.login-card {{ width: 100%; max-width: 380px; }}
</style>
</head>
<body>
<div class="login-wrap">
  <div class="card login-card">
    <h1 style="text-align:center;margin-bottom:4px">MTProxy Panel</h1>
    <p style="text-align:center;color:var(--muted);font-size:0.85rem;margin-bottom:24px">by @ali_sudo_of</p>
    {{% if error %}}<div class="flash error">{{{{ error }}}}</div>{{% endif %}}
    <form method="POST">
      <div class="form-group">
        <input type="password" name="password" placeholder="Password" required autofocus>
      </div>
      <button class="btn btn-primary btn-block" type="submit">Login</button>
    </form>
    <p style="text-align:center;color:var(--muted);font-size:0.75rem;margin-top:18px">Default: admin</p>
  </div>
</div>
</body>
</html>
"""

DASHBOARD_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MTProxy Panel</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="header">
  <div>
    <h1>MTProxy Panel</h1>
    <div class="sub">by @ali_sudo_of</div>
  </div>
  <a href="{{{{ url_for('logout') }}}}" style="color:var(--muted);font-size:0.85rem">Logout</a>
</div>

<div class="container">
  {{% with messages = get_flashed_messages(with_categories=true) %}}
    {{% for cat, msg in messages %}}
      <div class="flash {{{{ cat }}}}">{{{{ msg }}}}</div>
    {{% endfor %}}
  {{% endwith %}}

  <!-- Status -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
      {{% if status == 'active' %}}
        <span class="badge active"><span class="dot"></span> Running</span>
      {{% elif status == 'inactive' %}}
        <span class="badge inactive"><span class="dot"></span> Stopped</span>
      {{% else %}}
        <span class="badge not_installed"><span class="dot"></span> Not Installed</span>
      {{% endif %}}
      <div class="actions" style="margin:0">
        {{% if status == 'active' %}}
          <form method="POST" action="{{{{ url_for('action', act='stop') }}}}" style="display:inline"><button class="btn btn-danger" type="submit">Stop</button></form>
          <form method="POST" action="{{{{ url_for('action', act='restart') }}}}" style="display:inline"><button class="btn btn-warning" type="submit">Restart</button></form>
        {{% elif status == 'inactive' %}}
          <form method="POST" action="{{{{ url_for('action', act='start') }}}}" style="display:inline"><button class="btn btn-success" type="submit">Start</button></form>
        {{% endif %}}
        <a href="{{{{ url_for('dashboard') }}}}" class="btn btn-ghost">Refresh</a>
      </div>
    </div>

    {{% if status != 'not_installed' %}}
    <div class="grid" style="margin-top:16px">
      <div class="info-box"><label>IP</label><div class="val">{{{{ ip or 'N/A' }}}}</div></div>
      <div class="info-box"><label>Port</label><div class="val">{{{{ port }}}}</div></div>
      <div class="info-box"><label>Clients</label><div class="val">{{{{ clients|length }}}}</div></div>
      <div class="info-box"><label>AD Tag</label><div class="val">{{{{ adtag[:12] + '...' if adtag else 'Not set' }}}}</div></div>
    </div>
    {{% endif %}}
  </div>

  {{% if status != 'not_installed' %}}
  <!-- Clients -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <h2 style="margin:0">Clients</h2>
      <a href="{{{{ url_for('add_client') }}}}" class="btn btn-primary" style="padding:8px 14px;font-size:0.8rem;width:auto">+ New Client</a>
    </div>

    {{% if clients %}}
    <div style="overflow-x:auto">
      <table class="table">
        <thead>
          <tr>
            <th>Name</th>
            <th class="hide-mobile">Secret</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {{% for c in clients %}}
          <tr>
            <td><strong>{{{{ c.name }}}}</strong></td>
            <td class="hide-mobile" style="font-family:monospace;font-size:0.8rem">{{{{ c.secret[:10] }}}}...</td>
            <td>
              {{% if c.enabled %}}
                <span style="color:var(--success);font-size:0.8rem">Enabled</span>
              {{% else %}}
                <span style="color:var(--muted);font-size:0.8rem">Disabled</span>
              {{% endif %}}
            </td>
            <td style="text-align:right">
              <a href="{{{{ url_for('client_detail', cid=c.id) }}}}" class="btn btn-ghost" style="padding:6px 10px;font-size:0.75rem">Manage</a>
            </td>
          </tr>
          {{% endfor %}}
        </tbody>
      </table>
    </div>
    {{% else %}}
      <p style="color:var(--muted)">No clients yet. Create one.</p>
    {{% endif %}}
  </div>

  <!-- Quick Links for main -->
  {{% if clients %}}
  <div class="card">
    <h2>Quick Links (first client)</h2>
    {{% set c = clients[0] %}}
    <button type="button" class="link-box">
      <span class="link-label">Simple (dd) <span class="copy-hint">Tap to copy</span></span>
      <span class="link-text">tg://proxy?server={{{{ ip }}}}&port={{{{ port }}}}&secret=dd{{{{ c.secret }}}}</span>
    </button>
    <button type="button" class="link-box">
      <span class="link-label">Fake TLS (ee) <span class="copy-hint">Tap to copy</span></span>
      <span class="link-text">tg://proxy?server={{{{ ip }}}}&port={{{{ port }}}}&secret=ee{{{{ c.secret }}}}</span>
    </button>
  </div>
  {{% endif %}}

  <!-- Settings -->
  <div class="card">
    <h2>Global Settings</h2>
    <form method="POST" action="{{{{ url_for('save_settings') }}}}">
      <div class="form-group">
        <label>Port</label>
        <input type="number" name="port" value="{{{{ port }}}}" min="1" max="65535" required>
      </div>
      <div class="form-group">
        <label>AD Tag (Sponsor Channel from @MTProxybot)</label>
        <input type="text" name="adtag" value="{{{{ adtag }}}}" placeholder="Optional 32-char tag">
      </div>
      <button class="btn btn-primary" type="submit">Save & Apply</button>
    </form>
  </div>

  <!-- Password -->
  <div class="card">
    <h2>Panel Password</h2>
    <form method="POST" action="{{{{ url_for('change_password') }}}}">
      <div class="form-group">
        <input type="password" name="new_password" placeholder="New password" required minlength="4">
      </div>
      <button class="btn btn-ghost" type="submit">Change Password</button>
    </form>
  </div>

  <!-- Danger -->
  <div class="card">
    <h2>Danger Zone</h2>
    <form method="POST" action="{{{{ url_for('action', act='uninstall') }}}}" onsubmit="return confirm('Completely remove MTProxy and all clients?')">
      <button class="btn btn-danger" type="submit">Uninstall Everything</button>
    </form>
  </div>
  {{% else %}}
  <div class="card">
    <h2>Not Installed</h2>
    <p style="color:var(--muted);margin-bottom:16px">Run the install script on the server first.</p>
    <code style="display:block;background:var(--inset);padding:12px;border-radius:10px;font-size:0.8rem">
bash &lt;(curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh)
    </code>
  </div>
  {{% endif %}}
</div>
{COPY_JS}
</body>
</html>
"""

CLIENT_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Client - MTProxy</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="header">
  <div><h1>Client</h1><div class="sub">{{{{ client.name }}}}</div></div>
  <a href="{{{{ url_for('dashboard') }}}}" style="color:var(--muted);font-size:0.85rem">← Back</a>
</div>
<div class="container">
  {{% with messages = get_flashed_messages(with_categories=true) %}}
    {{% for cat, msg in messages %}}
      <div class="flash {{{{ cat }}}}">{{{{ msg }}}}</div>
    {{% endfor %}}
  {{% endwith %}}

  <div class="card">
    <div class="info-box" style="margin-bottom:12px">
      <label>Secret</label>
      <div class="val">{{{{ client.secret }}}}</div>
    </div>
    <button type="button" class="link-box">
      <span class="link-label">Simple (dd) <span class="copy-hint">Tap to copy</span></span>
      <span class="link-text">tg://proxy?server={{{{ ip }}}}&port={{{{ port }}}}&secret=dd{{{{ client.secret }}}}</span>
    </button>
    <button type="button" class="link-box">
      <span class="link-label">Fake TLS (ee) <span class="copy-hint">Tap to copy</span></span>
      <span class="link-text">tg://proxy?server={{{{ ip }}}}&port={{{{ port }}}}&secret=ee{{{{ client.secret }}}}</span>
    </button>
    <button type="button" class="link-box">
      <span class="link-label">Share Link <span class="copy-hint">Tap to copy</span></span>
      <span class="link-text">https://t.me/proxy?server={{{{ ip }}}}&port={{{{ port }}}}&secret=dd{{{{ client.secret }}}}</span>
    </button>
  </div>

  <div class="card">
    <h2>Edit Client</h2>
    <form method="POST">
      <div class="form-group">
        <label>Name</label>
        <input type="text" name="name" value="{{{{ client.name }}}}" required>
      </div>
      <div class="form-group">
        <label>Enabled</label>
        <select name="enabled">
          <option value="1" {{% if client.enabled %}}selected{{% endif %}}>Yes</option>
          <option value="0" {{% if not client.enabled %}}selected{{% endif %}}>No</option>
        </select>
      </div>
      <div class="actions">
        <button class="btn btn-primary" type="submit">Save</button>
        <button class="btn btn-danger" name="delete" value="1" type="submit" onclick="return confirm('Delete this client?')">Delete</button>
      </div>
    </form>
  </div>
</div>
{COPY_JS}
</body>
</html>
"""

ADD_CLIENT_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>New Client</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="header">
  <div><h1>New Client</h1></div>
  <a href="{{{{ url_for('dashboard') }}}}" style="color:var(--muted);font-size:0.85rem">← Back</a>
</div>
<div class="container">
  <div class="card">
    <form method="POST">
      <div class="form-group">
        <label>Client Name</label>
        <input type="text" name="name" placeholder="e.g. Mobile, Friend, Work" required>
      </div>
      <div class="form-group">
        <label>Custom Secret (optional - leave empty to auto generate)</label>
        <input type="text" name="secret" placeholder="32 hex chars" pattern="[0-9a-fA-F]{{0,32}}">
      </div>
      <button class="btn btn-primary btn-block" type="submit">Create Client</button>
    </form>
  </div>
</div>
</body>
</html>
"""

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
        ip=get_public_ip(),
        port=get_port(),
        adtag=get_adtag(),
        clients=load_clients()
    )

@app.route("/action/<act>", methods=["POST"])
@login_required
def action(act):
    if act == "start":
        ok, msg = run_cmd(f"systemctl start {SERVICE}")
        flash("Started" if ok else msg, "success" if ok else "error")
    elif act == "stop":
        ok, msg = run_cmd(f"systemctl stop {SERVICE}")
        flash("Stopped" if ok else msg, "success" if ok else "error")
    elif act == "restart":
        ok, msg = run_cmd(f"systemctl restart {SERVICE}")
        flash("Restarted" if ok else msg, "success" if ok else "error")
    elif act == "uninstall":
        run_cmd(f"systemctl stop {SERVICE} mtproxy-web")
        run_cmd(f"systemctl disable {SERVICE} mtproxy-web")
        run_cmd(f"rm -f /etc/systemd/system/{SERVICE}.service /etc/systemd/system/mtproxy-web.service")
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
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        flash("Invalid port", "error")
        return redirect(url_for("dashboard"))
    open(PORT_FILE, "w").write(port)
    open(ADTAG_FILE, "w").write(adtag)
    ok, _ = rebuild_service()
    run_cmd(f"systemctl restart {SERVICE}")
    flash("Settings applied", "success" if ok else "error")
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
        rebuild_service()
        run_cmd(f"systemctl restart {SERVICE}")
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
            rebuild_service()
            run_cmd(f"systemctl restart {SERVICE}")
            flash("Client deleted", "success")
            return redirect(url_for("dashboard"))

        client["name"] = request.form.get("name", client["name"]).strip()
        client["enabled"] = request.form.get("enabled") == "1"
        save_clients(clients)
        rebuild_service()
        run_cmd(f"systemctl restart {SERVICE}")
        flash("Client updated", "success")
        return redirect(url_for("client_detail", cid=cid))

    return render_template_string(CLIENT_HTML,
        client=client,
        ip=get_public_ip(),
        port=get_port()
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8880, debug=False)
