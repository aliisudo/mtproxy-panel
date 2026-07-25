# MTProxy Panel

Complete interactive MTProxy (Telegram Proxy) installer and management panel for Ubuntu.

**by @ali_sudo_of**

## Features

- Full interactive menu UI
- Automatic build from official source (with modern compiler fixes)
- Systemd service
- Auto secret generation
- Connection links (`tg://` and `https://t.me/proxy`)
- Default port **443** (works perfectly on root servers)
- Start / Stop / Restart / Status / Uninstall / Change port
- Update Telegram configs with one click
- Automatic firewall (UFW) handling

## Supported Systems

- Ubuntu 20.04 / 22.04 / 24.04
- Debian 11 / 12

## One-line Install

Run as **root**:

```bash
bash <(curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh)
```

## After Install

Use option **7** to get ready-to-use connection links.

- **dd** secret → Simple (recommended for most users)
- **ee** secret → Fake TLS (better against DPI)

## Manual Management

```bash
systemctl status mtproxy
systemctl start mtproxy
systemctl stop mtproxy
systemctl restart mtproxy
journalctl -u mtproxy -f
```

Important paths:
- Binary & configs: `/opt/mtproxy/`
- Secret: `/opt/mtproxy/secret.txt`
- Port: `/opt/mtproxy/port.txt`

## Uninstall

From the menu (option 2) or:

```bash
systemctl stop mtproxy
systemctl disable mtproxy
rm -f /etc/systemd/system/mtproxy.service
rm -rf /opt/mtproxy
userdel mtproxy
systemctl daemon-reload
```
