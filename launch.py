"""Launch both local services using the current Python environment."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    for port in (8000, 8501):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f"Port {port} is occupied. Stop the existing service before launching.")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    (logs / 'launcher.pid').write_text(str(os.getpid()), encoding='ascii')
    processes, handles = [], []
    env = {**os.environ, "PYTHONUTF8": "1", "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    commands = [("backend", ["-m", "uvicorn", "copilot.api:app", "--host", "127.0.0.1", "--port", "8000"]),
                ("dashboard", ["-m", "streamlit", "run", "dashboard.py", "--server.address", "127.0.0.1",
                               "--server.port", "8501", "--server.headless", "true"])]
    try:
        for name, args in commands:
            handle = (logs / f"{name}.log").open('a', encoding='utf-8')
            handles.append(handle)
            processes.append(subprocess.Popen([sys.executable] + args, cwd=ROOT, env=env,
                                              stdout=handle, stderr=subprocess.STDOUT, creationflags=flags))
        print("Dashboard: http://127.0.0.1:8501 | API docs: http://127.0.0.1:8000/docs", flush=True)
        print("Press Ctrl+C to stop both services. Logs: logs/", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        raise SystemExit("A service exited. See logs/backend.log and logs/dashboard.log")
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == 'nt':
                    # The Windows venv redirector launches a child interpreter: stop that whole owned tree.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
                process.wait(timeout=15)
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    main()
