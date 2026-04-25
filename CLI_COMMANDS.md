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

## Core Commands

```bash
cloudbase up
```

Start Cloudbase handmatig.

```bash
cloudbase down
```

Stopt de systemd service.

```bash
cloudbase restart
```

Herstart de systemd service.

```bash
cloudbase status
```

Toont de huidige status van Cloudbase.

```bash
cloudbase logs
```

Toont de laatste logs van de systemd service.

## Autostart

```bash
cloudbase enable
```

Schrijft of ververst de systemd unit, doet een daemon reload en zet boot autostart direct aan.

```bash
cloudbase disable
```

Zet boot autostart uit en stopt de service.

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

Na een update:

```bash
git pull
./install.sh
cloudbase restart
```

Logs bekijken:

```bash
cloudbase logs
```