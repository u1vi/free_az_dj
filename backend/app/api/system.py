"""Report installed tools without treating a missing tool as an API failure."""

import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/system", tags=["system"])


class ToolCheck(BaseModel):
    id: str
    version: str | None = None
    status: Literal["ready", "missing", "outdated", "error"]
    message: str | None = None


class SystemCheck(BaseModel):
    ready: bool
    tools: list[ToolCheck]
    # ffmpeg 7+ accepts file arguments using the -/option syntax.
    filter_graph_option: str | None


def check_binary(name: str, flag: str, minimum_major: int | None = None) -> ToolCheck:
    executable = shutil.which(name)
    if executable is None:
        return ToolCheck(id=name, status="missing", message="Not found on PATH.")
    try:
        result = subprocess.run(
            [executable, flag], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5, check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolCheck(id=name, status="error", message="Version check timed out. Try again.")
    except OSError:
        return ToolCheck(id=name, status="error", message="Could not run this tool. Check its installation.")

    if result.returncode != 0:
        return ToolCheck(id=name, status="error", message="Version check failed. Check its installation.")
    output = result.stdout or result.stderr
    match = re.search(rf"^{re.escape(name)}(?: version)?\s+(\S+)", output, re.MULTILINE)
    if not match:
        return ToolCheck(id=name, status="error", message="Could not read the installed version.")
    version = match.group(1)
    # Development builds can have a nonnumeric version; report rather than guess.
    major = re.match(r"n?(\d+)", version)
    if minimum_major and major and int(major.group(1)) < minimum_major:
        return ToolCheck(id=name, version=version, status="outdated", message=f"Version {minimum_major} or newer is required.")
    return ToolCheck(id=name, version=version, status="ready")


def check_ytdlp() -> ToolCheck:
    # Import jobs use this Python environment, not a potentially different CLI.
    try:
        version = metadata.version("yt-dlp")
    except metadata.PackageNotFoundError:
        return ToolCheck(id="yt-dlp", status="missing", message="Not installed in the app's Python environment.")
    return ToolCheck(id="yt-dlp", version=version, status="ready")


@router.get("/check", response_model=SystemCheck)
def system_check() -> SystemCheck:
    with ThreadPoolExecutor(max_workers=3) as executor:
        checks = [
            executor.submit(check_binary, "ffmpeg", "-version", 6),
            executor.submit(check_binary, "ffprobe", "-version", 6),
            executor.submit(check_binary, "deno", "--version"),
        ]
        ffmpeg, ffprobe, deno = [future.result() for future in checks]
    tools = [ffmpeg, ffprobe, check_ytdlp(), deno]
    major = re.match(r"n?(\d+)", ffmpeg.version or "")
    graph_option = None
    if ffmpeg.status == "ready":
        graph_option = "-/filter_complex" if major and int(major.group(1)) >= 7 else "-filter_complex_script"
    return SystemCheck(ready=all(tool.status == "ready" for tool in tools), tools=tools, filter_graph_option=graph_option)

