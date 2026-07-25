# MTProxy Panel v2.0

Complete MTProxy (Telegram Proxy) installer with **CLI Menu + Web UI** for Ubuntu.

**by @ali_sudo_of**

## Features

- Full interactive CLI menu
- **Web Panel** on port `8880` (dark modern UI)
- Support for **Sponsor Channel (AD Tag)** from `@MTProxybot`
- Default port **443**
- Start / Stop / Restart / Status / Change settings
- Auto secret generation + connection links (dd / ee)
- Systemd services for both proxy and web panel

## One-line Install

```bash
bash <(curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh)
```

After install you will see:

- Connection links
- Web Panel URL → `http://YOUR_IP:8880`
- Default password → `admin`

## Web Panel

Open `http://YOUR_SERVER_IP:8880`

Login with password `admin` (change it from the panel).

From the web panel you can:
- See live status
- Start / Stop / Restart
- Change port
- Set / change **AD Tag** (Sponsor Channel)
- View ready-to-use links
- Change panel password
- Uninstall

## AD Tag (Sponsor Channel)

1. Open Telegram and talk to **@MTProxybot**
2. Create a proxy / get your tag
3. Paste the tag in the Web Panel or during CLI install

## Manual Commands

```bash
systemctl status mtproxy
systemctl status mtproxy-web
journalctl -u mtproxy -f
```

## Uninstall

From CLI menu (option 2) or:

```bash
systemctl stop mtproxy mtproxy-web
systemctl disable mtproxy mtproxy-web
rm -f /etc/systemd/system/mtproxy.service /etc/systemd/system/mtproxy-web.service
rm -rf /opt/mtproxy /opt/mtproxy-panel
userdel mtproxy
systemctl daemon-reload
```
