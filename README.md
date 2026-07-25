# MTProxy Panel v2.1 Professional

by **@ali_sudo_of**

Full-featured MTProxy manager for Ubuntu with modern **Web UI** + multi-client support.

## Features

- Beautiful responsive Web Panel (Mobile + Desktop)
- **Multi-Client** system (create unlimited clients with separate secrets)
- AD Tag / Sponsor Channel support (`@MTProxybot`)
- Auto rebuild & update (no questions if already installed)
- Default port 443
- Start / Stop / Restart / Links / Settings from web
- Dark professional UI

## Install / Update (one command)

```bash
bash <(curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh)
```

- If already installed → automatically rebuilds & updates without asking
- Fresh install → asks port + optional AD Tag

## After Install

- Web Panel: `http://YOUR_IP:8880`
- Default password: `admin`

From the panel you can:
- Create new clients (each gets its own secret + links)
- Enable / Disable clients
- Change port & AD Tag
- View all connection links
- Change panel password

## AD Tag (Sponsor)

1. Talk to [@MTProxybot](https://t.me/MTProxybot) on Telegram
2. Get your tag
3. Paste it in Web Panel → Global Settings

## Uninstall

From Web Panel (Danger Zone) or:

```bash
systemctl stop mtproxy mtproxy-web
rm -rf /opt/mtproxy /opt/mtproxy-panel
rm -f /etc/systemd/system/mtproxy*.service
systemctl daemon-reload
```
