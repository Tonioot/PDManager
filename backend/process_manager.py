import asyncio
import os
import signal
import subprocess
import threading
import psutil
from collections import deque
from typing import Optional

APPS_BASE_DIR = os.path.expanduser("~/.pdmanager/apps")
os.makedirs(APPS_BASE_DIR, exist_ok=True)

# Recent lines for history (capped, no tracking issues)
log_buffers: dict[int, deque] = {}

# Real-time subscribers: app_id -> list of asyncio.Queue
_log_queues: dict[int, list[asyncio.Queue]] = {}
_queues_lock = threading.Lock()

# Main event loop — set once at startup
_main_loop: Optional[asyncio.AbstractEventLoop] = None

running_processes: dict[int, subprocess.Popen] = {}


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def subscribe_logs(app_id: int) -> asyncio.Queue:
    """Create and register a queue that receives new log lines for app_id."""
    q: asyncio.Queue = asyncio.Queue()
    with _queues_lock:
        _log_queues.setdefault(app_id, []).append(q)
    return q


def unsubscribe_logs(app_id: int, q: asyncio.Queue) -> None:
    with _queues_lock:
        queues = _log_queues.get(app_id, [])
        try:
            queues.remove(q)
        except ValueError:
            pass


def _push_line(app_id: int, line: str) -> None:
    """Thread-safe: push a new log line to all subscribers."""
    if _main_loop is None or _main_loop.is_closed():
        return
    with _queues_lock:
        queues = list(_log_queues.get(app_id, []))
    for q in queues:
        _main_loop.call_soon_threadsafe(q.put_nowait, line)


def get_app_dir(app_name: str) -> str:
    return os.path.join(APPS_BASE_DIR, app_name)


def detect_app_type(app_dir: str) -> tuple[str, str, Optional[int]]:
    if os.path.exists(os.path.join(app_dir, "package.json")):
        import json
        pkg = json.load(open(os.path.join(app_dir, "package.json")))
        scripts = pkg.get("scripts", {})
        if "start" in scripts:
            cmd = "npm start"
        elif os.path.exists(os.path.join(app_dir, "index.js")):
            cmd = "node index.js"
        elif os.path.exists(os.path.join(app_dir, "server.js")):
            cmd = "node server.js"
        elif os.path.exists(os.path.join(app_dir, "app.js")):
            cmd = "node app.js"
        else:
            cmd = "npm start"
        return "nodejs", cmd, 3000

    if os.path.exists(os.path.join(app_dir, "requirements.txt")):
        for entry in ["main.py", "app.py", "server.py", "run.py", "wsgi.py"]:
            if os.path.exists(os.path.join(app_dir, entry)):
                name = entry.replace(".py", "")
                try:
                    content = open(os.path.join(app_dir, entry)).read()
                    if any(kw in content for kw in ["FastAPI", "Flask", "Starlette"]):
                        return "python", f"uvicorn {name}:app --host 0.0.0.0 --port 8000", 8000
                except Exception:
                    pass
                return "python", f"python {entry}", None
        return "python", "python main.py", None

    if os.path.exists(os.path.join(app_dir, "Gemfile")):
        return "ruby", "bundle exec ruby app.rb", 4567

    if os.path.exists(os.path.join(app_dir, "go.mod")):
        return "go", "go run .", None

    if os.path.exists(os.path.join(app_dir, "composer.json")):
        return "php", "php -S 0.0.0.0:8080", 8080

    return "unknown", "", None


def is_process_running(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def get_process_stats(pid: int) -> dict:
    try:
        proc = psutil.Process(pid)
        import time
        with proc.oneshot():
            cpu = proc.cpu_percent(interval=0.1)
            mem = proc.memory_info()
            uptime = int(time.time() - proc.create_time())
            return {
                "cpu_percent": cpu,
                "memory_mb": round(mem.rss / 1024 / 1024, 2),
                "uptime_seconds": uptime,
                "status": proc.status(),
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {}


def start_app(app_id: int, app_name: str, command: str, working_dir: str, env_vars: dict = None) -> int:
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    log_buffers[app_id] = deque(maxlen=5000)
    log_path = os.path.join(os.path.expanduser("~/.pdmanager/logs"), f"{app_name}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_file = open(log_path, "w")  # truncate: each start is a fresh session

    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=working_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    running_processes[app_id] = proc

    def _reader():
        try:
            for raw_line in iter(proc.stdout.readline, ""):
                line = raw_line.rstrip()
                log_buffers[app_id].append(line)
                log_file.write(raw_line)
                log_file.flush()
                _push_line(app_id, line)
        except Exception:
            pass
        finally:
            log_file.close()

    threading.Thread(target=_reader, daemon=True).start()
    return proc.pid


def stop_app(app_id: int, pid: int) -> bool:
    proc = running_processes.pop(app_id, None)
    if proc:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return True
        except Exception:
            pass

    if pid and is_process_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except OSError:
            pass
    return False


def get_recent_logs(app_id: int, app_name: str, lines: int = 300) -> list[str]:
    buf = log_buffers.get(app_id)
    if buf:
        return list(buf)[-lines:]

    log_path = os.path.join(os.path.expanduser("~/.pdmanager/logs"), f"{app_name}.log")
    if os.path.exists(log_path):
        with open(log_path) as f:
            all_lines = f.readlines()
        return [l.rstrip() for l in all_lines[-lines:]]
    return []
