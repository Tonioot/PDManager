# Linux Quick Start

Gebruik deze flow op een Linux-server om Cloudbase in een paar commando's te installeren.

## 1. Clone de repo

```bash
git clone <jouw-repo-url> cloudbase
cd cloudbase
chmod +x install.sh start.sh dev.sh
```

## 2. Alles in een keer installeren

```bash
./install.sh
```

Dit doet het volgende:

- installeert Python, pip, venv en lsof als ze ontbreken
- installeert nginx
- zet de Python-omgeving op in `backend/venv`
- maakt `~/.pdmanager` aan als compatibele datafolder
- installeert een systemd service `cloudbase`
- installeert het commando `cloudbase` in `/usr/local/bin`
- zet Cloudbase direct aan als boot service

## 3. De service gebruiken

```bash
cloudbase up
cloudbase status
```

Handige extra commands:

```bash
cloudbase logs
cloudbase enable
cloudbase disable
cloudbase restart
```

## 4. Open de app

```text
http://<jouw-server-ip>:7823
```

## Update flow

```bash
git pull
./install.sh
cloudbase restart
```

Voor alle CLI-commando's, zie [CLI_COMMANDS.md](CLI_COMMANDS.md).