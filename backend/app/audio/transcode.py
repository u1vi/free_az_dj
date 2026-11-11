import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .ffprobe import AudioError


def transcode(source: Path, destination: Path, duration: float, progress: Callable[[float], None]) -> None:
    temporary = destination.with_suffix(".part.wav")
    try:
        # A file for stderr avoids blocking on a full error pipe during decoding.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                ["ffmpeg", "-y", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(source),
                 "-vn", "-map", "0:a:0", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le",
                 "-threads", "2", "-progress", "pipe:1", "-nostats", str(temporary)],
                stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8", errors="replace",
            )
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    key, _, value = line.strip().partition("=")
                    if key == "out_time_us":
                        try:
                            progress(max(0, min(1, float(value) / 1_000_000 / duration)))
                        except ValueError:
                            pass
                if process.wait():
                    errors.seek(0, 2)
                    errors.seek(max(0, errors.tell() - 16_384))
                    if b"no space left on device" in errors.read().lower():
                        raise AudioError("Not enough disk space. Free some space and try again.")
                    raise AudioError("Could not convert this file. Try another copy or a different format.")
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        temporary.replace(destination)
    except FileNotFoundError:
        raise AudioError("ffmpeg is missing. Install it and restart the app.") from None
    finally:
        temporary.unlink(missing_ok=True)
