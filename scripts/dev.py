"""Run both loopback-only dev servers and clean them up together."""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm is missing. Install Node.js and run make setup.")
    processes: list[subprocess.Popen] = []

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload", "--reload-dir", "app"],
            cwd=ROOT / "backend", start_new_session=os.name == "posix",
        ))
        processes.append(subprocess.Popen(
            [npm, "run", "dev"], cwd=ROOT / "frontend", start_new_session=os.name == "posix",
        ))
        while all(process.poll() is None for process in processes):
            time.sleep(0.2)
        print("A development server stopped; shutting down both servers.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
