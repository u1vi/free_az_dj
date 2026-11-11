import json
import math
import re
import subprocess
from pathlib import Path

from .ffprobe import AudioError


def measure(path: Path, duration: float) -> tuple[float | None, float | None]:
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=max(60, duration * 2),
    )
    try:
        if result.returncode:
            raise ValueError
        data = json.loads(re.findall(r"\{[^{}]+\}", result.stderr)[-1])

        def finite(key: str) -> float | None:
            number = float(data[key])
            return number if math.isfinite(number) else None

        return finite("input_i"), finite("input_tp")
    except (ValueError, KeyError, IndexError):
        raise AudioError("Could not analyse the volume of this file. Try importing it again.") from None


def suggest_trims(path: Path, duration: float) -> tuple[float, float]:
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-45dB:d=0.5", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=max(60, duration * 2),
    )
    if result.returncode:
        # A suggestion must not block an otherwise usable import.
        return 0, duration
    starts = [float(value) for value in re.findall(r"silence_start: ([\d.e+-]+)", result.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end: ([\d.e+-]+)", result.stderr)]
    start = ends[0] if starts and ends and starts[0] <= 0.05 else 0
    end = starts[-1] if starts and (len(starts) > len(ends) or ends[-1] >= duration - 0.05) else duration
    return (start, end) if 0 <= start < end <= duration else (0, duration)
