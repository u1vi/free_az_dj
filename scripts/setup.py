"""Bootstrap the project without changing global Python or npm packages."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required.")
    npm = shutil.which("npm")
    node = shutil.which("node")
    if not npm or not node:
        raise SystemExit("Install Node.js 22.12+ (or 20.19+) with npm, then run make setup again.")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    major, minor, *_ = [int(part) for part in version.split(".")]
    if not ((major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major >= 23):
        raise SystemExit("Node.js 22.12+ (or 20.19+) is required by Vite.")
    python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    uv = shutil.which("uv")
    if not python.exists():
        command = [uv, "venv", "--python", sys.executable, str(ROOT / ".venv")] if uv else [sys.executable, "-m", "venv", str(ROOT / ".venv")]
        subprocess.run(command, check=True, cwd=ROOT)
    install = [uv, "pip", "install", "--python", str(python)] if uv else [str(python), "-m", "pip", "install"]
    subprocess.run([*install, "-e", "./backend[dev]"], cwd=ROOT, check=True)
    subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    print("\nSetup complete. Run make dev for development, or make run to open the app.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None

