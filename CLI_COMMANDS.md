# Cloudbase CLI Commands

Deze documentatie beschrijft de Linux CLI voor Cloudbase.

## Install

```bash
./install.sh
```

Dit installeert standaard:

- systeemafhankelijkheden
- nginx
- Python virtual environment
- `/usr/local/bin/cloudbase`
- `cloudbase.service` met boot autostart
- lokale cert-opslag in `~/.pdmanager/certs`

## Core Commands

```bash
cloudbase start
```

Start Cloudbase. Als de systemd service bestaat, start dit de service. Zonder service start het direct lokaal.

```bash
cloudbase stop
```

Stopt Cloudbase. Als er geen systemd service bestaat, stopt dit het lokale proces op poort `7823`.

```bash
cloudbase restart
```

Herstart Cloudbase.

```bash
cloudbase status
```

Toont de huidige status van Cloudbase.

```bash
cloudbase logs
```

Toont de laatste service- of CLI-logs.

## Autostart

```bash
cloudbase enable
```

Schrijft of ververst de systemd unit, doet een daemon reload en zet boot autostart direct aan.

```bash
cloudbase disable
```

Zet boot autostart uit en stopt de service.

## Local Nginx Setup

Dit werkt ook als je Cloudbase niet via de webinterface of localhost wilt configureren.

```bash
cloudbase nginx setup panel.example.com
```

Maakt een lokale HTTP nginx-config voor Cloudbase.

```bash
cloudbase nginx setup panel.example.com fullchain.pem privkey.pem
```

Maakt een lokale HTTPS nginx-config voor Cloudbase. De cert- en keypaden mogen absolute paden zijn of bestandsnamen uit `~/.pdmanager/certs`.

```bash
cloudbase nginx show
cloudbase nginx disable
```

Toont of verwijdert de lokale Cloudbase nginx-config.

## Local Certificate Commands

```bash
cloudbase cert add /path/to/fullchain.pem
cloudbase cert add /path/to/privkey.pem
```

Kopieert certificaten naar de lokale Cloudbase cert-map.

```bash
cloudbase cert list
cloudbase cert path
```

Toont de beschikbare lokale certs of het storage-pad.

## Compatibility Aliases

```bash
cloudbase up
cloudbase down
```

Dit zijn aliassen voor `cloudbase start` en `cloudbase stop`.

## Help

```bash
cloudbase help
```

Toont de beschikbare commando's.

## Typical Flows

Eerste installatie:

```bash
git clone <jouw-repo-url> cloudbase
cd cloudbase
chmod +x install.sh start.sh dev.sh
./install.sh
cloudbase status
```

Nginx en certs lokaal instellen:

```bash
cloudbase cert add /etc/letsencrypt/live/panel/fullchain.pem
cloudbase cert add /etc/letsencrypt/live/panel/privkey.pem
cloudbase nginx setup panel.example.com fullchain.pem privkey.pem
```

Na een update:

```bash
git pull
./install.sh
cloudbase restart
```
