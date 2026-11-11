import json
import math
import subprocess
from pathlib import Path


class AudioError(Exception):
    """An import failure with a message suitable for the person using the app."""


def probe(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except FileNotFoundError:
        raise AudioError("ffprobe is missing. Install ffmpeg and restart the app.") from None
    except subprocess.TimeoutExpired:
        raise AudioError("Reading this file took too long. Try another copy of the song.") from None
    if result.returncode:
        raise AudioError("This file could not be read. It may be damaged or not an audio or video file.")
    try:
        data = json.loads(result.stdout)
        streams = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"]
        if not streams:
            raise AudioError("This file has no audio.")
        duration = float(data.get("format", {}).get("duration", streams[0].get("duration", 0)))
        if not math.isfinite(duration) or duration <= 0:
            raise AudioError("Could not determine this file's audio length.")
        return {"duration": duration, "title": data.get("format", {}).get("tags", {}).get("title"), "audio": streams[0]}
    except (ValueError, KeyError, TypeError):
        raise AudioError("Could not read the audio information in this file.") from None
