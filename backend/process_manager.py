import asyncio
import json
import os
import signal
import subprocess
import threading
import time
import psutil
from collections import deque
from typing import Optional

APPS_BASE_DIR = os.path.expanduser("~/.pdmanager/apps")
REGISTRY_PATH = os.path.expanduser("~/.pdmanager/pid_registry.json")
os.makedirs(APPS_BASE_DIR, exist_ok=True)

# Recent lines for history (capped, no tracking issues)
log_buffers: dict[int, deque] = {}

# Real-time subscribers: app_id -> list of asyncio.Queue
_log_queues: dict[int, list[asyncio.Queue]] = {}
_queues_lock = threading.Lock()

# Main event loop — set once at startup
_main_loop: Optional[asyncio.AbstractEventLoop] = None

running_processes: dict[int, subprocess.Popen] = {}

# Persistent PID registry: {app_id: {pid, shell_pid, create_time}}
# Survives PDManager restarts so we can recover orphaned processes
_pid_registry: dict[int, dict] = {}

# Stats history: last 60 snapshots per app (~2 min at 2s interval)
_stats_history: dict[int, deque] = {}
_stats_queues: dict[int, list[asyncio.Queue]] = {}
_stats_queues_lock = threading.Lock()


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def subscribe_stats(app_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    with _stats_queues_lock:
        _stats_queues.setdefault(app_id, []).append(q)
    return q


def unsubscribe_stats(app_id: int, q: asyncio.Queue) -> None:
    with _stats_queues_lock:
        queues = _stats_queues.get(app_id, [])
        try:
            queues.remove(q)
        except ValueError:
            pass


def _push_stat(app_id: int, data: dict) -> None:
    if _main_loop is None or _main_loop.is_closed():
        return
    with _stats_queues_lock:
        queues = list(_stats_queues.get(app_id, []))
    for q in queues:
        _main_loop.call_soon_threadsafe(q.put_nowait, data)


def get_recent_stats(app_id: int) -> list[dict]:
    return list(_stats_history.get(app_id, []))


def load_registry() -> None:
    global _pid_registry
    try:
        with open(REGISTRY_PATH) as f:
            _pid_registry = {int(k): v for k, v in json.load(f).items()}
    except Exception:
        _pid_registry = {}


def _save_registry() -> None:
    try:
        with open(REGISTRY_PATH, "w") as f:
            json.dump(_pid_registry, f)
    except Exception:
        pass


def subscribe_logs(app_id: int) -> asyncio.Queue:
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
    if _main_loop is None or _main_loop.is_closed():
        return
    with _queues_lock:
        queues = list(_log_queues.get(app_id, []))
    for q in queues:
        _main_loop.call_soon_threadsafe(q.put_nowait, line)


def _safe_dir_name(name: str) -> str:
    """Strip/replace characters that are invalid or problematic in file paths."""
    import re
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)


def get_app_dir(app_name: str) -> str:
    return os.path.join(APPS_BASE_DIR, _safe_dir_name(app_name))


def detect_app_type_from_command(cmd: str) -> str:
    """Infer app type from the start command."""
    cmd = cmd.strip().lower()
    if cmd.startswith("node ") or "npm " in cmd or cmd == "npm start" or cmd.startswith("npx "):
        return "nodejs"
    if cmd.startswith("python") or cmd.startswith("uvicorn") or cmd.startswith("gunicorn") or cmd.startswith("flask"):
        return "python"
    if cmd.startswith("ruby") or cmd.startswith("bundle exec ruby") or cmd.startswith("rails"):
        return "ruby"
    if cmd.startswith("go run") or cmd.startswith("go build") or cmd.startswith("./ "):
        return "go"
    if cmd.startswith("php") or cmd.startswith("composer"):
        return "php"
    if cmd.startswith("java") or cmd.startswith("mvn") or cmd.startswith("gradle"):
        return "java"
    if cmd.startswith("dotnet") or cmd.endswith(".exe"):
        return "dotnet"
    return "unknown"


def detect_app_type(app_dir: str) -> tuple[str, str, Optional[int]]:
    if os.path.exists(os.path.join(app_dir, "package.json")):
        import json as _json
        pkg = _json.load(open(os.path.join(app_dir, "package.json")))
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


def _pid_alive(pid: int, expected_create_time: Optional[float] = None) -> bool:
    """Check if a PID is alive, optionally verifying it's the same process."""
    try:
        proc = psutil.Process(pid)
        if not (proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE):
            return False
        if expected_create_time is not None:
            if abs(proc.create_time() - expected_create_time) > 2.0:
                return False  # PID was reused by a different process
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def is_process_running(pid: int, app_id: Optional[int] = None) -> bool:
    reg = _pid_registry.get(app_id) if app_id is not None else None
    create_time = reg.get("create_time") if reg else None

    if _pid_alive(pid, create_time):
        return True

    # Fallback: if we know the shell PID, check if its children are alive
    if reg:
        shell_pid = reg.get("shell_pid")
        if shell_pid and shell_pid != pid:
            try:
                children = psutil.Process(shell_pid).children(recursive=True)
                if any(c.is_running() for c in children):
                    return True
            except Exception:
                pass

    return False


def find_process_by_port(port: int) -> Optional[int]:
    """Find PID of process listening on a given port (port-based recovery)."""
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                return conn.pid
    except Exception:
        pass
    return None


def get_process_stats(pid: int) -> dict:
    try:
        proc = psutil.Process(pid)
        # cpu_percent must be called outside oneshot(); interval=0.5 gives a real measurement
        cpu = proc.cpu_percent(interval=0.5)
        mem = proc.memory_info()
        uptime = int(time.time() - proc.create_time())

        try:
            num_threads = proc.num_threads()
        except Exception:
            num_threads = 0

        try:
            conns = proc.connections() if hasattr(proc, 'connections') else proc.net_connections()
            num_connections = len(conns)
        except Exception:
            num_connections = 0

        return {
            "cpu_percent": cpu,
            "memory_mb": round(mem.rss / 1024 / 1024, 2),
            "memory_vms_mb": round(mem.vms / 1024 / 1024, 2),
            "uptime_seconds": uptime,
            "status": proc.status(),
            "num_threads": num_threads,
            "num_connections": num_connections,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {}


def get_log_path(app_name: str) -> str:
    return os.path.join(os.path.expanduser("~/.pdmanager/logs"), f"{_safe_dir_name(app_name)}.log")


def attach_log_tailer(
    app_id: int,
    app_name: str,
    proc: Optional[subprocess.Popen] = None,
    seek_to_end: bool = False,
) -> None:
    """Tail a log file and push new lines to log_buffers / subscribers.

    Uses the log file directly so the child process is not coupled to
    pdmanager via a pipe — pdmanager restarts no longer send SIGPIPE to apps.
    """
    log_path = get_log_path(app_name)

    def _reader():
        try:
            # Wait briefly if the file hasn't been created yet (fast start)
            for _ in range(20):
                if os.path.exists(log_path):
                    break
                time.sleep(0.05)
            else:
                return

            with open(log_path, "r") as f:
                if seek_to_end:
                    f.seek(0, 2)
                while True:
                    raw_line = f.readline()
                    if raw_line:
                        line = raw_line.rstrip()
                        log_buffers[app_id].append(line)
                        _push_line(app_id, line)
                    else:
                        # Determine whether the process is still alive
                        if proc is not None:
                            if proc.poll() is not None:
                                # Read any last bytes the OS may have buffered
                                for raw in f:
                                    l = raw.rstrip()
                                    log_buffers[app_id].append(l)
                                    _push_line(app_id, l)
                                break
                        else:
                            reg = _pid_registry.get(app_id)
                            if not reg:
                                break
                            pid = reg.get("pid")
                            ct  = reg.get("create_time")
                            if pid and not _pid_alive(pid, ct):
                                for raw in f:
                                    l = raw.rstrip()
                                    log_buffers[app_id].append(l)
                                    _push_line(app_id, l)
                                break
                        time.sleep(0.05)
        except Exception:
            pass

    threading.Thread(target=_reader, daemon=True).start()


def start_app(app_id: int, app_name: str, command: str, working_dir: str, env_vars: dict = None) -> int:
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    log_buffers[app_id] = deque(maxlen=5000)
    _stats_history.pop(app_id, None)  # fresh process = fresh history
    log_path = get_log_path(app_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    # Open for writing; pass the fd directly so the child owns it.
    # No pipe means pdmanager restarts never send SIGPIPE to the child.
    log_file = open(log_path, "w")

    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=working_dir,
        env=env,
        stdout=log_file,
        stderr=log_file,
        # New session so we can kill the whole process group cleanly
        start_new_session=True,
    )
    # Parent no longer needs the fd; child has its own copy
    log_file.close()

    running_processes[app_id] = proc
    shell_pid = proc.pid

    # Find the actual app PID (child of shell) after a brief moment
    actual_pid = shell_pid
    try:
        time.sleep(0.25)
        children = psutil.Process(shell_pid).children(recursive=True)
        if children:
            actual_pid = children[-1].pid
    except Exception:
        pass

    # Persist to registry for recovery after PDManager restarts
    try:
        create_time = psutil.Process(actual_pid).create_time()
        _pid_registry[app_id] = {
            "pid": actual_pid,
            "shell_pid": shell_pid,
            "create_time": create_time,
        }
        _save_registry()
    except Exception:
        _pid_registry[app_id] = {"pid": actual_pid, "shell_pid": shell_pid}
        _save_registry()

    attach_log_tailer(app_id, app_name, proc=proc, seek_to_end=False)
    return actual_pid


def stop_app(app_id: int, pid: int) -> bool:
    proc = running_processes.pop(app_id, None)
    reg  = _pid_registry.pop(app_id, {})
    _save_registry()

    killed = False

    # Kill entire process group (shell + all children)
    shell_pid = reg.get("shell_pid") or (proc.pid if proc else None)
    if shell_pid:
        try:
            os.killpg(os.getpgid(shell_pid), signal.SIGTERM)
            killed = True
        except Exception:
            pass

    # Also terminate via Popen object
    if proc:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            killed = True
        except Exception:
            pass

    # Kill by actual PID and its children
    for target_pid in {pid, reg.get("pid")} - {None}:
        if target_pid and _pid_alive(target_pid):
            try:
                parent = psutil.Process(target_pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except Exception:
                        pass
                parent.terminate()
                killed = True
            except Exception:
                pass

    return killed


def get_recent_logs(app_id: int, app_name: str, lines: int = 300) -> list[str]:
    buf = log_buffers.get(app_id)
    if buf:
        return list(buf)[-lines:]

    log_path = os.path.join(os.path.expanduser("~/.pdmanager/logs"), f"{_safe_dir_name(app_name)}.log")
    if os.path.exists(log_path):
        with open(log_path) as f:
            all_lines = f.readlines()
        return [l.rstrip() for l in all_lines[-lines:]]
    return []
