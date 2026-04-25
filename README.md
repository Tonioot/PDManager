# Cloudbase

A self-hosted server management panel. Run and monitor your apps, manage nginx, SSL certificates and deployments — all from a clean web UI on your own server.

- Web dashboard on port **7823**
- Process manager with auto-restart and crash recovery
- Nginx reverse proxy management per app
- SSL certificate management
- Systemd integration for boot autostart

---

## Requirements

- Linux (Ubuntu, Debian, RHEL, Arch, openSUSE)
- Python 3.10+
- Nginx
- systemd (optional, for autostart)
- Git

---

## Installation

```bash
git clone https://github.com/your-user/cloudbase.git
cd cloudbase
sudo bash install.sh
```

The installer handles everything: system packages, Python venv, nginx, systemd service, and the `cloudbase` CLI.

Your administrator password is shown once at the end of the install. Open **http://your-server-ip:7823** to log in.

---

## Commands

```
cloudbase start            Start Cloudbase
cloudbase stop             Stop Cloudbase
cloudbase restart          Restart Cloudbase
cloudbase status           Show status
cloudbase logs             View logs
cloudbase enable           Enable boot autostart (systemd)
cloudbase disable          Disable boot autostart
cloudbase update           Pull latest changes and restart
cloudbase password         Change the administrator password
```

**Nginx**
```
cloudbase nginx <domain>   Set up nginx reverse proxy (auto-detects SSL certs)
cloudbase nginx show       Show current nginx config
cloudbase nginx disable    Remove nginx config
```

**Certificates**
```
cloudbase cert add <path>  Add a certificate to local cert store
cloudbase cert list        List stored certificates
cloudbase cert path        Show cert store location
```

**Backup & restore**
```
cloudbase export [file]    Export database + credentials to .tar.gz
cloudbase import <file>    Restore from a .tar.gz backup
```

---

## Data

All data is stored in `~/.cloudbase/`:

| File | Contents |
|---|---|
| `cloudbase.db` | All apps and configuration |
| `credentials` | Hashed admin password |
| `secret_key` | JWT signing key |
| `certs/` | Stored SSL certificates |

---

## Updating

```bash
cloudbase update
```

Or manually:
```bash
cd /path/to/cloudbase
git pull
cloudbase restart
```

---

## Backup

```bash
cloudbase export ~/backup.tar.gz
```

Restore on another server:
```bash
cloudbase import ~/backup.tar.gz
cloudbase restart
```
